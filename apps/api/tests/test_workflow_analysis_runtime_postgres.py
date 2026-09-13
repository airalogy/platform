"""Actual Record -> approved built-in Analysis -> Protocol, without AI or mocks."""

import asyncio
import json
from uuid import UUID

import pytest
from fastapi import HTTPException, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError

from app.models.analysis import AnalysisRun
from app.models.research import (
    ResearchApproval,
    ResearchHumanWorkItem,
    ResearchRun,
    ResearchTask,
)
from app.models.resource import PersistentJob
from app.models.workflow_analysis import ResearchAnalysisAction
from app.models.workflow_definition import WorkflowNodeResolution
from app.routers import analyses, research_tasks
from app.services.resource_job_worker import process_persistent_job
from app.services.workflow_definitions import WorkflowDraft
from tests.test_record_analysis_postgres import execute_job
from tests.test_workflow_analysis_methods_postgres import publish_method, saved_method
from tests.test_workflow_definitions_postgres import (
    actions_by_node,
    add_record,
    approve_action,
    create_task,
    database,
    edge,
    get,
    node,
    publish,
    seed_analysis,
    start_workflow,
    submit_record,
)
from tests.test_workflow_definitions_postgres import (
    deterministic_no_ai as deterministic_no_ai,
)
from tests.test_workflow_definitions_postgres import pytestmark as pytestmark


