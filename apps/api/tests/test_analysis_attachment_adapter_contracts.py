"""Attachment integration contracts; real storage/execution has separate tests."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services import (
    analysis_compute,
    analysis_compute_files,
    research_compute,
    workflow_analysis_methods,
    workflow_analysis_runtime,
)
from app.services.analysis_compute_contracts import AnalysisComputeRecipe


@pytest.mark.parametrize("denied", [None, "owner", "requester", "assignee", "reviewer"])
def test_each_workflow_recipient_needs_attachment_source_access(monkeypatch, denied):
    users = {
        name: SimpleNamespace(id=uuid4())
        for name in ("owner", "requester", "assignee", "reviewer")
    }
    by_id = {user.id: user for user in users.values()}
    project = SimpleNamespace(id=uuid4())
    task = SimpleNamespace(owner_user_id=users["owner"].id, project_id=project.id)
    run = SimpleNamespace(requested_by_user_id=users["requester"].id)
    envelope = {"schema": "synthetic-already-sealed-attachment-envelope"}
    action = SimpleNamespace(
        assignee_user_id=users["assignee"].id,
        input_data={
            "analysis_input": {"summary": {"compute": {"input_files": envelope}}}
        },
    )
    snapshot = {"protocol_id": str(uuid4()), "records": []}
    db = SimpleNamespace(
        get=AsyncMock(side_effect=lambda model, identity: by_id[identity])
    )
    monkeypatch.setattr(
        workflow_analysis_runtime,
        "analysis_scope",
        AsyncMock(return_value=(None, project, False)),
    )
    monkeypatch.setattr(
        workflow_analysis_runtime, "authorize_source_manifest", AsyncMock()
    )
    checked = set()

    async def authorize(session, selected, files, user):
        assert session is db and selected is snapshot and files is envelope
        checked.add(user.id)
        if denied and user.id == users[denied].id:
            raise HTTPException(403, "Synthetic source revocation")

    monkeypatch.setattr(
        analysis_compute_files, "authorize_preview_input_files", authorize
    )
    operation = workflow_analysis_runtime.authorize_analysis_sources(
        db,
        task=task,
        run=run,
        action=action,
        snapshot=snapshot,
        extra_user=users["reviewer"],
    )
    if denied:
        with pytest.raises(HTTPException) as error:
            asyncio.run(operation)
        assert error.value.status_code == 403
        assert users[denied].id in checked
    else:
        asyncio.run(operation)
        assert checked == set(by_id)


@pytest.mark.parametrize("file_type", ["file", "plain", "missing"])
def test_published_compute_method_validates_attachment_field_not_private_files(
    monkeypatch, file_type
):
    field = {"type": "string"}
    if file_type == "file":
        field.update(airalogy_type="FileIdCSV", file_extension="csv")
    version = SimpleNamespace(
        version="1.0.0",
        fields={"vars": ["attachment"]},
        json_schema={
            "vars": {
                "type": "object",
                "properties": {"attachment": field} if file_type != "missing" else {},
            }
        },
    )
    recipe = AnalysisComputeRecipe(
        environment_revision_id=uuid4(),
        language="python",
        source_code="pass\n",
        input_files=[{"input_id": "sample", "field_path": ["var", "attachment"]}],
    )
    environment = SimpleNamespace(result_schema={"type": "object"})
    monkeypatch.setattr(
        analysis_compute,
        "environment_for_recipe",
        AsyncMock(return_value=(environment, environment)),
    )
    monkeypatch.setattr(research_compute, "compute_environment_snapshot", lambda *_: {})
    # Publishing only the field declaration must not read or share private bytes.
    forbidden = AsyncMock(
        side_effect=AssertionError("Publication must not read attachments")
    )
    monkeypatch.setattr(analysis_compute_files, "preview_input_files", forbidden)
    operation = workflow_analysis_methods.compute_publication_contract(
        None, SimpleNamespace(), recipe, version, None
    )
    if file_type == "file":
        contract = asyncio.run(operation)
        assert contract["input_schema_contract"]["json_schema"] == version.json_schema
        assert "input_files" not in contract
    else:
        with pytest.raises(ValueError, match="typed FileId"):
            asyncio.run(operation)
    forbidden.assert_not_called()
