"""Real multi-Protocol method -> Workflow -> worker -> downstream Record."""

import asyncio
import json
import threading
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi import HTTPException, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select, update

from app.models.analysis import AnalysisRun
from app.models.record import Record
from app.models.research import ResearchRun, ResearchTask
from app.models.resource import PersistentJob
from app.models.workflow_analysis import ResearchAnalysisAction
from app.routers import analyses, research_tasks
from app.services import project_analysis_engine, record_analyses
from app.services.persistent_jobs import JobDeferred
from app.services.resource_job_worker import process_persistent_job
from app.services.workflow_definitions import WorkflowDraft
from tests.test_project_analyses_postgres import project_recipe, project_scope
from tests.test_record_analysis_postgres import add_record, database, execute_job
from tests.test_workflow_analysis_runtime_postgres import (
    queued_analysis,
    transition_task,
)
from tests.test_workflow_definitions_postgres import (
    actions_by_node,
    create_task,
    edge,
    node,
    publish,
    start_workflow,
    submit_record,
)
from tests.test_workflow_definitions_postgres import (
    deterministic_no_ai as deterministic_no_ai,  # noqa: PLC0414 -- pytest fixture registration
)
from tests.test_workflow_definitions_postgres import (
    pytestmark as pytestmark,  # noqa: PLC0414
)
from tests.test_workflow_project_methods_postgres import (
    publish_project_method,
    saved_project_method,
)


async def setup_project_workflow(
    sessions, fixture, *, report_only=False, relational=False
):
    scope = fixture.scope
    saved, original = await saved_project_method(
        sessions, fixture, recipe=project_recipe(relational=relational)
    )
    method, _ = await publish_project_method(sessions, fixture, saved)
    sources = [
        ("first_a", "first", scope, 6, "S1", 3),
        ("first_b", "first", scope, 8, "S2", 4),
        ("second_a", "second", fixture.second, 30, "S1", 3),
        ("second_b", "second", fixture.second, 50, "S2", 4),
    ]
    outputs = (
        []
        if report_only
        else [
            {
                "output_id": "mean_value",
                "source": {"kind": "join"}
                if relational
                else {"kind": "local", "slot_id": "first"},
                "field": "left_value" if relational else "value",
                "statistic": "mean",
                "group": {},
            }
        ]
    )
    graph = {
        "schema_version": 6,
        "nodes": [
            *[node(source, name) for name, _, source, *_ in sources],
            {
                "node_id": "analysis",
                "kind": "analysis",
                "analysis_kind": "project",
                "method_publication_id": method["id"],
                "record_sources": [
                    {"source_node_id": name, "slot_id": slot, "cardinality": "one"}
                    for name, slot, *_ in sources
                ],
                "input_policy": "all_declared",
                "project_outputs": outputs,
            },
            node(scope, "next"),
        ],
        "edges": [
            *[edge(name, "analysis") for name, *_ in sources],
            edge("analysis", "next"),
        ],
        "bindings": []
        if report_only
        else [
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
        ],
    }
    workflow, _ = await publish(
        sessions,
        scope,
        WorkflowDraft(
            project_id=scope.project.id,
            title="Synthetic cross-Protocol Workflow",
            graph=graph,
        ),
    )
    task = await create_task(
        sessions, scope, protocol_ids=[scope.protocol.id, fixture.second.protocol.id]
    )
    started, _ = await start_workflow(sessions, scope, workflow, task)
    actions = await actions_by_node(sessions, started["run_id"])
    records = []
    for name, _, source, value, group, number in sources:
        record = await add_record(sessions, source, value, group, number=number)
        records.append(record)
        await submit_record(sessions, source, actions[name].id, record)
    return (
        workflow,
        started,
        await actions_by_node(sessions, started["run_id"]),
        records,
        original,
    )


