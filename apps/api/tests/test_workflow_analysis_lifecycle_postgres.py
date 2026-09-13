"""Real Workflow analysis pause/cancel/revocation boundaries, no alternate engine."""

import asyncio
import threading
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, update

from app.models.analysis import AnalysisRun
from app.models.record import Record
from app.models.research import (
    ResearchAction,
    ResearchApproval,
    ResearchHumanWorkItem,
    ResearchTask,
)
from app.models.resource import PersistentJob
from app.models.workflow_analysis import ResearchAnalysisAction
from app.routers import analyses
from app.routers import research_tasks as tasks
from app.services import record_analyses, workflow_analysis_runtime
from app.services.persistent_jobs import JobDeferred, enqueue_job
from app.services.resource_job_worker import (
    fail_record_analysis_job,
    reconcile_exhausted_jobs,
)
from tests.test_record_analysis_postgres import database, execute_job, seed_analysis
from tests.test_workflow_analysis_runtime_postgres import (
    queued_analysis,
    setup_analysis_workflow,
    transition_task,
)
from tests.test_workflow_definitions_postgres import (
    deterministic_no_ai as deterministic_no_ai,
)
from tests.test_workflow_definitions_postgres import pytestmark as pytestmark


def analysis_card(actions):
    return next(action for action in actions.values() if action.kind == "analysis_run")


def test_exhausted_orphan_analysis_job_is_settled_instead_of_deferred_forever():
    async def exercise():
        async with database() as sessions:
            async with sessions() as db:
                job = await enqueue_job(
                    db,
                    kind="record_analysis",
                    payload={"analysis_id": str(uuid4())},
                    idempotency_key=f"synthetic-orphan-analysis:{uuid4()}",
                    max_attempts=1,
                )
                job.status, job.attempts = "running", 1
                job.lease_owner = "synthetic-crashed-worker"
                job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=60)
                await db.commit()
                job_id = job.id
            async with sessions() as db:
                await reconcile_exhausted_jobs(db)
                await db.commit()
                job = await db.get(PersistentJob, job_id, populate_existing=True)
                assert (
                    job.status == "failed"
                    and job.lease_owner is None
                    and job.lease_expires_at is None
                )

    asyncio.run(exercise())


@pytest.mark.parametrize("recovery", ["exhausted", "worker_failure"])
def test_recovery_never_holds_job_while_waiting_for_concurrent_task_cancellation(
    monkeypatch, recovery
):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            _, started, actions, _, _ = await setup_analysis_workflow(sessions, scope)
            analysis = await queued_analysis(sessions, scope, actions)
            worker_id = "synthetic-failed-workflow-worker"
            async with sessions() as db:
                job = await db.get(PersistentJob, analysis.job_id)
                job.status = "running"
                job.attempts = job.max_attempts
                job.lease_owner = worker_id
                job.lease_expires_at = datetime.now(UTC) + timedelta(
                    seconds=-60 if recovery == "exhausted" else 60
                )
                await db.commit()
            entering_context = asyncio.Event()
            real_context = workflow_analysis_runtime.workflow_analysis_context

            async def observed_context(db, analysis_id, **kwargs):
                if analysis_id == analysis.id:
                    entering_context.set()
                return await real_context(db, analysis_id, **kwargs)

            monkeypatch.setattr(
                workflow_analysis_runtime, "workflow_analysis_context", observed_context
            )

            async def recover():
                async with sessions() as db:
                    if recovery == "exhausted":
                        await reconcile_exhausted_jobs(db)
                    else:
                        job = await db.get(PersistentJob, analysis.job_id)
                        await fail_record_analysis_job(
                            db,
                            job=job,
                            worker_id=worker_id,
                            error="Synthetic worker crashed",
                        )
                    await db.commit()

            async with sessions() as cancelling:
                task = await cancelling.scalar(
                    select(ResearchTask)
                    .where(ResearchTask.id == UUID(str(started["task_id"])))
                    .with_for_update()
                )
                recoverer = asyncio.create_task(recover())
                try:
                    await asyncio.wait_for(entering_context.wait(), timeout=10)
                    # If recovery took Job first, this real cancellation would
                    # wait for Job while recovery waits for this Task row.
                    await asyncio.wait_for(
                        tasks.cancel_research_task(
                            task.id,
                            tasks.TaskTransitionParams(
                                expected_revision=task.revision,
                                reason="Cancel while a failed worker is recovering",
                            ),
                            scope.owner,
                            cancelling,
                        ),
                        timeout=10,
                    )
                finally:
                    if cancelling.in_transaction():
                        await cancelling.rollback()
                await asyncio.wait_for(recoverer, timeout=10)
            async with sessions() as db:
                if recovery == "exhausted":
                    await reconcile_exhausted_jobs(db)
                    await db.commit()
                job = await db.get(
                    PersistentJob, analysis.job_id, populate_existing=True
                )
                stored = await db.get(AnalysisRun, analysis.id)
                action = await db.get(ResearchAction, analysis_card(actions).id)
                assert job.status == stored.status == action.status == "cancelled"
                assert stored.result is None

    asyncio.run(exercise())


