"""Actual Workflow/Compute transport and budget boundaries on migrated PostgreSQL.

Default results are labelled synthetic Runner receipts. The explicit OCI case
executes the published source with the existing isolated container engine.
"""

import asyncio
import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi import HTTPException, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from app.models.analysis import AnalysisRun
from app.models.project import ProjectRole, ProjectUser
from app.models.record import Record
from app.models.research import (
    ResearchAction,
    ResearchProtocolRun,
    ResearchTask,
)
from app.models.research_execution import ResearchBudgetEntry, ResearchComputeJob
from app.models.workflow_analysis import ResearchAnalysisAction
from app.routers import analysis_compute
from app.routers import research_compute_jobs as jobs
from app.routers import research_tasks as tasks
from app.services.analysis_compute_contracts import (
    AnalysisComputeCancel,
    AnalysisComputeDecision,
)
from app.services.workflow_definitions import WorkflowDraft
from tests.test_analysis_compute_runtime_postgres import (
    completion,
    download_and_start,
    execute_container,
    lease,
    submit_completion,
    upload,
)
from tests.test_record_analysis_postgres import add_record, database
from tests.test_workflow_analysis_runtime_postgres import transition_task
from tests.test_workflow_compute_methods_postgres import (
    compute_graph,
    compute_task,
    publish_compute_method,
    saved_compute_method,
)
from tests.test_workflow_definitions_postgres import (
    actions_by_node,
    approve_action,
    edge,
    node,
    publish,
    start_workflow,
    submit_record,
)
from tests.test_workflow_definitions_postgres import (
    deterministic_no_ai as deterministic_no_ai,
)
from tests.test_workflow_definitions_postgres import pytestmark as pytestmark


async def setup_compute_workflow(
    sessions, *, parallel=False, budget="1", after=True, real_engine=False
):
    f, saved, original = await saved_compute_method(sessions, real_engine=real_engine)
    method, _ = await publish_compute_method(
        sessions,
        f,
        saved,
        compute_result_schema={
            "type": "object",
            "properties": {
                "mean": {"type": "number", "unit": "mg/L"},
                "count": {"type": "integer"},
                "uid": {"type": "integer"},
            },
            "required": ["mean", "count", "uid"],
        },
    )
    graph = compute_graph(f, method)
    graph["nodes"][1]["compute_outputs"][0]["unit"] = "mg/L"
    if parallel:
        graph["nodes"].append({**graph["nodes"][1], "node_id": "analysis_b"})
        graph["edges"].append(edge("source", "analysis_b"))
    if after:
        graph["nodes"].append(node(f.scope, "next"))
        graph["edges"].append(edge("analysis", "next"))
        graph["bindings"].append(
            {
                "binding_id": "mean_input",
                "source_node_id": "analysis",
                "source_path": ["analysis", "mean_value"],
                "target_node_id": "next",
                "target_path": ["var", "value"],
                "value_type": "number",
                "unit": "mg/L",
                "cardinality": "one",
            }
        )
    workflow, _ = await publish(
        sessions,
        f.scope,
        WorkflowDraft(
            project_id=f.scope.project.id,
            title="Synthetic governed Compute graph",
            graph=graph,
        ),
    )
    task = await compute_task(
        sessions,
        f,
        compute_environment_revision_ids=[f.compute.revision.id],
        budget_limit=budget,
        budget_currency="USD",
    )
    started, _ = await start_workflow(sessions, f.scope, workflow, task)
    actions = await actions_by_node(sessions, started["run_id"])
    record = await add_record(sessions, f.scope, 9, author=f.scope.owner, number=5)
    await submit_record(sessions, f.scope, actions["source"].id, record)
    f.records = [record]
    return f, started, await actions_by_node(sessions, started["run_id"]), original


async def queued(sessions, f, actions, name="analysis"):
    await approve_action(sessions, f.scope, actions[name].id)
    async with sessions() as db:
        bridge = await db.get(ResearchAnalysisAction, actions[name].id)
        job = await db.scalar(
            select(ResearchComputeJob).where(
                ResearchComputeJob.analysis_run_id == bridge.analysis_run_id
            )
        )
        assert job.action_id is None and job.status == "queued"
        return job