async def setup_analysis_workflow(
    sessions, scope, *, condition_threshold=None, exclude_first_source=False
):
    saved, original = await saved_method(sessions, scope)
    method, _ = await publish_method(sessions, scope, saved)
    workflow, _ = await publish(
        sessions,
        scope,
        WorkflowDraft(
            project_id=scope.project.id,
            title="Synthetic exact-source analysis workflow",
            graph={
                "schema_version": 2,
                "nodes": [
                    node(scope, "source_a"),
                    node(scope, "source_b"),
                    {
                        "node_id": "analysis",
                        "kind": "analysis",
                        "method_publication_id": method["id"],
                        "record_sources": [
                            {"source_node_id": source, "cardinality": "one"}
                            for source in ("source_a", "source_b")
                        ],
                        "input_policy": "all_declared",
                        "analysis_outputs": [
                            {
                                "output_id": "mean_value",
                                "field": "value",
                                "statistic": "mean",
                                "group": {},
                            }
                        ],
                    },
                    node(scope, "next"),
                ],
                "edges": [
                    edge("source_a", "analysis")
                    | (
                        {
                            "condition": {
                                "path": ["var", "value"],
                                "value_type": "number",
                                "unit": "mg/L",
                                "operator": "gt",
                                "value": 10,
                            }
                        }
                        if exclude_first_source
                        else {}
                    ),
                    edge("source_b", "analysis"),
                    edge("analysis", "next")
                    | (
                        {
                            "condition": {
                                "path": ["analysis", "mean_value"],
                                "value_type": "number",
                                "unit": "mg/L",
                                "operator": "gt",
                                "value": condition_threshold,
                            }
                        }
                        if condition_threshold is not None
                        else {}
                    ),
                ],
                "bindings": [
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
            },
        ),
    )
    started, _ = await start_workflow(
        sessions, scope, workflow, await create_task(sessions, scope)
    )
    actions = await actions_by_node(sessions, started["run_id"])
    records = []
    for name, value, number in [("source_a", 2, 2), ("source_b", 4, 3)]:
        record = await add_record(sessions, scope, value, number=number)
        records.append(record)
        await submit_record(sessions, scope, actions[name].id, record)
    return (
        workflow,
        started,
        await actions_by_node(sessions, started["run_id"]),
        records,
        original,
    )


async def queued_analysis(sessions, scope, actions):
    await approve_action(sessions, scope, actions["analysis"].id)
    async with sessions() as db:
        bridge = await db.get(ResearchAnalysisAction, actions["analysis"].id)
        assert bridge.analysis_run_id is not None
        return await db.get(AnalysisRun, bridge.analysis_run_id)


async def transition_task(sessions, scope, task_id, operation):
    async with sessions() as db:
        task = await db.get(ResearchTask, UUID(str(task_id)))
        return await getattr(research_tasks, f"{operation}_research_task")(
            task.id,
            research_tasks.TaskTransitionParams(
                expected_revision=task.revision, reason="Synthetic operator decision"
            ),
            scope.owner,
            db,
        )


def test_record_analysis_protocol_uses_only_declared_inputs_and_fresh_approval():
    async def exercise():
        async with database() as sessions:
            # Match production: implicit query-triggered flushes must not hide bugs.
            sessions.configure(autoflush=False)
            scope = await seed_analysis(sessions)
            (
                workflow,
                started,
                actions,
                records,
                original,
            ) = await setup_analysis_workflow(sessions, scope)
            action = actions["analysis"]
            assert action.kind == "analysis_run" and action.status == "proposed"
            async with sessions() as db:
                run = await db.get(ResearchRun, UUID(str(started["run_id"])))
                assert (
                    run.environment_snapshot["manual_workflow"][
                        "execution_contract_version"
                    ]
                    == 3
                )
                bridge = await db.get(ResearchAnalysisAction, action.id)
                assert (
                    bridge.analysis_run_id is None
                    and bridge.analysis_preview_id is None
                )
                assert {
                    item["record_id"] for item in bridge.input_snapshot["records"]
                } == {str(item.id) for item in records}
                assert str(original.id) not in json.dumps(bridge.input_snapshot)
                assert "8173.125" not in json.dumps(action.input_data)
                approval = await db.scalar(
                    select(ResearchApproval).where(
                        ResearchApproval.action_id == action.id,
                        ResearchApproval.status == "pending",
                    )
                )
                assert (
                    approval.preview_digest
                    == bridge.preview_digest
                    == action.preview_digest
                )
                # Only the original private method-creation analysis exists.
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisRun)
                        .where(AnalysisRun.project_id == scope.project.id)
                    )
                    == 1
                )
                with pytest.raises(DBAPIError):
                    await db.execute(
                        update(ResearchAnalysisAction)
                        .where(ResearchAnalysisAction.action_id == action.id)
                        .values(input_snapshot={})
                    )
                await db.rollback()
            analysis = await queued_analysis(sessions, scope, actions)
            assert analysis.status == "pending"
            await execute_job(sessions, analysis.as_dict())
            actions = await actions_by_node(sessions, started["run_id"])
            assert actions["analysis"].status == "completed"
            result = actions["analysis"].output_data["analysis_result"]
            assert result["outputs"] == {"analysis": {"mean_value": 3.0}}
            assert result["report"]["groups"][0]["fields"]["value"]["count"] == 2
            assert "8173.125" not in json.dumps(result)
            assert actions["next"].input_data["initial_values"] == {"value": 3.0}
            assert actions["next"].status == "proposed"
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(ResearchHumanWorkItem.id).where(
                            ResearchHumanWorkItem.action_id == actions["next"].id
                        )
                    )
                    is None
                )
                resolution = await db.scalar(
                    select(WorkflowNodeResolution).where(
                        WorkflowNodeResolution.action_id == actions["next"].id
                    )
                )
                assert resolution.receipt["sources"]["analysis"]["analysis_id"] == str(
                    analysis.id
                )
                # Redelivery reads the same sealed result, never creates another job.
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
            await submit_record(
                sessions,
                scope,
                actions["next"].id,
                await add_record(sessions, scope, 3, number=4),
            )
            async with sessions() as db:
                run = await db.get(ResearchRun, UUID(str(started["run_id"])))
                assert run.status == "completed"
                task = await db.get(ResearchTask, run.task_id)
                assert task.status != "completed"
            detail = await get(sessions, scope, workflow["id"])
            assert all(
                item["status"] == "completed" for item in detail["runs"][0]["actions"]
            )

    asyncio.run(exercise())