def test_failed_worker_rechecks_lease_after_waiting_for_parent_lock(monkeypatch):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            _, started, actions, _, _ = await setup_analysis_workflow(sessions, scope)
            analysis = await queued_analysis(sessions, scope, actions)
            async with sessions() as db:
                job = await db.get(PersistentJob, analysis.job_id)
                job.status, job.lease_owner = "running", "stale-worker"
                job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=60)
                await db.commit()
            entered = asyncio.Event()
            real_context = workflow_analysis_runtime.workflow_analysis_context

            async def observed_context(db, analysis_id, **kwargs):
                entered.set()
                return await real_context(db, analysis_id, **kwargs)

            monkeypatch.setattr(
                workflow_analysis_runtime, "workflow_analysis_context", observed_context
            )

            async def fail_stale_worker():
                async with sessions() as db:
                    job = await db.get(PersistentJob, analysis.job_id)
                    with pytest.raises(ValueError, match="lease"):
                        await fail_record_analysis_job(
                            db,
                            job=job,
                            worker_id="stale-worker",
                            error="Stale failure must not settle a new owner",
                        )
                    await db.rollback()

            async with sessions() as winner:
                await winner.scalar(
                    select(ResearchTask)
                    .where(ResearchTask.id == UUID(str(started["task_id"])))
                    .with_for_update()
                )
                failed_worker = asyncio.create_task(fail_stale_worker())
                await asyncio.wait_for(entered.wait(), timeout=10)
                # The lease row must remain available while the worker waits for
                # Task; replacing its owner invalidates the stale failure report.
                await asyncio.wait_for(
                    winner.execute(
                        update(PersistentJob)
                        .where(PersistentJob.id == analysis.job_id)
                        .values(lease_owner="current-worker")
                    ),
                    timeout=10,
                )
                await winner.commit()
                await asyncio.wait_for(failed_worker, timeout=10)
            async with sessions() as db:
                job = await db.get(PersistentJob, analysis.job_id)
                assert job.status == "running" and job.lease_owner == "current-worker"
                assert (await db.get(AnalysisRun, analysis.id)).status == "pending"
                assert (
                    await db.get(ResearchAction, analysis_card(actions).id)
                ).status == "queued"

    asyncio.run(exercise())


def test_source_revocation_pauses_pending_analysis_without_replacing_sealed_inputs():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            _, started, actions, records, _ = await setup_analysis_workflow(
                sessions, scope
            )
            analysis = await queued_analysis(sessions, scope, actions)
            source = records[0]
            async with sessions() as db:
                await db.execute(
                    update(Record)
                    .where(Record.id == source.id, Record.version == source.version)
                    .values(deleted_at=datetime.now(UTC).replace(tzinfo=None))
                )
                await db.commit()
            async with sessions() as db:
                with pytest.raises(JobDeferred, match="authority"):
                    await record_analyses.process_record_analysis(db, analysis.id)
                await db.commit()
            async with sessions() as db:
                task = await db.get(ResearchTask, UUID(str(started["task_id"])))
                pending = await db.get(AnalysisRun, analysis.id)
                bridge = await db.get(ResearchAnalysisAction, analysis_card(actions).id)
                assert task.status == "paused" and pending.status == "pending"
                assert (
                    bridge.source_digest == analysis.source_digest
                    and pending.result is None
                )
                await db.execute(
                    update(Record)
                    .where(Record.id == source.id, Record.version == source.version)
                    .values(deleted_at=None)
                )
                await db.commit()
            await transition_task(sessions, scope, started["task_id"], "resume")
            assert (await execute_job(sessions, {"job_id": analysis.job_id}))[
                "status"
            ] == "succeeded"

    asyncio.run(exercise())


def test_queued_analysis_pause_resume_preserves_exact_input_and_same_execution():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            _, started, actions, _, _ = await setup_analysis_workflow(sessions, scope)
            analysis = await queued_analysis(sessions, scope, actions)
            await transition_task(sessions, scope, started["task_id"], "pause")
            async with sessions() as db:
                with pytest.raises(JobDeferred, match="paused"):
                    await record_analyses.process_record_analysis(db, analysis.id)
                await db.commit()
            async with sessions() as db:
                pending = await db.get(AnalysisRun, analysis.id)
                bridge = await db.get(ResearchAnalysisAction, analysis_card(actions).id)
                assert pending.status == "pending"
                assert bridge.analysis_run_id == analysis.id
                digest = bridge.source_digest
            await transition_task(sessions, scope, started["task_id"], "resume")
            result = await execute_job(sessions, {"job_id": analysis.job_id})
            assert result["status"] == "succeeded"
            async with sessions() as db:
                bridge = await db.get(ResearchAnalysisAction, analysis_card(actions).id)
                assert (
                    bridge.source_digest == digest
                    and bridge.analysis_run_id == analysis.id
                )
                action = await db.get(ResearchAction, bridge.action_id)
                assert action.status == "completed"

    asyncio.run(exercise())