async def ledger(sessions, task_id):
    async with sessions() as db:
        entries = list(
            (
                await db.scalars(
                    select(ResearchBudgetEntry).where(
                        ResearchBudgetEntry.task_id == UUID(str(task_id))
                    )
                )
            ).all()
        )
        return [(item.kind, item.amount) for item in entries]


def test_compute_workflow_uses_exact_inputs_one_approval_budget_and_governed_report():
    async def exercise():
        async with database() as sessions:
            sessions.configure(autoflush=False)
            f, started, actions, original = await setup_compute_workflow(sessions)
            assert actions["analysis"].status == "proposed"
            async with sessions() as db:
                bridge = await db.get(ResearchAnalysisAction, actions["analysis"].id)
                assert bridge.analysis_run_id is None
                assert str(original) not in json.dumps(actions["analysis"].input_data)
            job = await queued(sessions, f, actions)
            assert await ledger(sessions, started["task_id"]) == [
                ("reserve", Decimal("0.1"))
            ]
            delivery = await lease(sessions, f)
            assert delivery.job.analysis_id == str(job.analysis_run_id)
            await download_and_start(sessions, f, delivery)
            result = {
                "mean": 9.0,
                "count": 1,
                "uid": 65532,
            }  # Synthetic receiver receipt.
            payload = json.dumps(result).encode()
            await upload(sessions, f, delivery, payload)
            receipt = completion(delivery, result, payload)
            await submit_completion(sessions, f, delivery, receipt)
            await submit_completion(sessions, f, delivery, receipt)
            entries = await ledger(sessions, started["task_id"])
            assert len(entries) == 3 and {kind for kind, _ in entries} == {
                "reserve",
                "release",
                "expense",
            }
            assert dict(entries)["expense"] == Decimal("0.001666666666666667")
            refreshed = await actions_by_node(sessions, started["run_id"])
            assert (
                refreshed["analysis"].status == "completed"
                and refreshed["next"].status == "proposed"
            )
            async with sessions() as db:
                typed = await db.scalar(
                    select(ResearchProtocolRun).where(
                        ResearchProtocolRun.action_id == refreshed["next"].id
                    )
                )
                assert typed.initial_values == {"value": 9.0}
                detail = jsonable_encoder(
                    await tasks.get_research_task(
                        UUID(str(started["task_id"])), f.scope.owner, db
                    )
                )
                assert "computed_result" in json.dumps(detail)
                with pytest.raises(HTTPException) as restricted:
                    await tasks.download_workflow_analysis_output(
                        UUID(str(started["task_id"])),
                        actions["analysis"].id,
                        UUID(delivery.job.outputs[0].id),
                        f.scope.recorder,
                        db,
                    )
                assert restricted.value.status_code == 403
            async with sessions() as db:
                member = await db.scalar(
                    select(ProjectUser).where(
                        ProjectUser.project_id == f.scope.project.id,
                        ProjectUser.user_id == f.scope.recorder.id,
                    )
                )
                member.role = ProjectRole.COLLABORATOR
                await db.commit()
            async with sessions() as db:
                response = await tasks.download_workflow_analysis_output(
                    UUID(str(started["task_id"])),
                    actions["analysis"].id,
                    UUID(delivery.job.outputs[0].id),
                    f.scope.recorder,
                    db,
                )
                assert (
                    b"".join([chunk async for chunk in response.body_iterator])
                    == payload
                )
            async with sessions() as db:
                record = await db.get(Record, (f.records[0].id, f.records[0].version))
                record.deleted_at = datetime.now(UTC).replace(tzinfo=None)
                await db.commit()
            async with sessions() as db:
                with pytest.raises(HTTPException):
                    await tasks.download_workflow_analysis_output(
                        UUID(str(started["task_id"])),
                        actions["analysis"].id,
                        UUID(delivery.job.outputs[0].id),
                        f.scope.recorder,
                        db,
                    )

    asyncio.run(exercise())


