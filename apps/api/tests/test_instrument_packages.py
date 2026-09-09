import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routers import instrument_packages as routes


def test_source_review_requires_explicit_ack_and_no_unknown_authority_flags():
    for change in (
        {},
        {"source_reviewed": True, "reason": " "},
        {"source_reviewed": True, "hardware_authorized": True},
    ):
        with pytest.raises(ValidationError):
            routes.ReviewDraft(
                **{
                    "expected_revision": 1,
                    "operation": "approve_source",
                    "reason": "Reviewed",
                    **change,
                }
            )


def test_import_digest_binds_actor_lab_request_and_exact_bytes():
    user, lab, request_id = uuid4(), uuid4(), uuid4()
    inspection = {"archive_digest": "a" * 64, "manifest_digest": "b" * 64}
    original = routes._import_preview(user, lab, request_id, inspection, None)
    assert (
        not original["hardware_authorized"] and not original["installation_authorized"]
    )
    for args in [
        (uuid4(), lab, request_id, inspection),
        (user, uuid4(), request_id, inspection),
        (user, lab, uuid4(), inspection),
        (user, lab, request_id, {**inspection, "archive_digest": "c" * 64}),
    ]:
        assert (
            original["preview_digest"]
            != routes._import_preview(*args, None)["preview_digest"]
        )


def test_review_is_stale_guarded_terminal_and_never_hardware_authority():
    user = uuid4()
    row = SimpleNamespace(
        id=uuid4(),
        lab_id=uuid4(),
        archive_digest="a" * 64,
        manifest_digest="b" * 64,
        state="imported",
        revision=1,
    )
    params = routes.ReviewDraft(
        expected_revision=1,
        operation="approve_source",
        reason="Source checked",
        source_reviewed=True,
    )
    preview = routes._review_preview(row, user, params)
    assert not preview["installation_authorized"]
    changed = params.model_copy(update={"reason": "Different source assertion"})
    assert (
        preview["preview_digest"]
        != routes._review_preview(row, user, changed)["preview_digest"]
    )
    row.revision = 2
    with pytest.raises(HTTPException) as stale:
        routes._review_preview(row, user, params)
    assert stale.value.status_code == 409
    row.revision, row.state = 1, "revoked"
    with pytest.raises(HTTPException):
        routes._review_preview(row, user, params)


def test_upload_authorization_precedes_parsing(monkeypatch):
    parse = AsyncMock()
    monkeypatch.setattr(routes, "_read_inspection", parse)
    monkeypatch.setattr(
        routes, "_authorize", AsyncMock(side_effect=HTTPException(403, "Denied"))
    )
    with pytest.raises(HTTPException):
        asyncio.run(
            routes.preview_import(
                object(), uuid4(), uuid4(), SimpleNamespace(id=uuid4()), object()
            )
        )
    parse.assert_not_awaited()


def test_upload_declared_and_actual_byte_limits():
    class Request:
        def __init__(self):
            self.headers = {"content-length": "1", "content-type": "application/zip"}

        async def stream(self):
            yield b"excess"

    with pytest.raises(HTTPException) as oversized:
        asyncio.run(routes._read_inspection(Request()))
    assert oversized.value.status_code == 413