@pytest.mark.parametrize("report_only", [False, True, "join"])
def test_project_workflow_real_sources_approval_result_and_downstream_record(
    report_only,
):
    async def exercise():
        async with database() as sessions:
            sessions.configure(autoflush=False)
            fixture = await project_scope(sessions)
            scope = fixture.scope
            _, started, actions, records, original = await setup_project_workflow(
                sessions,
                fixture,
                report_only=report_only is True,
                relational=report_only == "join",
            )
            action = actions["analysis"]
            assert action.status == "proposed"
            async with sessions() as db:
                run = await db.get(ResearchRun, UUID(str(started["run_id"])))
                assert (
                    run.environment_snapshot["manual_workflow"][
                        "execution_contract_version"
                    ]
                    == 7
                )
                bridge = await db.get(ResearchAnalysisAction, action.id)
                assert bridge.analysis_run_id is None
                captured = {
                    row["record_id"]
                    for item in bridge.input_snapshot["inputs"]
                    for row in item["snapshot"]["records"]
                }
                assert captured == {str(record.id) for record in records}
                assert not captured & {str(record.id) for record in fixture.records}
                assert original["id"] not in json.dumps(action.input_data)
                inputs = action.input_data["analysis_input"]
                assert len(inputs["source_nodes"]) == 4
                assert {item["slot_id"] for item in inputs["source_nodes"]} == {
                    "first",
                    "second",
                }
                assert inputs["summary"]["source_scope"] == "project"
            analysis = await queued_analysis(sessions, scope, actions)
            assert analysis.source_scope == "project" and analysis.protocol_id is None
            await execute_job(sessions, analysis.as_dict())
            actions = await actions_by_node(sessions, started["run_id"])
            assert actions["analysis"].status == "completed"
            result = actions["analysis"].output_data["analysis_result"]
            reports = {
                item["slot_id"]: item["report"]
                for item in result["report"]["local_results"]
            }
            assert reports["first"]["groups"][0]["fields"]["value"]["mean"] == 7
            assert reports["second"]["groups"][0]["fields"]["value"]["mean"] == 40
            assert result["outputs"] == {
                "analysis": {} if report_only is True else {"mean_value": 7}
            }
            assert actions["next"].status == "proposed"
            if report_only is not True:
                assert actions["next"].input_data["initial_values"] == {"value": 7}
            async with sessions() as db:
                job = await db.get(PersistentJob, analysis.job_id)
                await process_persistent_job(db, job)
                await db.commit()
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisRun)
                        .where(AnalysisRun.project_id == scope.project.id)
                    )
                    == 2
                )
                # Shared Workflow reports do not grant another user's private run.
                with pytest.raises(HTTPException) as private:
                    await analyses.get_record_analysis(
                        analysis.id, db, scope.analyst, Response()
                    )
                assert private.value.status_code == 404
                detail = jsonable_encoder(
                    await research_tasks.get_research_task(
                        UUID(str(started["task_id"])), scope.analyst, db
                    )
                )
                card = next(
                    item for item in detail["actions"] if item["id"] == str(action.id)
                )
                assert (
                    card["output_data"]["analysis_result"]["report"] == result["report"]
                )
                assert card["analysis_run"]["can_open_private_report"] is False
            await submit_record(
                sessions,
                scope,
                actions["next"].id,
                await add_record(sessions, scope, 7, number=5),
            )
            async with sessions() as db:
                run = await db.get(ResearchRun, UUID(str(started["run_id"])))
                assert run.status == "completed"

    asyncio.run(exercise())


@pytest.mark.parametrize("interruption", ["pause", "source_deleted"])
def test_project_workflow_defers_and_resumes_same_job_after_pause_or_any_source_loss(
    interruption,
):
    async def exercise():
        async with database() as sessions:
            fixture = await project_scope(sessions)
            scope = fixture.scope
            _, started, actions, records, _ = await setup_project_workflow(
                sessions, fixture
            )
            analysis = await queued_analysis(sessions, scope, actions)
            if interruption == "pause":
                await transition_task(sessions, scope, started["task_id"], "pause")
            else:
                async with sessions() as db:
                    await db.execute(
                        update(Record)
                        .where(Record.id == records[-1].id)
                        .values(deleted_at=datetime.now(UTC).replace(tzinfo=None))
                    )
                    await db.commit()
            async with sessions() as db:
                with pytest.raises(JobDeferred):
                    await record_analyses.process_record_analysis(db, analysis.id)
                await db.commit()
            actions = await actions_by_node(sessions, started["run_id"])
            assert actions["analysis"].status != "completed"
            assert "analysis_result" not in actions["analysis"].output_data
            assert actions["next"].status != "completed"
            async with sessions() as db:
                inner = await db.get(AnalysisRun, analysis.id)
                assert inner.status == "pending"
                assert not inner.result
                assert (
                    await db.get(ResearchTask, UUID(str(started["task_id"])))
                ).status == "paused"
                if interruption == "source_deleted":
                    await db.execute(
                        update(Record)
                        .where(Record.id == records[-1].id)
                        .values(deleted_at=None)
                    )
                    await db.commit()
            await transition_task(sessions, scope, started["task_id"], "resume")
            assert (await execute_job(sessions, analysis.as_dict()))[
                "status"
            ] == "succeeded"
            async with sessions() as db:
                bridge = await db.get(ResearchAnalysisAction, actions["analysis"].id)
                assert bridge.analysis_run_id == analysis.id
                assert bridge.source_digest == analysis.source_digest

    asyncio.run(exercise())


def test_project_workflow_discards_late_real_result_after_task_cancel(monkeypatch):
    async def exercise():
        async with database() as sessions:
            fixture = await project_scope(sessions)
            _, started, actions, _, _ = await setup_project_workflow(sessions, fixture)
            analysis = await queued_analysis(sessions, fixture.scope, actions)
            entered, release = threading.Event(), threading.Event()
            compute = project_analysis_engine.compute_project_analysis

            def paused_real_compute(*args, **kwargs):
                entered.set()
                if not release.wait(30):
                    raise AssertionError(
                        "Synthetic Project cancellation barrier timed out"
                    )
                return compute(*args, **kwargs)

            monkeypatch.setattr(
                project_analysis_engine, "compute_project_analysis", paused_real_compute
            )
            worker = asyncio.create_task(execute_job(sessions, analysis.as_dict()))
            try:
                assert await asyncio.to_thread(entered.wait, 15)
                await asyncio.wait_for(
                    transition_task(
                        sessions, fixture.scope, started["task_id"], "cancel"
                    ),
                    timeout=15,
                )
            finally:
                release.set()
            result = await asyncio.wait_for(worker, timeout=20)
            assert result["status"] == "cancelled"
            actions = await actions_by_node(sessions, started["run_id"])
            assert actions["analysis"].status == actions["next"].status == "cancelled"
            assert not actions["analysis"].output_data.get("analysis_result")
            async with sessions() as db:
                assert (await db.get(AnalysisRun, analysis.id)).result is None

    asyncio.run(exercise())