def test_analysis_report_acl_is_distinct_from_private_report_ownership():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions, public=True)
            _, started, actions, _, _ = await setup_analysis_workflow(sessions, scope)
            analysis = await queued_analysis(sessions, scope, actions)
            await execute_job(sessions, analysis.as_dict())
            async with sessions() as db:
                for user, private_link in ((scope.owner, True), (scope.analyst, False)):
                    view = jsonable_encoder(
                        await research_tasks.get_research_task(
                            UUID(str(started["task_id"])), user, db
                        )
                    )
                    card = next(
                        item
                        for item in view["actions"]
                        if item["id"] == str(actions["analysis"].id)
                    )
                    assert (
                        card["output_data"]["analysis_result"]["outputs"]["analysis"][
                            "mean_value"
                        ]
                        == 3
                    )
                    assert (
                        card["analysis_run"]["can_open_private_report"] is private_link
                    )
                with pytest.raises(HTTPException) as private:
                    await analyses.get_record_analysis(
                        analysis.id, db, scope.analyst, Response()
                    )
                assert private.value.status_code == 404
                restricted = jsonable_encoder(
                    await research_tasks.get_research_task(
                        UUID(str(started["task_id"])), scope.recorder, db
                    )
                )
                card = next(
                    item
                    for item in restricted["actions"]
                    if item["id"] == str(actions["analysis"].id)
                )
                assert card["workflow_data_restricted"] is True
                assert card["output_data"] == {} and card["preview_digest"] == ""
                # Published port names are Project metadata; actual inputs/results are not.
                assert "analysis_input" not in card["input_data"]
                assert str(analysis.id) not in json.dumps(card["output_data"])

    asyncio.run(exercise())


@pytest.mark.parametrize("threshold,expected", [(2, "proposed"), (10, "skipped")])
def test_actual_analysis_output_drives_a_typed_condition(threshold, expected):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            _, started, actions, _, _ = await setup_analysis_workflow(
                sessions,
                scope,
                condition_threshold=threshold,
            )
            analysis = await queued_analysis(sessions, scope, actions)
            await execute_job(sessions, analysis.as_dict())
            latest = await actions_by_node(sessions, started["run_id"])
            assert latest["analysis"].output_data["analysis_result"]["outputs"] == {
                "analysis": {"mean_value": 3.0},
            }
            assert latest["next"].status == expected
            async with sessions() as db:
                receipt = await db.scalar(
                    select(WorkflowNodeResolution).where(
                        WorkflowNodeResolution.action_id == latest["next"].id,
                    )
                )
                assert receipt.receipt["sources"]["analysis"]["analysis_id"] == str(
                    analysis.id
                )
                assert receipt.state == (
                    "ready" if expected == "proposed" else "branch_not_selected"
                )
                assert (
                    await db.scalar(
                        select(ResearchHumanWorkItem.id).where(
                            ResearchHumanWorkItem.action_id == latest["next"].id,
                        )
                    )
                    is None
                )

    asyncio.run(exercise())


def test_unselected_declared_source_cannot_silently_reduce_analysis_sample():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            _, started, actions, _, _ = await setup_analysis_workflow(
                sessions,
                scope,
                exclude_first_source=True,
            )
            assert actions["analysis"].status == "failed"
            assert actions["next"].status == "skipped"
            async with sessions() as db:
                bridge = await db.get(ResearchAnalysisAction, actions["analysis"].id)
                assert bridge.analysis_run_id is None and bridge.source_digest is None
                receipt = await db.scalar(
                    select(WorkflowNodeResolution).where(
                        WorkflowNodeResolution.action_id == actions["analysis"].id,
                    )
                )
                assert "partial samples are forbidden" in receipt.receipt["error"]
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisRun)
                        .where(
                            AnalysisRun.project_id == scope.project.id,
                        )
                    )
                    == 1
                )
                assert (
                    await db.get(ResearchRun, UUID(str(started["run_id"])))
                ).status == "failed"

    asyncio.run(exercise())