def test_compute_workflow_queue_pause_resume_preserves_job_and_reserved_budget():
    async def exercise():
        async with database() as sessions:
            f, started, actions, _ = await setup_compute_workflow(
                sessions, budget="0.1"
            )
            job = await queued(sessions, f, actions)
            await transition_task(sessions, f.scope, started["task_id"], "pause")
            async with sessions() as db:
                assert (await jobs.lease_compute_job(f.token, db))["job"] is None
                assert (await db.get(ResearchComputeJob, job.id)).status == "queued"
            await transition_task(sessions, f.scope, started["task_id"], "resume")
            assert (await lease(sessions, f)).job.job_id == str(job.id)
            assert await ledger(sessions, started["task_id"]) == [
                ("reserve", Decimal("0.1"))
            ]

    asyncio.run(exercise())


def test_compute_workflow_running_cancel_rejects_late_receipt_and_holds_unknown_usage():
    async def exercise():
        async with database() as sessions:
            f, started, actions, _ = await setup_compute_workflow(sessions)
            job = await queued(sessions, f, actions)
            delivery = await lease(sessions, f)
            await download_and_start(sessions, f, delivery)
            await transition_task(sessions, f.scope, started["task_id"], "cancel")
            with pytest.raises(HTTPException):
                await upload(sessions, f, delivery, b"{}")
            async with sessions() as db:
                await jobs.acknowledge_compute_cancellation(
                    job.id,
                    jobs.RunnerCancelled(reason="Synthetic isolated process stopped"),
                    f.token,
                    delivery.token,
                    db,
                )
            assert await ledger(sessions, started["task_id"]) == [
                ("reserve", Decimal("0.1"))
            ]
            async with sessions() as db:
                assert (
                    await db.get(ResearchTask, UUID(str(started["task_id"])))
                ).status == "cancelled"
                assert (await db.get(ResearchComputeJob, job.id)).actual_cost is None

    asyncio.run(exercise())


def test_compute_workflow_parallel_approvals_share_task_budget_without_double_dispatch():
    async def exercise():
        async with database() as sessions:
            f, started, actions, _ = await setup_compute_workflow(
                sessions, parallel=True, budget="0.15"
            )
            await queued(sessions, f, actions)
            from app.routers import research_budget

            async with sessions() as db:
                task = await db.get(ResearchTask, UUID(str(started["task_id"])))
                params = research_budget.BudgetEntryDraft(
                    expected_task_revision=task.revision,
                    kind="release",
                    amount="0.1",
                    currency="USD",
                    description="Synthetic attempted manual release of automatic reservation",
                    idempotency_key="synthetic-manual-compute-release",
                )
                with pytest.raises(HTTPException, match="Manual releases"):
                    await research_budget.preview_budget_entry(
                        task.id, params, f.scope.owner, db
                    )
            async with sessions() as db:
                with pytest.raises(HTTPException, match="Manual releases"):
                    await research_budget.create_budget_entry(
                        task.id,
                        research_budget.BudgetEntryCreate(
                            **params.model_dump(), preview_digest="0" * 64
                        ),
                        f.scope.owner,
                        db,
                    )
            with pytest.raises(HTTPException) as over:
                await queued(sessions, f, actions, "analysis_b")
            assert over.value.status_code == 409
            assert await ledger(sessions, started["task_id"]) == [
                ("reserve", Decimal("0.1"))
            ]
            async with sessions() as db:
                bridge = await db.get(ResearchAnalysisAction, actions["analysis_b"].id)
                assert bridge.analysis_run_id is None

    asyncio.run(exercise())


