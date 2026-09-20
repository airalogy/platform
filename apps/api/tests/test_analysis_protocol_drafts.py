"""Draft request, receipt and sealed revision checks without a database."""

import asyncio
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.services import analysis_protocol_drafts as service
from tests.test_analysis_protocol_packages import builtin_method


def content(**changes):
    return service.DraftContent.model_validate(
        {
            "method_id": uuid4(),
            "files": {"a": "", "b": "", "c": ""},
            "reason": "Document the stable method",
            **changes,
        }
    )


@pytest.mark.parametrize("mismatch", ["project", "protocol", "partial"])
def test_upload_rejects_inconsistent_source_before_any_target_lock(monkeypatch, mismatch):
    from fastapi import BackgroundTasks

    from app.routers import protocol_versions

    project_id, protocol_id = uuid4(), uuid4()
    draft = SimpleNamespace(
        project_id=project_id,
        target_protocol_id=protocol_id,
        base_protocol_version_id=uuid4(),
    )
    get_draft = AsyncMock(return_value=(draft, SimpleNamespace()))
    target_context = AsyncMock()
    project_find = AsyncMock()
    monkeypatch.setattr(service, "get_draft", get_draft)
    monkeypatch.setattr(service, "target_context", target_context)
    monkeypatch.setattr(protocol_versions.Project, "find", project_find)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(
            protocol_versions.upload_package(
                current_user=SimpleNamespace(id=uuid4()),
                db_session=object(),
                file=None,
                background_tasks=BackgroundTasks(),
                project_id=uuid4() if mismatch == "project" else project_id,
                protocol_id=uuid4() if mismatch == "protocol" else protocol_id,
                source_analysis_protocol_draft_id=uuid4(),
                source_analysis_protocol_revision=1,
                source_analysis_protocol_digest="a" * 64,
                source_analysis_protocol_preview_digest="b" * 64,
                source_analysis_protocol_preview_token=None
                if mismatch == "partial"
                else "receipt",
            )
        )
    assert caught.value.status_code == 422
    target_context.assert_not_awaited()
    project_find.assert_not_awaited()
    if mismatch == "partial":
        get_draft.assert_not_awaited()


@pytest.mark.parametrize(
    "changes",
    [
        {"target_protocol_id": uuid4()},
        {"base_protocol_version_id": uuid4()},
        {"reason": "   "},
        {"state": "reviewed"},
        {"approved_by": str(uuid4())},
        {"files": {"protocol.aimd": "text"}},
    ],
)
def test_draft_requires_exact_target_and_no_client_approval(changes):
    with pytest.raises(ValidationError):
        content(**changes)


def test_content_normalizes_reason_but_never_file_bytes():
    request = content(
        reason="  explain this  ", files={"a": " x\r\n", "b": "y\n", "c": "z"}
    )
    assert request.reason == "explain this"
    assert request.files["a"] == " x\r\n"
    assert request.files["b"] == "y\n"


def test_blank_review_and_revision_notes_are_request_validation_errors():
    with pytest.raises(ValidationError):
        service.RevisionContent(
            expected_revision=1, files={"a": "", "b": "", "c": ""}, reason="  "
        )
    with pytest.raises(ValidationError):
        service.ReviewRequest(
            expected_revision=1,
            package_digest="a" * 64,
            decision="reviewed",
            note=" \n ",
        )


@pytest.mark.parametrize("alter", ["user", "purpose", "digest", "signature"])
def test_receipt_binds_actor_operation_and_exact_preview(alter):
    actor = uuid4()
    token, expires = service._receipt(user_id=actor, purpose="create", digest="a" * 64)
    assert expires
    service.verify_receipt(token, user_id=actor, purpose="create", digest="a" * 64)
    with pytest.raises(HTTPException) as caught:
        service.verify_receipt(
            "invalid" if alter == "signature" else token,
            user_id=uuid4() if alter == "user" else actor,
            purpose="publish:another:1" if alter == "purpose" else "create",
            digest="b" * 64 if alter == "digest" else "a" * 64,
        )
    assert caught.value.status_code == 409


def test_expired_receipt_cannot_authorize_a_new_write(monkeypatch):
    monkeypatch.setattr(service, "PREVIEW_TTL", timedelta(seconds=-60))
    actor = uuid4()
    token, _ = service._receipt(user_id=actor, purpose="create", digest="a" * 64)
    with pytest.raises(HTTPException) as caught:
        service.verify_receipt(token, user_id=actor, purpose="create", digest="a" * 64)
    assert caught.value.status_code == 409


def test_file_manifest_preserves_exact_utf8_size_and_content():
    from hashlib import sha256

    result = service.files_manifest({"z": "实验\n", "a": "x\r\n"})
    assert result == [
        {"path": "a", "size_bytes": 3, "sha256": sha256(b"x\r\n").hexdigest()},
        {"path": "z", "size_bytes": 7, "sha256": sha256("实验\n".encode()).hexdigest()},
    ]


def test_revision_integrity_covers_editable_files_manifest_and_method():
    method = builtin_method()
    method.digest = "a" * 64
    method.title = "Stable method"
    package = service._package(method)
    row = SimpleNamespace(
        files=deepcopy(package.files),
        package_digest=package.content_digest,
        manifest_digest=package.manifest_digest,
        method_digest=method.digest,
    )
    assert service.verify_revision(method, row).content_digest == package.content_digest
    row.files["protocol.aimd"] += "\nChanged after review.\n"
    with pytest.raises(HTTPException) as caught:
        service.verify_revision(method, row)
    assert caught.value.status_code == 409
    row.files = deepcopy(package.files)
    row.method_digest = "b" * 64
    with pytest.raises(HTTPException):
        service.verify_revision(method, row)


def test_legacy_upload_direct_call_defaults_do_not_inject_source_body_objects():
    from inspect import signature

    from app.routers.protocol_versions import upload_package

    parameters = signature(upload_package).parameters
    for name in parameters:
        if name.startswith("source_analysis_protocol_"):
            assert parameters[name].default is None


def test_unpublished_packages_and_preview_receipts_never_enter_body_logs(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock, Mock

    from starlette.requests import Request
    from starlette.responses import Response

    from app import routers

    monkeypatch.setattr(routers.config, "LOG_REQUEST_BODIES", True)
    log = Mock()
    monkeypatch.setattr(routers.logger, "info", log)
    receive = AsyncMock(
        return_value={
            "type": "http.request",
            "body": b'{"files":{"protocol.aimd":"unpublished findings"},"preview_token":"secret"}',
        }
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/analysis-protocol-drafts/preview",
            "scheme": "http",
            "server": ("testserver", 80),
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
        },
        receive=receive,
    )
    response = asyncio.run(
        routers.logger_middleware(request, AsyncMock(return_value=Response("ok")))
    )
    assert response.status_code == 200
    receive.assert_not_awaited()
    assert log.call_args.args == ("POST /analysis-protocol-drafts/preview",)
