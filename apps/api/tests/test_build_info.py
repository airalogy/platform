import asyncio
from unittest.mock import AsyncMock, Mock

import app.build_info as build_info_module
from app.build_info import resolve_build_info
from app.routers.system import system_version


def test_build_info_prefers_explicit_release_environment(monkeypatch):
    monkeypatch.setenv("PLATFORM_VERSION", "1.2.3")
    monkeypatch.setenv("GIT_TAG", "v1.2.3")
    monkeypatch.setenv("GIT_COMMIT", "a" * 40)
    monkeypatch.setenv("BUILD_TIME", "2026-08-14T00:00:00Z")
    monkeypatch.setenv("BUILD_DIRTY", "false")

    info = resolve_build_info()

    assert info.version == "1.2.3"
    assert info.tag == "v1.2.3"
    assert info.commit == "a" * 40
    assert info.build_time == "2026-08-14T00:00:00Z"
    assert info.dirty is False
    assert info.release_manifest_sha256 is None


def test_baked_build_identity_cannot_be_relabelled_by_runtime_environment(monkeypatch):
    monkeypatch.setattr(
        build_info_module,
        "_read_json",
        lambda _path: {
            "version": "1.2.3",
            "tag": "v1.2.3",
            "commit": "a" * 40,
            "build_time": "2026-08-14T00:00:00Z",
            "dirty": True,
        },
    )
    monkeypatch.setenv("PLATFORM_VERSION", "9.9.9")
    monkeypatch.setenv("GIT_COMMIT", "b" * 40)
    monkeypatch.setenv("BUILD_DIRTY", "false")

    info = resolve_build_info()

    assert info.version == "1.2.3"
    assert info.commit == "a" * 40
    assert info.dirty is True


def test_system_version_includes_database_revision(monkeypatch):
    result = Mock()
    result.scalar_one_or_none.return_value = "0008_record_exports"
    db_session = AsyncMock()
    db_session.execute.return_value = result
    monkeypatch.setenv("PLATFORM_VERSION", "1.2.3")

    payload = asyncio.run(system_version(db_session))

    assert payload["version"] == "1.2.3"
    assert payload["database_revision"] == "0008_record_exports"
    db_session.execute.assert_awaited_once()


def test_system_version_survives_database_diagnostics(monkeypatch):
    db_session = AsyncMock()
    db_session.execute.side_effect = RuntimeError("database unavailable")
    monkeypatch.setenv("PLATFORM_VERSION", "1.2.3")

    payload = asyncio.run(system_version(db_session))

    assert payload["version"] == "1.2.3"
    assert payload["database_revision"] == "unavailable"