def test_compute_workflow_private_approval_cancel_cannot_bypass_task_governance():
    async def exercise():
        async with database() as sessions:
            f, started, actions, _ = await setup_compute_workflow(sessions)
            job = await queued(sessions, f, actions)
            async with sessions() as db:
                detail = await analysis_compute.get_analysis_compute(
                    job.analysis_run_id, db, f.scope.owner, Response()
                )
                with pytest.raises(HTTPException) as bypass:
                    await analysis_compute.decide_analysis_compute(
                        job.analysis_run_id,
                        AnalysisComputeDecision(
                            decision="approved",
                            expected_revision=detail["approval"]["revision"],
                            contract_digest=detail["approval"]["contract_digest"],
                            reason="Synthetic alternate path",
                        ),
                        db,
                        f.scope.owner,
                        Response(),
                    )
                assert bypass.value.status_code == 409
            async with sessions() as db:
                with pytest.raises(HTTPException) as bypass:
                    await analysis_compute.cancel_analysis_compute(
                        job.analysis_run_id,
                        AnalysisComputeCancel(
                            expected_revision=job.revision,
                            contract_digest=detail["approval"]["contract_digest"],
                            reason="Synthetic alternate path",
                        ),
                        db,
                        f.scope.owner,
                        Response(),
                    )
                assert bypass.value.status_code == 409

    asyncio.run(exercise())


def test_exact_reserved_budget_executes_and_settles_without_new_dispatch_pause():
    async def exercise():
        async with database() as sessions:
            f, started, actions, _ = await setup_compute_workflow(
                sessions, budget="0.1", after=False
            )
            await queued(sessions, f, actions)
            delivery = await lease(sessions, f)
            await download_and_start(sessions, f, delivery)
            result = {"mean": 9, "count": 1, "uid": 65532}
            payload = json.dumps(result).encode()
            await upload(sessions, f, delivery, payload)
            receipt = completion(delivery, result, payload)
            receipt.usage.wall_seconds = 60
            await submit_completion(sessions, f, delivery, receipt)
            await submit_completion(sessions, f, delivery, receipt)
            assert dict(await ledger(sessions, started["task_id"]))[
                "expense"
            ] == Decimal("0.1")
            async with sessions() as db:
                task = await db.get(ResearchTask, UUID(str(started["task_id"])))
                assert task.status == "review_required"
                assert task.result_package

    asyncio.run(exercise())


def test_compute_source_revocation_prevents_actual_approval_and_runner_dispatch():
    async def exercise():
        async with database() as sessions:
            f, started, actions, _ = await setup_compute_workflow(sessions)
            async with sessions() as db:
                record = await db.get(Record, (f.records[0].id, f.records[0].version))
                record.deleted_at = datetime.now(UTC).replace(tzinfo=None)
                await db.commit()
            with pytest.raises(HTTPException):
                await queued(sessions, f, actions)
            async with sessions() as db:
                bridge = await db.get(ResearchAnalysisAction, actions["analysis"].id)
                assert bridge.analysis_run_id is None
                assert (await jobs.lease_compute_job(f.token, db))["job"] is None
            assert await ledger(sessions, started["task_id"]) == []

    asyncio.run(exercise())


@pytest.mark.parametrize("known_usage", [False, True])
@pytest.mark.parametrize("after", [False, True])
def test_paused_terminal_compute_settles_without_new_dispatch_when_budget_is_full(
    known_usage,
    after,
):
    async def exercise():
        async with database() as sessions:
            f, started, actions, _ = await setup_compute_workflow(
                sessions, budget="0.1", after=after
            )
            job = await queued(sessions, f, actions)
            delivery = await lease(sessions, f)
            await download_and_start(sessions, f, delivery)
            await transition_task(sessions, f.scope, started["task_id"], "pause")
            async with sessions() as db:
                await jobs.acknowledge_compute_cancellation(
                    job.id,
                    jobs.RunnerCancelled(
                        reason="Synthetic stopped process",
                        usage={"wall_seconds": 60, "output_bytes": 0}
                        if known_usage
                        else None,
                    ),
                    f.token,
                    delivery.token,
                    db,
                )
            async with sessions() as db:
                original_jobs = set(
                    (await db.scalars(select(ResearchComputeJob.id))).all()
                )
                task = await db.get(ResearchTask, UUID(str(started["task_id"])))
                assert task.status == "paused"
            await transition_task(sessions, f.scope, started["task_id"], "resume")
            async with sessions() as db:
                task = await db.get(ResearchTask, UUID(str(started["task_id"])))
                assert task.status == "review_required"
                assert task.result_package
                if after:
                    downstream = await db.get(ResearchAction, actions["next"].id)
                    assert downstream.status == "skipped"
                    assert (
                        downstream.input_data["workflow_resolution"]["state"]
                        == "blocked"
                    )
                assert (
                    set((await db.scalars(select(ResearchComputeJob.id))).all())
                    == original_jobs
                )
                assert (await jobs.lease_compute_job(f.token, db))["job"] is None
            values = dict(await ledger(sessions, started["task_id"]))
            assert values.get("expense") == (Decimal("0.1") if known_usage else None)
            assert ("release" in values) is known_usage

    asyncio.run(exercise())


