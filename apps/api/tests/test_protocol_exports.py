import asyncio
import json
import shutil
import stat
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from airalogy.archive import unpack_archive, validate_archive
from fastapi import HTTPException

from app.routers import protocol_versions as router
from app.services.protocol_exports import build_protocol_export


def source_package(path, extra=None):
    files = {
        "protocol.aimd": "# Synthetic protocol\n{{var|sample: str}}\n",
        "protocol.toml": '[airalogy_protocol]\nid="synthetic"\nname="Synthetic"\nversion="0.1.0"\n',
        "files/figure.svg": '<svg xmlns="http://www.w3.org/2000/svg"/>',
        ".env": "DO_NOT_EXPORT=synthetic-secret",
        "__pycache__/model.pyc": "cache",
        "tmp_aimd_model.py": "runtime file",
    }
    files.update(extra or {})
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr("wrapped/" + name, content)
    return path


@pytest.mark.parametrize("format", ["aira", "zip"])
def test_export_uses_exact_source_without_secrets_or_runtime_files(tmp_path, format):
    source = source_package(tmp_path / "source.zip")
    original = source.read_bytes()
    output = build_protocol_export(source, tmp_path, format)
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        assert names - {"_airalogy_archive/manifest.json"} == {
            "protocol.aimd",
            "protocol.toml",
            "files/figure.svg",
        }
        assert archive.read("protocol.aimd").startswith(b"# Synthetic")
        if format == "aira":
            manifest = json.loads(archive.read("_airalogy_archive/manifest.json"))
            assert manifest["kind"] == "protocol"
            assert set(manifest["protocol"]["file_hashes"]) == names - {
                "_airalogy_archive/manifest.json"
            }
    if format == "aira":
        assert validate_archive(output) == (True, [])
        unpack_archive(output, tmp_path / "roundtrip")
        assert (tmp_path / "roundtrip/protocol.aimd").is_file()
    assert source.read_bytes() == original


@pytest.mark.parametrize("name", ["../escape", "/absolute", "files\\escape"])
def test_unsafe_paths_are_rejected(tmp_path, name):
    source = source_package(tmp_path / "source.zip")
    with zipfile.ZipFile(source, "a") as archive:
        archive.writestr(name, "unsafe")
    with pytest.raises(ValueError):
        build_protocol_export(source, tmp_path, "aira")


def test_symlink_members_are_rejected(tmp_path):
    source = source_package(tmp_path / "source.zip")
    with zipfile.ZipFile(source, "a") as archive:
        member = zipfile.ZipInfo("wrapped/link")
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(member, "/outside")
    with pytest.raises(ValueError, match="Unsafe"):
        build_protocol_export(source, tmp_path, "aira")


def test_duplicate_members_are_rejected(tmp_path):
    source = source_package(tmp_path / "source.zip")
    with zipfile.ZipFile(source, "a") as archive, pytest.warns(UserWarning):
        archive.writestr("wrapped/protocol.toml", "duplicate")
    with pytest.raises(ValueError, match="Duplicate"):
        build_protocol_export(source, tmp_path, "aira")


def test_legacy_redundant_inline_python_exports_to_valid_aira(tmp_path):
    python = """from airalogy.assigner import assigner, AssignerResult
@assigner(assigned_fields=["b"], dependent_fields=["a"], mode="auto")
def double_a(dep):
    return AssignerResult(assigned_fields={"b": dep["a"] * 2})
"""
    source = source_package(
        tmp_path / "source.zip",
        {
            "protocol.aimd": "{{var|a: float}}\n{{var|b: float}}\n```assigner\n"
            + python
            + "```\n",
            "assigner.py": python,
        },
    )
    output = build_protocol_export(source, tmp_path, "aira")
    assert validate_archive(output) == (True, [])
    with zipfile.ZipFile(output) as archive:
        assert "assigner.py" not in archive.namelist()


def test_download_rechecks_access_uses_selected_version_and_cleans_up(
    tmp_path, monkeypatch
):
    source = source_package(tmp_path / "source.zip")
    protocol = SimpleNamespace(id=uuid4(), project_id=uuid4(), uid="synthetic")

    async def download(destination):
        shutil.copyfile(source, destination)

    package = SimpleNamespace(
        version="0.1.0", download_package=AsyncMock(side_effect=download)
    )
    monkeypatch.setattr(router.Protocol, "find", AsyncMock(return_value=protocol))
    monkeypatch.setattr(router.Project, "find", AsyncMock(return_value=object()))
    find_version = AsyncMock(return_value=package)
    monkeypatch.setattr(router.ProtocolVersion, "find_by", find_version)
    permission = AsyncMock()
    monkeypatch.setattr(router, "check_user_permission", permission)
    response = asyncio.run(
        router.export_protocol_package(protocol.id, "0.1.0", None, object(), "aira")
    )
    assert response.filename == "synthetic-v0.1.0.aira"
    assert response.headers["cache-control"] == "private, no-store"
    assert validate_archive(response.path) == (True, [])
    assert find_version.call_args.args[1][1].right.value == "0.1.0"
    folder = Path(response.path).parent
    asyncio.run(response.background())
    assert not folder.exists()
    permission.side_effect = HTTPException(403, "Not allowed")
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            router.export_protocol_package(protocol.id, "0.1.0", None, object(), "zip")
        )
    assert error.value.status_code == 403
    package.download_package.assert_awaited_once()