def test_task_cancellation_discards_real_late_cpu_result_and_keeps_descendants_stopped(
    monkeypatch,
):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            _, started, actions, _, _ = await setup_analysis_workflow(sessions, scope)
            analysis = await queued_analysis(sessions, scope, actions)
            entered, release = threading.Event(), threading.Event()
            original_compute = record_analyses.compute_analysis

            def bounded_compute(*args, **kwargs):
                entered.set()
                if not release.wait(30):
                    raise AssertionError("Synthetic cancellation barrier timed out")
                return original_compute(*args, **kwargs)

            monkeypatch.setattr(record_analyses, "compute_analysis", bounded_compute)
            worker = asyncio.create_task(
                execute_job(sessions, {"job_id": analysis.job_id})
            )
            try:
                assert await asyncio.to_thread(entered.wait, 15)
                await asyncio.wait_for(
                    transition_task(sessions, scope, started["task_id"], "cancel"),
                    timeout=15,
                )
            finally:
                release.set()
            result = await asyncio.wait_for(worker, timeout=20)
            assert result["status"] == "cancelled"
            async with sessions() as db:
                persisted = await db.get(AnalysisRun, analysis.id)
                action = await db.get(ResearchAction, analysis_card(actions).id)
                task = await db.get(ResearchTask, UUID(str(started["task_id"])))
                assert persisted.status == action.status == task.status == "cancelled"
                assert (
                    persisted.result is None
                    and action.output_data.get("analysis_result") is None
                )
                downstream = [
                    item
                    for item in actions.values()
                    if item.kind == "protocol_run"
                    and item.id
                    not in {
                        actions[key].id
                        for key in ("source_a", "source_b")
                        if key in actions
                    }
                ]
                for child in downstream:
                    row = await db.get(ResearchAction, child.id)
                    if row.status != "completed":
                        assert row.status == "cancelled"
                        assert (
                            await db.scalar(
                                select(ResearchHumanWorkItem.id).where(
                                    ResearchHumanWorkItem.action_id == child.id
                                )
                            )
                            is None
                        )

    asyncio.run(exercise())


def test_private_analysis_cancel_cannot_bypass_governed_task_cancellation():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            _, _, actions, _, _ = await setup_analysis_workflow(sessions, scope)
            analysis = await queued_analysis(sessions, scope, actions)
            async with sessions() as db:
                with pytest.raises(HTTPException) as denied:
                    await analyses.cancel_record_analysis(analysis.id, db, scope.owner)
                assert denied.value.status_code == 409
                assert "Research Task cancellation" in denied.value.detail
                await db.rollback()
            async with sessions() as db:
                assert (await db.get(AnalysisRun, analysis.id)).status == "pending"

    asyncio.run(exercise())


def test_explicit_analysis_approver_cannot_read_or_approve_other_users_record_inputs():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions, public=True)
            _, started, actions, _, _ = await setup_analysis_workflow(sessions, scope)
            target = analysis_card(actions)
            async with sessions() as db:
                approval = await db.scalar(
                    select(ResearchApproval).where(
                        ResearchApproval.action_id == target.id,
                        ResearchApproval.status == "pending",
                    )
                )
                approval.approver_user_id = scope.recorder.id
                await db.commit()
                action = await db.get(ResearchAction, target.id)
                view = jsonable_encoder(
                    await tasks.get_research_approval(approval.id, scope.recorder, db)
                )
                assert view["workflow_data_restricted"] is True
                assert "analysis_input" not in view["action"]["input_data"]
                assert view["preview_digest"] == ""
                with pytest.raises(HTTPException) as denied:
                    await tasks.approve_research_action(
                        approval.id,
                        tasks.ApprovalDecisionParams(
                            expected_revision=approval.revision,
                            expected_action_revision=action.revision,
                            preview_digest=approval.preview_digest,
                            reason="Cannot approve unreadable upstream Record values",
                        ),
                        scope.recorder,
                        db,
                    )
                assert denied.value.status_code == 403
                await db.rollback()
            async with sessions() as db:
                bridge = await db.get(ResearchAnalysisAction, target.id)
                assert (
                    bridge.analysis_run_id is None
                    and bridge.analysis_preview_id is None
                )
                assert (
                    await db.get(ResearchTask, UUID(str(started["task_id"])))
                ).status == "active"

    asyncio.run(exercise())