def test_task_can_pin_enabled_historical_compute_revision_without_manage_capability():
    async def exercise():
        from app.models.research import ResearchTaskComputeEnvironment
        from app.models.research_execution import ResearchComputeEnvironmentRevision
        from app.routers import research_compute

        async with database() as sessions:
            f, _, _ = await saved_compute_method(sessions)
            async with sessions() as db:
                previous = await db.get(
                    ResearchComputeEnvironmentRevision, f.compute.revision.id
                )
                values = {
                    column.name: getattr(previous, column.name)
                    for column in ResearchComputeEnvironmentRevision.__table__.columns
                    if column.name not in {"id", "created_at", "revision"}
                }
                newer = ResearchComputeEnvironmentRevision(**values, revision=2)
                db.add(newer)
                member = await db.scalar(
                    select(ProjectUser).where(
                        ProjectUser.project_id == f.scope.project.id,
                        ProjectUser.user_id == f.scope.recorder.id,
                    )
                )
                member.role = ProjectRole.COLLABORATOR
                await db.commit()
            async with sessions() as db:
                result = await tasks.task_compute_environment_revisions(
                    f.scope.project.id, f.scope.recorder, db
                )
                assert {item["source_revision_id"] for item in result["items"]} == {
                    str(previous.id),
                    str(newer.id),
                }
                with pytest.raises(HTTPException) as no_manage:
                    await research_compute.list_compute_environment_revisions(
                        f.scope.lab.id, f.scope.recorder, db
                    )
                assert no_manage.value.status_code == 403
            task = await compute_task(
                sessions, f, compute_environment_revision_ids=[previous.id]
            )
            async with sessions() as db:
                pinned = await db.scalar(
                    select(ResearchTaskComputeEnvironment).where(
                        ResearchTaskComputeEnvironment.task_id == UUID(str(task["id"]))
                    )
                )
                assert pinned.compute_environment_revision_id == previous.id
            with pytest.raises(HTTPException) as duplicate:
                await compute_task(
                    sessions,
                    f,
                    compute_environment_ids=[f.compute.environment.id],
                    compute_environment_revision_ids=[previous.id],
                )
            assert duplicate.value.status_code == 422

    asyncio.run(exercise())


@pytest.mark.skipif(
    os.environ.get("COMPUTE_ENGINE_TEST") != "1",
    reason="Explicit isolated OCI execution opt-in required",
)
def test_workflow_compute_executes_published_python_against_only_its_upstream_record():
    async def exercise():
        async with database() as sessions:
            f, started, actions, _ = await setup_compute_workflow(
                sessions, real_engine=True, after=False
            )
            job = await queued(sessions, f, actions)
            delivery = await lease(sessions, f)
            inputs = await download_and_start(sessions, f, delivery)
            result, payload = execute_container(delivery, inputs)
            assert result == {"mean": 9.0, "count": 1, "uid": 65532}
            await upload(sessions, f, delivery, payload)
            await submit_completion(
                sessions, f, delivery, completion(delivery, result, payload)
            )
            async with sessions() as db:
                run = await db.get(AnalysisRun, job.analysis_run_id)
                assert run.result["computed_result"] == result
                assert (
                    await db.get(ResearchTask, UUID(str(started["task_id"])))
                ).status == "review_required"

    asyncio.run(exercise())
