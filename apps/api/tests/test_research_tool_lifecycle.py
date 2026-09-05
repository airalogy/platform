"""Small regression checks; real transaction coverage lives in research integration."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.research import ResearchAction, ResearchRun, ResearchTask
from app.models.research_execution import ResearchToolJob
from app.services import research_tools
from app.services.persistent_jobs import JobDeferred, defer_job


def context():
    task = ResearchTask(
        id=uuid4(),
        status="active",
        revision=1,
        archived_at=None,
        project_id=uuid4(),
        lab_id=uuid4(),
        owner_user_id=uuid4(),
        autonomy_level="assisted",
        deadline_at=None,
        budget_limit=None,
    )
    run = ResearchRun(
        id=uuid4(),
        task_id=task.id,
        status="waiting_for_tool",
        requested_by_user_id=task.owner_user_id,
        aira_state={},
        environment_snapshot={},
    )
    action = ResearchAction(
        id=uuid4(),
        run_id=run.id,
        status="queued",
        revision=1,
        input_data={"resume_run": True, "source": "manual"},
        requirements={},
        policy_decision="allow",
        executor_type="platform_tool",
        preview_digest="a" * 64,
    )
    job = ResearchToolJob(
        id=uuid4(),
        action_id=action.id,
        status="queued",
        tool_key="knowledge.search",
        tool_version="1",
        arguments={"query": "test"},
        timeout_seconds=60,
    )
    return task, run, action, job


@pytest.mark.parametrize("paused", ["task", "run"])
def test_paused_tool_never_dispatches(monkeypatch, paused):
    objects = context()
    objects[0 if paused == "task" else 1].status = "paused"
    monkeypatch.setattr(
        research_tools, "_locked_tool_context", AsyncMock(return_value=objects)
    )
    execute = AsyncMock()
    monkeypatch.setattr(research_tools, "execute_research_tool", execute)
    with pytest.raises(JobDeferred, match="paused"):
        asyncio.run(
            research_tools.process_research_tool_job(
                AsyncMock(), tool_job_id=objects[3].id
            )
        )
    execute.assert_not_awaited()
    assert objects[3].status == "queued"


@pytest.mark.parametrize("state", ["cancelled", "completed", "failed"])
@pytest.mark.parametrize("terminal", [False, True])
def test_late_failure_preserves_terminal_task_and_run(monkeypatch, state, terminal):
    task, run, action, job = objects = context()
    task.status = run.status = state
    monkeypatch.setattr(
        research_tools, "_locked_tool_context", AsyncMock(return_value=objects)
    )
    event = AsyncMock()
    monkeypatch.setattr(research_tools, "emit_research_event", event)
    asyncio.run(
        research_tools.mark_research_tool_job_failure(
            AsyncMock(),
            tool_job_id=job.id,
            error="late provider failure",
            terminal=terminal,
        )
    )
    assert task.status == run.status == state
    assert job.status == "cancelled"
    event.assert_not_awaited()


@pytest.mark.parametrize("state", ["completed", "failed", "cancelled"])
def test_duplicate_failure_is_idempotent(monkeypatch, state):
    objects = context()
    objects[3].status = state
    monkeypatch.setattr(
        research_tools, "_locked_tool_context", AsyncMock(return_value=objects)
    )
    asyncio.run(
        research_tools.mark_research_tool_job_failure(
            AsyncMock(), tool_job_id=objects[3].id, error="late failure", terminal=True
        )
    )
    assert objects[3].status == state
    assert objects[2].revision == 1


def test_deferred_work_does_not_exhaust_single_attempt():
    job = SimpleNamespace(
        status="running",
        lease_owner="worker",
        attempts=1,
        lease_expires_at=datetime.now(UTC) + timedelta(seconds=60),
    )
    asyncio.run(defer_job(AsyncMock(), job=job, worker_id="worker", reason="paused"))
    assert job.status == "pending" and job.attempts == 0
    assert job.lease_owner is None and job.lease_expires_at is None
    assert job.available_at > datetime.now(UTC)


def test_expired_deadline_stops_before_authorization_or_provider(monkeypatch):
    task, run, action, job = context()
    task.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
    monkeypatch.setattr(research_tools, "emit_research_event", AsyncMock())
    db = AsyncMock()
    with pytest.raises(JobDeferred, match="time limit"):
        asyncio.run(
            research_tools._check_tool_dispatch(
                db, task=task, run=run, action=action, tool_job=job
            )
        )
    db.get.assert_not_awaited()
    assert task.status == run.status == "paused"
    assert task.outcome == "stopped_time"


def test_revoked_permission_pauses_without_tool_access(monkeypatch):
    task, run, action, job = context()
    db = AsyncMock()
    db.get.side_effect = [
        SimpleNamespace(id=task.owner_user_id),
        SimpleNamespace(lab_id=task.lab_id, deleted_at=None),
    ]
    monkeypatch.setattr(
        research_tools, "has_research_capability", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(research_tools, "emit_research_event", AsyncMock())
    with pytest.raises(JobDeferred, match="permission was revoked"):
        asyncio.run(
            research_tools._check_tool_dispatch(
                db, task=task, run=run, action=action, tool_job=job
            )
        )
    assert task.status == run.status == "paused"


@pytest.mark.parametrize("approved", [True, False])
def test_aira_dispatch_requires_exact_approval_or_automatic_authority(
    monkeypatch, approved
):
    task, run, action, job = context()
    run.environment_snapshot = {"tools": [{"key": "knowledge.search", "version": "1"}]}
    action.input_data = {"source": "aira"}
    db = AsyncMock()
    db.get.side_effect = [
        SimpleNamespace(id=task.owner_user_id),
        SimpleNamespace(lab_id=task.lab_id, deleted_at=None),
    ]
    db.scalar.return_value = uuid4() if approved else None
    monkeypatch.setattr(
        research_tools, "has_research_capability", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(research_tools, "emit_research_event", AsyncMock())
    dispatch = research_tools._check_tool_dispatch(
        db, task=task, run=run, action=action, tool_job=job
    )
    if approved:
        assert asyncio.run(dispatch).key == "knowledge.search"
        assert task.status == "active"
    else:
        with pytest.raises(
            JobDeferred, match="Assisted Research requires confirmation"
        ):
            asyncio.run(dispatch)
        assert task.status == "paused"
