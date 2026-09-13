"""Indivisible report/AI boundaries use the actual reader and all source assets."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.research import ResearchResultPackageSnapshot
from app.routers import research_result_packages as reports
from app.routers import research_tasks as tasks
from app.services import research_asset_visibility as assets
from app.services import research_runtime as runtime
from app.services import workflow_visibility


def context():
    user = SimpleNamespace(id=uuid4())
    task = SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        owner_user_id=uuid4(),
        revision=4,
        result_package={"evidence": [{"id": "old-task-evidence"}]},
        status="active",
    )
    run = SimpleNamespace(
        id=uuid4(),
        task_id=task.id,
        requested_by_user_id=user.id,
        result_package={"evidence": [{"id": "old-run-evidence"}]},
        environment_snapshot={},
        status="running",
        last_error=None,
    )
    return user, task, run


def test_complete_context_requires_all_task_sources_before_latest_run_only_data(
    monkeypatch,
):
    user, task, run = context()
    deny = AsyncMock(side_effect=HTTPException(403, "Earlier Run source is private"))
    snapshot = AsyncMock()
    monkeypatch.setattr(assets, "require_task_asset_sources_readable", deny)
    monkeypatch.setattr(assets, "require_asset_snapshot_sources_readable", snapshot)
    with pytest.raises(HTTPException, match="Earlier Run"):
        asyncio.run(
            runtime.require_research_context_readable(
                object(), task=task, run=run, current_user=user
            )
        )
    assert deny.await_args.kwargs == {"task_id": task.id, "user": user}
    snapshot.assert_not_awaited()


def test_complete_context_checks_unfiltered_task_and_run_packages(monkeypatch):
    user, task, run = context()
    whole = AsyncMock()
    snapshot = AsyncMock()
    workflow = AsyncMock()
    monkeypatch.setattr(assets, "require_task_asset_sources_readable", whole)
    monkeypatch.setattr(assets, "require_asset_snapshot_sources_readable", snapshot)
    monkeypatch.setattr(workflow_visibility, "require_workflow_data_readable", workflow)
    asyncio.run(
        runtime.require_research_context_readable(
            object(), task=task, run=run, current_user=user
        )
    )
    assert [call.kwargs["payload"] for call in snapshot.await_args_list] == [
        task.result_package,
        run.result_package,
    ]
    assert all(call.kwargs["user"] is user for call in snapshot.await_args_list)
    assert workflow.await_args.kwargs["current_user"] is user


@pytest.mark.parametrize("missing_actor", [False, True])
def test_aira_pauses_without_substituting_owner_when_requester_loses_source_access(
    monkeypatch, missing_actor
):
    user, task, run = context()
    project = SimpleNamespace(id=task.project_id, deleted_at=None)
    db = SimpleNamespace(
        get=AsyncMock(side_effect=[None if missing_actor else user, project]),
        commit=AsyncMock(),
    )
    denied = AsyncMock(side_effect=HTTPException(403, "Source is private"))
    monkeypatch.setattr(runtime, "require_research_context_readable", denied)
    monkeypatch.setattr(runtime, "require_research_capability", AsyncMock())
    monkeypatch.setattr(runtime, "emit_research_event", AsyncMock())
    allowed = asyncio.run(
        runtime._authorize_aira_research_context(db, task=task, run=run)
    )
    assert allowed is False
    assert task.status == run.status == "paused"
    assert db.get.await_args_list[0].args[1] == run.requested_by_user_id
    assert all(call.args[1] != task.owner_user_id for call in db.get.await_args_list)
    if missing_actor:
        denied.assert_not_awaited()
    else:
        assert denied.await_args.kwargs["current_user"] is user
    db.commit.assert_awaited_once()


def test_review_does_not_build_or_send_partial_context_when_old_sources_are_private(
    monkeypatch,
):
    user, task, run = context()
    monkeypatch.setattr(tasks, "_latest_run", AsyncMock(return_value=run))
    guard = AsyncMock(side_effect=HTTPException(403, "Old Evidence is private"))
    monkeypatch.setattr(tasks, "require_research_context_readable", guard)
    bundle = AsyncMock()
    monkeypatch.setattr(tasks, "research_asset_bundle", bundle)
    with pytest.raises(HTTPException, match="Old Evidence"):
        asyncio.run(tasks._research_review_context(object(), task, current_user=user))
    bundle.assert_not_awaited()
    assert guard.await_args.kwargs["current_user"] is user


def test_finalization_requires_whole_context_before_creating_any_seal(monkeypatch):
    user, task, run = context()
    task.status = "review_required"
    task.owner_user_id = user.id
    db = SimpleNamespace(
        scalars=AsyncMock(return_value=SimpleNamespace(one=lambda: task))
    )
    monkeypatch.setattr(
        tasks, "_task_context", AsyncMock(return_value=(task, object(), object()))
    )
    monkeypatch.setattr(tasks, "_latest_run", AsyncMock(return_value=run))
    monkeypatch.setattr(
        tasks,
        "require_research_context_readable",
        AsyncMock(side_effect=HTTPException(403, "Historical source is private")),
    )
    params = tasks.TaskCompleteParams(
        expected_revision=task.revision,
        outcome="goal_met",
        scientific_outcome="supports_hypothesis",
        conclusion="Reviewed conclusion",
    )
    with pytest.raises(HTTPException, match="Historical source"):
        asyncio.run(tasks.complete_research_task(task.id, params, user, db))
    assert task.status == "review_required"


@pytest.mark.parametrize("export", [False, True])
def test_old_sealed_package_get_and_export_recheck_exact_original_sources(
    monkeypatch, export
):
    user, task, run = context()
    run.run_number = 1
    package = {
        "evidence": [
            {
                "artifact_type": "record",
                "artifact_id": str(uuid4()),
                "artifact_version": "1",
            }
        ]
    }
    snapshot = SimpleNamespace(
        package=package, digest=runtime.canonical_digest(package)
    )
    db = SimpleNamespace(
        scalars=AsyncMock(return_value=SimpleNamespace(first=lambda: run))
    )
    monkeypatch.setattr(reports, "_authorized_task", AsyncMock(return_value=task))
    monkeypatch.setattr(reports, "require_workflow_data_readable", AsyncMock())
    monkeypatch.setattr(
        ResearchResultPackageSnapshot, "find_by", AsyncMock(return_value=snapshot)
    )
    guard = AsyncMock(side_effect=HTTPException(403, "Sealed Record is private"))
    monkeypatch.setattr(reports, "require_asset_snapshot_sources_readable", guard)
    endpoint = (
        reports.export_research_result_package
        if export
        else reports.get_research_result_package
    )
    with pytest.raises(HTTPException, match="Sealed Record"):
        asyncio.run(endpoint(task.id, user, db, run_id=run.id))
    assert guard.await_args.kwargs == {
        "task_id": task.id,
        "payload": package,
        "user": user,
    }


def test_replication_context_requires_actual_reader_access_to_original_sealed_run(
    monkeypatch,
):
    user, task, source = context()
    replication = SimpleNamespace(
        environment_snapshot={
            "run_origin": {
                "kind": "replication",
                "source_run_id": str(source.id),
            }
        }
    )
    db = SimpleNamespace(get=AsyncMock(return_value=source))
    guard = AsyncMock(side_effect=HTTPException(403, "Replication source private"))
    monkeypatch.setattr(tasks, "_require_run_package_sources", guard)
    with pytest.raises(HTTPException, match="Replication source private"):
        asyncio.run(
            tasks._reproduction_context(
                db,
                task,
                current_user=user,
                run=replication,
                scientific_assets={"evidence": []},
            )
        )
    assert guard.await_args.args == (db, task, source, user)


@pytest.mark.parametrize("denied", [False, True])
def test_ordinary_protocol_card_checks_live_record_not_historical_evidence(
    monkeypatch, denied
):
    user, task, run = context()
    project = SimpleNamespace(id=task.project_id, deleted_at=None)
    output = {"record": {"current": "actual displayed Record"}}
    action = SimpleNamespace(
        kind="protocol_run", run_id=run.id, status="completed", output_data=output
    )
    db = SimpleNamespace(get=AsyncMock(return_value=task))
    guard = AsyncMock(
        side_effect=HTTPException(403, "Record private") if denied else None
    )
    monkeypatch.setattr(assets, "_require_protocol_output_readable", guard)
    allowed = asyncio.run(
        workflow_visibility.workflow_action_data_readable(
            db, run=run, action=action, current_user=user, project=project
        )
    )
    assert allowed is not denied
    assert guard.await_args.kwargs == {
        "task": task,
        "action": action,
        "user": user,
        "output": output,
    }


def test_ordinary_pending_protocol_without_record_keeps_legacy_path():
    _, _, run = context()
    action = SimpleNamespace(kind="protocol_run", status="proposed", output_data={})
    assert asyncio.run(
        workflow_visibility.workflow_action_data_readable(
            object(), run=run, action=action, current_user=None, project=None
        )
    )


@pytest.mark.parametrize("kind", ["work_item", "approval"])
def test_embedded_run_redacted_without_disabling_independent_readable_card(
    monkeypatch, kind
):
    user, task, run = context()
    task.title, task.goal = "Task", "Study"
    run.as_dict = lambda: {
        "id": str(run.id),
        "status": "running",
        "aira_state": {"private": "history"},
        "result_package": {"private": "result"},
    }
    project = SimpleNamespace(id=task.project_id, uid="project", name="Project")
    lab = SimpleNamespace(id=uuid4(), uid="lab", name="Lab")
    action = SimpleNamespace(kind="protocol_run")
    action_data = {
        "assignee": None,
        "status": "approved",
        "input_data": {"initial_values": {"own": "readable"}},
    }
    monkeypatch.setattr(tasks, "_action_data", AsyncMock(return_value=action_data))
    monkeypatch.setattr(
        tasks,
        "require_research_context_readable",
        AsyncMock(side_effect=HTTPException(403, "Other branch private")),
    )
    monkeypatch.setattr(tasks, "has_research_capability", AsyncMock(return_value=True))
    if kind == "work_item":
        item = SimpleNamespace(
            assignee_user_id=user.id,
            status="open",
            as_dict=lambda: {
                "id": "item",
                "instructions": "Do this readable experiment",
            },
        )
        result = asyncio.run(
            tasks._work_item_data(object(), user, item, action, run, task, project, lab)
        )
        assert result["permissions"]["can_start"] is True
        assert result["instructions"] == "Do this readable experiment"
    else:
        monkeypatch.setattr(
            tasks,
            "_approval_summary",
            AsyncMock(return_value={"status": "pending", "preview_digest": "a" * 64}),
        )
        result = asyncio.run(
            tasks._approval_data(
                object(), object(), action, run, task, project, lab, current_user=user
            )
        )
        assert result["preview_digest"] == "a" * 64
    assert result["action"] == action_data
    assert result["run"]["workflow_data_restricted"] is True
    assert result["run"]["aira_state"] == result["run"]["result_package"] == {}
