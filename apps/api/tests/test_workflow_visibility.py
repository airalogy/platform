"""Resolved Workflow values require source access for the actual API reader."""

import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.protocol import Protocol
from app.models.workflow_definition import WorkflowNodeResolution
from app.services import workflow_visibility as visibility
from app.services.research_runtime import canonical_digest
from app.services.workflow_resolutions import resolution_payload


def setup():
    project = SimpleNamespace(id=uuid4(), deleted_at=None)
    record = SimpleNamespace(
        id=uuid4(),
        version=1,
        protocol_id=uuid4(),
        hash="exact-record-hash",
        deleted_at=None,
        data={},
    )
    protocol = SimpleNamespace(
        id=record.protocol_id, project_id=project.id, deleted_at=None
    )
    run = SimpleNamespace(
        id=uuid4(),
        task_id=uuid4(),
        environment_snapshot={
            "manual_workflow": {
                "execution_contract_version": 2,
                "revision_id": str(uuid4()),
            }
        },
    )
    source = {
        "record_id": str(record.id),
        "record_version": 1,
        "record_hash": record.hash,
        "protocol_id": str(record.protocol_id),
    }
    row = SimpleNamespace(
        workflow_revision_id=run.environment_snapshot["manual_workflow"]["revision_id"],
        task_id=run.task_id,
        run_id=run.id,
        action_id=uuid4(),
        node_id="target",
        state="ready",
        initial_values={"measurement": 8173.125},
        receipt={"sources": {"source": source}, "bindings": [{"value": 8173.125}]},
    )
    row.digest = canonical_digest(resolution_payload(row))
    db = AsyncMock()
    db.scalars.side_effect = lambda statement: SimpleNamespace(
        all=lambda: (
            [row]
            if statement.column_descriptions[0]["entity"] is WorkflowNodeResolution
            else []
        )
    )
    db.scalar.return_value = record
    db.get.side_effect = lambda model, *_args, **_kwargs: (
        protocol if model is Protocol else None
    )
    return db, project, run, row, record


@pytest.mark.parametrize("status", [400, 403, 404, None])
def test_reader_is_checked_against_exact_source_record(monkeypatch, status):
    db, project, run, row, record = setup()
    reader = SimpleNamespace(id=uuid4())
    permission = AsyncMock(
        side_effect=HTTPException(status, "denied") if status else None
    )
    monkeypatch.setattr(visibility, "check_user_permission", permission)
    allowed = asyncio.run(
        visibility.workflow_data_readable(
            db, run=run, current_user=reader, project=project
        )
    )
    assert allowed is (status is None)
    assert permission.await_args.kwargs["user"] is reader
    assert permission.await_args.kwargs["record"] is record
    assert permission.await_args.kwargs["action"] == "read_record"
    if status:
        with pytest.raises(HTTPException) as denied:
            asyncio.run(
                visibility.require_workflow_data_readable(
                    db, run=run, current_user=reader, project=project
                )
            )
        assert denied.value.status_code == 403


@pytest.mark.parametrize("mutation", ["seal", "scope", "deleted", "hash", "version"])
def test_invalid_source_receipt_never_discloses_values(monkeypatch, mutation):
    db, project, run, row, record = setup()
    permission = AsyncMock()
    monkeypatch.setattr(visibility, "check_user_permission", permission)
    if mutation == "seal":
        row.initial_values = {"measurement": 123}
    elif mutation == "scope":
        project.id = uuid4()
    elif mutation == "deleted":
        record.deleted_at = "deleted"
    elif mutation == "hash":
        record.hash = "changed"
    else:
        row.receipt["sources"]["source"]["record_version"] = True
        row.digest = canonical_digest(resolution_payload(row))
    assert not asyncio.run(
        visibility.workflow_data_readable(
            db, run=run, current_user=SimpleNamespace(id=uuid4()), project=project
        )
    )
    permission.assert_not_awaited()


@pytest.mark.parametrize("marker", [{}, {"manual_workflow": {"revision_id": "legacy"}}])
def test_legacy_and_aira_read_paths_are_unchanged(marker):
    db = AsyncMock()
    assert asyncio.run(
        visibility.workflow_data_readable(
            db, run=SimpleNamespace(environment_snapshot=marker), current_user=None
        )
    )
    assert not db.mock_calls


def test_status_only_action_strips_every_value_copy_without_mutating_evidence():
    original = {
        "id": "card",
        "status": "proposed",
        "title": "Measurement",
        "input_data": {
            "protocol_id": "protocol",
            "initial_values": {"value": 8173.125},
            "workflow_resolution": {"receipt": {"value": 8173.125}},
        },
        "output_data": {"record": {"value": 8173.125}},
        "preview_digest": "valid-only-for-original-input",
        "protocol_run": {
            "initial_values": {"value": 8173.125},
            "validation_report": {"value": 8173.125},
        },
        "work_item": {"submission": {"value": 8173.125}},
        "approval": {"preview_digest": "valid-only-for-original-input"},
    }
    before = copy.deepcopy(original)
    result = visibility.restricted_workflow_payload(original, kind="action")
    assert result["id"] == "card" and result["status"] == "proposed"
    assert result["workflow_data_restricted"] is True
    assert result["input_data"] == {"protocol_id": "protocol"}
    assert "8173.125" not in str(result)
    assert "valid-only-for-original-input" not in str(result)
    assert original == before


@pytest.mark.parametrize("kind", ["run", "task"])
def test_status_only_result_never_claims_an_original_signed_package(kind):
    payload = {
        "id": "id",
        "status": "completed",
        "result_package": {"digest": "sealed", "actions": [{"value": 8173.125}]},
    }
    result = visibility.restricted_workflow_payload(payload, kind=kind)
    assert result["id"] == "id" and result["status"] == "completed"
    assert result["result_package"] == {}
    assert "sealed" not in str(result)
