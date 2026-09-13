"""Pure lock-contract checks; concurrent PostgreSQL tests cover real waiting."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.models.analysis import AnalysisRun
from app.models.research import ResearchAction, ResearchRun, ResearchTask
from app.models.research_execution import ResearchComputeJob
from app.routers import research_compute_jobs as routes
from app.services import workflow_analysis_runtime
from app.services.persistent_jobs import JobDeferred
from app.services.research_compute_jobs import compute_lease_token_digest


class ContextDB:
    def __init__(self, *, analysis):
        self.task = SimpleNamespace(id=uuid4(), status="active")
        self.run = SimpleNamespace(
            id=uuid4(), task_id=self.task.id, status="waiting_for_compute"
        )
        self.action = SimpleNamespace(id=uuid4(), run_id=self.run.id, status="queued")
        self.analysis = SimpleNamespace(id=uuid4())
        self.job = SimpleNamespace(
            id=uuid4(),
            action_id=None if analysis else self.action.id,
            analysis_run_id=self.analysis.id if analysis else None,
        )
        self.rows = {
            ResearchTask: self.task,
            ResearchRun: self.run,
            ResearchAction: self.action,
            AnalysisRun: self.analysis,
            ResearchComputeJob: self.job,
        }
        self.locked = []
        self.sql = []
        self.unavailable = None

    async def get(self, model, _id):
        return self.rows.get(model)

    async def scalar(self, statement):
        model = statement.column_descriptions[0]["entity"]
        self.locked.append(model)
        self.sql.append(str(statement.compile(dialect=postgresql.dialect())))
        return None if model is self.unavailable else self.rows[model]


@pytest.mark.parametrize("skip_locked", [False, True])
def test_workflow_analysis_context_precedes_analysis_and_job_locks(
    monkeypatch, skip_locked
):
    async def exercise():
        db = ContextDB(analysis=True)

        async def context(_db, analysis_id, **kwargs):
            assert analysis_id == db.analysis.id
            assert db.locked == []
            assert kwargs == {"skip_locked": skip_locked}
            db.locked.extend([ResearchTask, ResearchRun, ResearchAction])

        monkeypatch.setattr(
            workflow_analysis_runtime, "workflow_analysis_context", context
        )
        result = await routes._lock_compute_job_context(
            db, db.job, skip_locked=skip_locked
        )
        assert result == (db.job, None, db.analysis, None)
        assert db.locked == [
            ResearchTask,
            ResearchRun,
            ResearchAction,
            AnalysisRun,
            ResearchComputeJob,
        ]
        assert all(("SKIP LOCKED" in sql) is skip_locked for sql in db.sql)

    asyncio.run(exercise())


def test_regular_compute_uses_the_same_parent_first_order():
    async def exercise():
        db = ContextDB(analysis=False)
        assert await routes._lock_compute_job_context(db, db.job) == (
            db.job,
            db.action,
            db.run,
            db.task,
        )
        assert db.locked == [
            ResearchTask,
            ResearchRun,
            ResearchAction,
            ResearchComputeJob,
        ]

    asyncio.run(exercise())


def test_skip_locked_parent_does_not_try_to_acquire_job(monkeypatch):
    async def exercise():
        db = ContextDB(analysis=True)
        db.unavailable = AnalysisRun
        monkeypatch.setattr(
            workflow_analysis_runtime,
            "workflow_analysis_context",
            AsyncMock(return_value=None),
        )
        with pytest.raises(JobDeferred):
            await routes._lock_compute_job_context(db, db.job, skip_locked=True)
        assert db.locked == [AnalysisRun]

    asyncio.run(exercise())


def test_runner_token_is_checked_again_after_parent_wait(monkeypatch):
    async def exercise():
        db = ContextDB(analysis=True)
        runner = SimpleNamespace(id=uuid4())
        db.job.runner_id = runner.id
        db.job.lease_token_digest = compute_lease_token_digest("original")
        db.scalars = AsyncMock(return_value=SimpleNamespace(first=lambda: db.job))

        async def changed_lease(_db, candidate):
            candidate.lease_token_digest = compute_lease_token_digest("replacement")
            return candidate, None, db.analysis, None

        monkeypatch.setattr(routes, "_lock_compute_job_context", changed_lease)
        with pytest.raises(HTTPException) as rejected:
            await routes._runner_job_context(
                db, runner=runner, job_id=db.job.id, lease_token="original"
            )
        assert rejected.value.status_code == 401

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "status,expected", [("active", False), ("paused", True), ("cancelled", True)]
)
def test_queued_workflow_pause_is_a_delivery_skip_not_analysis_failure(
    monkeypatch, status, expected
):
    async def exercise():
        db = ContextDB(analysis=True)
        db.task.status = status
        monkeypatch.setattr(
            workflow_analysis_runtime,
            "workflow_analysis_context",
            AsyncMock(return_value=(db.task, db.run, db.action, None)),
        )
        assert await routes._workflow_compute_delivery_paused(db, db.job) is expected

    asyncio.run(exercise())
