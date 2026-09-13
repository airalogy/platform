"""Pure security boundaries for Workflow file references; no object services."""

import asyncio
import hashlib
import io
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from jose import jwt

from app.config import config
from app.models.airalogy_file import AiralogyFile
from app.routers.airalogy_files import (
    RegisterExternalAiralogyFilePayload,
    register_external_airalogy_file,
)
from app.services import account_security
from app.services import workflow_files as files


def alias():
    return AiralogyFile(
        id=uuid4(),
        filename="result.json",
        protocol_id=uuid4(),
        user_id=uuid4(),
        storage_backend=files.WORKFLOW_FILE_BACKEND,
    )


@pytest.mark.parametrize(
    "method,args",
    [
        ("local_url", ()),
        ("file_object_url", ()),
        ("get_file_content", ()),
        ("download_file", ("/must-not-write",)),
        ("copy_file", ("must-not-copy",)),
    ],
)
def test_alias_never_reaches_an_ordinary_storage_backend(method, args):
    with pytest.raises(ValueError, match="source-authorized"):
        asyncio.run(getattr(alias(), method)(*args))


def test_alias_stream_and_delete_do_not_access_shared_storage():
    async def exercise():
        item = alias()
        with pytest.raises(ValueError, match="source-authorized"):
            await anext(item.get_file_with_stream())
        assert await item.delete_file() is None

    asyncio.run(exercise())


def test_external_registration_cannot_forge_the_reserved_alias_backend():
    params = RegisterExternalAiralogyFilePayload(
        protocol_id=uuid4(),
        filename="forged.json",
        external_uri="https://example.test/forged.json",
        storage_backend=files.WORKFLOW_FILE_BACKEND,
    )
    with pytest.raises(HTTPException) as failure:
        asyncio.run(register_external_airalogy_file(params, None, None))
    assert failure.value.status_code == 422


@pytest.mark.parametrize(
    "error", [ValueError("removed"), KeyError("origin"), TypeError("invalid")]
)
def test_source_contract_errors_are_denied_and_recursion_context_is_restored(
    monkeypatch, error
):
    identity = uuid4()
    implementation = AsyncMock(side_effect=error)
    monkeypatch.setattr(files, "_authorize_binding", implementation)

    async def exercise():
        with pytest.raises(HTTPException) as failure:
            await files.authorize_binding(None, identity, object())
        assert failure.value.status_code == 409
        assert files._ACTIVE_FILES.get() == frozenset()
        implementation.side_effect = None
        implementation.return_value = "readable"
        assert await files.authorize_binding(None, identity, object()) == "readable"
        assert files._ACTIVE_FILES.get() == frozenset()

    asyncio.run(exercise())


@pytest.mark.parametrize("body", [b"source", b"change", b"longer-than-source", b""])
def test_blob_bytes_are_verified_before_the_first_response_byte(monkeypatch, body):
    async def chunks(*args, **kwargs):
        yield body

    monkeypatch.setattr(files, "get_file_with_stream", chunks)
    blob = SimpleNamespace(
        size_bytes=6,
        checksum_sha256=hashlib.sha256(b"source").hexdigest(),
        storage_object_key="private/key",
        storage_backend="minio",
    )

    async def exercise():
        if body == b"source":
            handle = await files.verified_blob_spool(blob)
            try:
                assert handle.read() == b"source"
            finally:
                handle.close()
        else:
            with pytest.raises(HTTPException) as failure:
                await files.verified_blob_spool(blob)
            assert failure.value.status_code == 409

    asyncio.run(exercise())


def test_archive_has_its_own_exact_byte_bound_not_a_single_file_limit(monkeypatch):
    body = b"two-files"

    async def chunks(*args, **kwargs):
        yield body

    monkeypatch.setattr(files, "get_file_with_stream", chunks)
    blob = SimpleNamespace(
        size_bytes=len(body),
        checksum_sha256=hashlib.sha256(body).hexdigest(),
        storage_object_key="private/archive",
        storage_backend="minio",
    )

    async def exercise():
        with pytest.raises(HTTPException) as failure:
            await files.verified_blob_spool(blob, max_bytes=4)
        assert failure.value.status_code == 413
        handle = await files.verified_blob_spool(blob, max_bytes=blob.size_bytes)
        try:
            assert handle.read() == body
        finally:
            handle.close()
        blob.size_bytes -= 1
        with pytest.raises(HTTPException) as tampered:
            await files.verified_blob_spool(blob, max_bytes=blob.size_bytes)
        assert tampered.value.status_code == 409

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "filename,body",
    [
        ("fake.pdf", b"<html>unsafe</html>"),
        ("../escape.csv", b"a,b\n"),
        ("x\r\ny.csv", b"a,b"),
    ],
)
def test_file_header_and_filename_fail_closed(filename, body):
    with pytest.raises(ValueError):
        files.validate_file_header(io.BytesIO(body), filename)


def test_nested_file_references_are_not_treated_as_unprotected_text():
    a, b = uuid4(), uuid4()
    assert set(
        files.file_ids(
            {
                "unrelated": [{"notes": f"airalogy.id.file.{a}.pdf"}],
                "var": {"file": f"airalogy.id.file.{b}.csv"},
            }
        )
    ) == {a, b}


def test_reference_scan_covers_browser_and_sdk_noncanonical_lookup_spellings():
    a, b = uuid4(), uuid4()
    for value in (
        f"airalogy.id.file.{str(a).upper()}.JSON",
        f"airalogy.id.file.{a}.json.extra",
        f"airalogy.id.fileanything.{a}.json",
        f"airalogy.id.file.{{{a}}}.json",
    ):
        assert a in set(files.file_ids({"nested": [value]}))
    assert set(files.file_ids(f"airalogy.id.file.{a}.{b}.json")) == {a, b}


def test_private_preview_token_is_scoped_expiring_and_auth_version_bound(monkeypatch):
    user, target = SimpleNamespace(id=uuid4()), uuid4()
    db = SimpleNamespace(get=AsyncMock(return_value=user))
    current = AsyncMock(return_value=3)
    monkeypatch.setattr(account_security, "get_auth_version", current)

    async def exercise():
        token = await files.token_for(db, purpose="file", identity=target, user=user)
        assert (
            await files.token_user(db, token, purpose="file", identity=target) is user
        )
        for purpose, identity in [("export", target), ("file", uuid4())]:
            with pytest.raises(HTTPException) as failure:
                await files.token_user(db, token, purpose=purpose, identity=identity)
            assert failure.value.status_code == 401
        data = jwt.decode(
            token,
            config.SECRET_KEY,
            algorithms=["HS256"],
            audience="workflow-private-download",
        )
        assert "user" not in data
        data["exp"] = datetime.now(UTC) - timedelta(seconds=1)
        expired = jwt.encode(data, config.SECRET_KEY, algorithm="HS256")
        with pytest.raises(HTTPException):
            await files.token_user(db, expired, purpose="file", identity=target)
        current.return_value = 4
        with pytest.raises(HTTPException):
            await files.token_user(db, token, purpose="file", identity=target)

    asyncio.run(exercise())


def test_cyclic_file_lineage_stops_before_database_access():
    identity = uuid4()
    token = files._ACTIVE_FILES.set(frozenset({identity}))
    try:
        with pytest.raises(HTTPException) as failure:
            asyncio.run(
                files.authorize_binding(None, identity, SimpleNamespace(id=uuid4()))
            )
        assert failure.value.status_code == 409
    finally:
        files._ACTIVE_FILES.reset(token)
