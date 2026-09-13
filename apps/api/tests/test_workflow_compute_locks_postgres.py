"""Real Runner/cancellation lock ordering, without executing scientific code."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import event, select, update

from app.models.analysis import AnalysisRun
from app.models.analysis_compute import AnalysisCompute
from app.models.research import ResearchTask
from app.models.research_execution import ResearchComputeJob, ResearchComputeRunner
from app.routers import analysis_compute as private_compute
from app.routers import research_compute_jobs as jobs
from app.routers import research_tasks as tasks
from app.services import workflow_analysis_runtime
from app.services.analysis_compute_contracts import AnalysisComputeCancel
from app.services.research_compute_jobs import compute_lease_token_digest
from tests.test_analysis_compute_runtime_postgres import confirmed as confirm_private
from tests.test_analysis_compute_runtime_postgres import download_and_start, lease
from tests.test_analysis_compute_runtime_postgres import fixture as private_fixture
from tests.test_record_analysis_postgres import database
from tests.test_workflow_compute_runtime_postgres import queued, setup_compute_workflow
from tests.test_workflow_definitions_postgres import (
    deterministic_no_ai as deterministic_no_ai,
)
from tests.test_workflow_definitions_postgres import pytestmark as pytestmark


@pytest.mark.parametrize("operation", ["request", "queue_delivery", "expired_recovery"])
def test_runner_never_holds_job_while_waiting_for_task_cancellation(
    monkeypatch, operation
):
    async def exercise():
        async with database() as sessions:
            f, started, actions, _ = await setup_compute_workflow(sessions)
            job = await queued(sessions, f, actions)
            delivery = None
            if operation != "queue_delivery":
                delivery = await lease(sessions, f)
                await download_and_start(sessions, f, delivery)
            if operation == "expired_recovery":
                async with sessions() as db:
                    await db.execute(
                        update(ResearchComputeJob)
                        .where(ResearchComputeJob.id == job.id)
                        .values(
                            lease_expires_at=datetime.now(UTC) - timedelta(seconds=60)
                        )
                    )
                    await db.commit()
            entered = asyncio.Event()
            actual_context = workflow_analysis_runtime.workflow_analysis_context

            async def observed_context(db, analysis_id, **kwargs):
                if analysis_id == job.analysis_run_id:
                    entered.set()
                return await actual_context(db, analysis_id, **kwargs)

            monkeypatch.setattr(
                workflow_analysis_runtime, "workflow_analysis_context", observed_context
            )

            async def runner_request():
                async with sessions() as db:
                    if operation == "request":
                        return await jobs.heartbeat_compute_job(
                            job.id, f.token, delivery.token, db
                        )
                    return await jobs.lease_compute_job(f.token, db)

            async with sessions() as cancelling:
                task = await cancelling.scalar(
                    select(ResearchTask)
                    .where(ResearchTask.id == UUID(str(started["task_id"])))
                    .with_for_update()
                )
                request = asyncio.create_task(runner_request())
                try:
                    await asyncio.wait_for(entered.wait(), timeout=10)
                    await asyncio.wait_for(
                        tasks.cancel_research_task(
                            task.id,
                            tasks.TaskTransitionParams(
                                expected_revision=task.revision,
                                reason="Cancel while Runner waits at the governed boundary",
                            ),
                            f.scope.owner,
                            cancelling,
                        ),
                        timeout=10,
                    )
                finally:
                    if cancelling.in_transaction():
                        await cancelling.rollback()
                response = await asyncio.wait_for(request, timeout=10)
            async with sessions() as db:
                current = await db.get(ResearchComputeJob, job.id)
                task = await db.get(ResearchTask, UUID(str(started["task_id"])))
                assert task.status == "cancelled"
                assert current.status == (
                    "cancelled" if operation == "queue_delivery" else "cancel_requested"
                )
            if operation == "request":
                assert response["cancel_requested"] is True
            else:
                assert response["job"] is None

    asyncio.run(exercise())


def test_runner_request_rechecks_lease_after_waiting_for_parent(monkeypatch):
    async def exercise():
        async with database() as sessions:
            f, started, actions, _ = await setup_compute_workflow(sessions)
            job = await queued(sessions, f, actions)
            delivery = await lease(sessions, f)
            entered = asyncio.Event()
            actual_context = workflow_analysis_runtime.workflow_analysis_context

            async def observed_context(db, analysis_id, **kwargs):
                if analysis_id == job.analysis_run_id:
                    entered.set()
                return await actual_context(db, analysis_id, **kwargs)

            monkeypatch.setattr(
                workflow_analysis_runtime, "workflow_analysis_context", observed_context
            )

            async def stale_request():
                async with sessions() as db:
                    runner = await db.get(ResearchComputeRunner, f.compute.runner.id)
                    with pytest.raises(HTTPException) as rejected:
                        await jobs._runner_job_context(
                            db, runner=runner, job_id=job.id, lease_token=delivery.token
                        )
                    assert rejected.value.status_code == 401
                    await db.rollback()

            async with sessions() as owner:
                await owner.scalar(
                    select(ResearchTask)
                    .where(ResearchTask.id == UUID(str(started["task_id"])))
                    .with_for_update()
                )
                request = asyncio.create_task(stale_request())
                await asyncio.wait_for(entered.wait(), timeout=10)
                await asyncio.wait_for(
                    owner.execute(
                        update(ResearchComputeJob)
                        .where(ResearchComputeJob.id == job.id)
                        .values(
                            lease_token_digest=compute_lease_token_digest(
                                "replacement-synthetic-lease"
                            )
                        )
                    ),
                    timeout=10,
                )
                await owner.commit()
                await asyncio.wait_for(request, timeout=10)
            async with sessions() as db:
                current = await db.get(ResearchComputeJob, job.id)
                assert current.status == "leased" and current.started_at is None

    asyncio.run(exercise())


def test_private_analysis_cancel_and_runner_use_analysis_before_job():
    async def exercise():
        async with database() as sessions:
            f = await private_fixture(sessions)
            analysis_id = await confirm_private(sessions, f)
            delivery = await lease(sessions, f)
            await download_and_start(sessions, f, delivery)
            job_id = UUID(delivery.job.job_id)
            async with sessions() as db:
                job = await db.get(ResearchComputeJob, job_id)
                details = await db.get(AnalysisCompute, analysis_id)
                params = AnalysisComputeCancel(
                    expected_revision=job.revision,
                    contract_digest=details.contract_digest,
                    reason="Cancel during a concurrent private Runner heartbeat",
                )
            entered = asyncio.Event()

            async def cancel():
                async with sessions() as db:
                    connection = (await db.connection()).sync_connection

                    def observe(
                        _connection,
                        _cursor,
                        statement,
                        _parameters,
                        _context,
                        _executemany,
                    ):
                        if "FOR UPDATE" in statement and (
                            "analysis_runs" in statement
                            or "research_compute_jobs" in statement
                        ):
                            entered.set()

                    event.listen(connection, "before_cursor_execute", observe)
                    try:
                        return await private_compute.cancel_analysis_compute(
                            analysis_id, params, db, f.scope.analyst, Response()
                        )
                    finally:
                        event.remove(connection, "before_cursor_execute", observe)

            async with sessions() as runner_db:
                await runner_db.scalar(
                    select(AnalysisRun)
                    .where(AnalysisRun.id == analysis_id)
                    .with_for_update()
                )
                cancellation = asyncio.create_task(cancel())
                try:
                    await asyncio.wait_for(entered.wait(), timeout=10)
                    # Old cancellation held Job while waiting for this Analysis;
                    # the actual Runner request would then wait in the other direction.
                    heartbeat = await asyncio.wait_for(
                        jobs.heartbeat_compute_job(
                            job_id, f.token, delivery.token, runner_db
                        ),
                        timeout=10,
                    )
                    assert heartbeat["status"] == "running"
                finally:
                    if runner_db.in_transaction():
                        await runner_db.rollback()
                receipt = await asyncio.wait_for(cancellation, timeout=10)
                assert receipt["status"] == "cancel_requested"
            async with sessions() as db:
                assert (
                    await db.get(ResearchComputeJob, job_id)
                ).status == "cancel_requested"

    asyncio.run(exercise())
