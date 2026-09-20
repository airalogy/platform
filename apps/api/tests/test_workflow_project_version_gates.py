"""Version 7 uses existing authorization/governance paths, never legacy fallback."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.services import workflow_analysis_runtime, workflow_compute_runtime
from app.services.research_runtime import _workflow_resolution_v2
from app.services.workflow_asset_runtime import asset_rows_for_run
from app.services.workflow_visibility import (
    workflow_action_data_readable,
    workflow_data_readable,
)
from tests.test_project_analysis_engine import project_fixture


def workflow_run(version=7, **marker):
    return SimpleNamespace(
        id=uuid4(),
        task_id=uuid4(),
        requested_by_user_id=uuid4(),
        environment_snapshot={
            "manual_workflow": {
                "execution_contract_version": version,
                **marker,
            }
        },
    )


@pytest.mark.parametrize("version", range(1, 8))
def test_supported_contracts_use_the_expected_resolution_lifecycle(version):
    assert _workflow_resolution_v2(workflow_run(version)) is (version >= 2)


def test_new_contract_rejects_anonymous_full_and_analysis_card_reads():
    async def scenario():
        run = workflow_run()
        action = SimpleNamespace(kind="analysis_run", output_data={}, status="blocked")
        project = SimpleNamespace(deleted_at=None)
        assert not await workflow_data_readable(
            None, run=run, current_user=None, project=project
        )
        assert not await workflow_action_data_readable(
            None, run=run, action=action, current_user=None, project=project
        )

    asyncio.run(scenario())


def test_new_contract_still_requires_pinned_compute_governance():
    action = SimpleNamespace(input_data={"action_graph": {"node_id": "compute"}})
    with pytest.raises(HTTPException):
        workflow_compute_runtime.governance(workflow_run(), action)
    policy = {"approver_user_id": str(uuid4()), "currency": "USD", "cost_cap": "1"}
    run = workflow_run(compute_governance={"compute": policy})
    assert workflow_compute_runtime.governance(run, action) == policy


def test_new_contract_does_not_skip_asset_receipt_identity_verification():
    async def scenario():
        db = SimpleNamespace(get=AsyncMock(return_value=None))
        with pytest.raises(HTTPException) as invalid:
            await asset_rows_for_run(
                db,
                task=SimpleNamespace(project_id=uuid4()),
                run=workflow_run(revision_id=str(uuid4())),
            )
        assert invalid.value.status_code == 409
        db.get.assert_awaited_once()

    asyncio.run(scenario())


def test_project_input_authorization_checks_every_slot_for_every_recipient(monkeypatch):
    async def scenario():
        _, snapshot = project_fixture()
        task = SimpleNamespace(
            owner_user_id=uuid4(), project_id=UUID(snapshot["project_id"])
        )
        run = workflow_run()
        action = SimpleNamespace(assignee_user_id=uuid4(), input_data={})
        approver = SimpleNamespace(id=uuid4())
        users = {
            identity: SimpleNamespace(id=identity)
            for identity in (
                task.owner_user_id,
                run.requested_by_user_id,
                action.assignee_user_id,
                approver.id,
            )
        }
        db = SimpleNamespace(
            get=AsyncMock(side_effect=lambda _model, identity: users[identity])
        )
        project = SimpleNamespace(id=task.project_id)
        check_scope = AsyncMock(return_value=(None, project, False))
        check_manifest = AsyncMock()
        monkeypatch.setattr(workflow_analysis_runtime, "analysis_scope", check_scope)
        monkeypatch.setattr(
            workflow_analysis_runtime, "authorize_source_manifest", check_manifest
        )
        await workflow_analysis_runtime.authorize_analysis_sources(
            db,
            task=task,
            run=run,
            action=action,
            snapshot=snapshot,
            extra_user=approver,
        )
        checked = {
            (args.args[1], args.args[2].id) for args in check_manifest.await_args_list
        }
        assert checked == {
            (UUID(item["snapshot"]["protocol_id"]), identity)
            for item in snapshot["inputs"]
            for identity in users
        }
        assert check_scope.await_count == check_manifest.await_count == 8

    asyncio.run(scenario())


def test_project_cancellation_uses_the_ordinary_non_compute_analysis_path(monkeypatch):
    async def scenario():
        analysis = SimpleNamespace(
            status="pending", engine_version="airalogy.project-analysis.v1"
        )
        db = SimpleNamespace(
            execute=AsyncMock(
                return_value=SimpleNamespace(all=lambda: [(None, analysis)])
            )
        )
        cancel = AsyncMock()
        stop_computes = AsyncMock()
        monkeypatch.setattr(workflow_analysis_runtime, "cancel_analysis", cancel)
        monkeypatch.setattr(
            workflow_compute_runtime, "stop_workflow_computes", stop_computes
        )
        run = workflow_run()
        await workflow_analysis_runtime.cancel_workflow_analyses(db, run=run)
        cancel.assert_awaited_once_with(db, analysis)
        stop_computes.assert_awaited_once_with(db, run=run)

    asyncio.run(scenario())
