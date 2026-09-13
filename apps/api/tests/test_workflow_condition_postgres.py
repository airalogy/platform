"""Real conditional Workflow execution from pinned synthetic Record receipts.

No condition decisions, joins, permissions, SQL or approval transitions are
mocked. Invalid legacy Record values and an executor failure are explicitly
injected where named, solely to verify fail-closed recovery in the test database.
"""

from __future__ import annotations

import asyncio
import copy
import os
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError

from app.config import config
from app.models.record import Record
from app.models.research import (
    ResearchAction,
    ResearchApproval,
    ResearchEvent,
    ResearchHumanWorkItem,
    ResearchRun,
    ResearchTask,
)
from app.models.resource import PersistentJob
from app.models.workflow_definition import WorkflowDefinition, WorkflowNodeResolution
from app.routers import research_tasks
from app.services.analysis_engine import canonical_digest
from app.services.research_runtime import hold_or_release_aira_action_group
from app.services.workflow_resolutions import verify_resolution_seal
from tests.test_record_analysis_postgres import add_record, database, seed_analysis
from tests.test_workflow_definitions_postgres import (
    actions_by_node,
    create_task,
    draft,
    edge,
    node,
    preview,
    publish,
    start_workflow,
    submit_record,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("RESOURCE_TEST_DATABASE_URL"),
    reason="Use pnpm research:integration with the isolated migrated PostgreSQL runtime",
)


@pytest.fixture(autouse=True)
def deterministic_no_ai(monkeypatch):
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")
    monkeypatch.setattr(config, "AI_ENABLED", False)


def conditional(source="first", target="next", **changes):
    condition = {
        "path": ["var", "value"],
        "value_type": "number",
        "operator": "gt",
        "value": 5,
        "unit": "mg/L",
        **changes,
    }
    return {**edge(source, target), "condition": condition}


async def start(sessions, scope, *, names=None, edges=None):
    workflow, _ = await publish(
        sessions,
        scope,
        draft(
            scope,
            nodes=[node(scope, name) for name in names or ["first", "next"]],
            edges=edges or [conditional()],
        ),
    )
    task = await create_task(sessions, scope)
    started, _ = await start_workflow(sessions, scope, workflow, task)
    return started, await actions_by_node(sessions, started["run_id"])


async def resolution(sessions, action_id):
    async with sessions() as db:
        row = await db.scalar(
            select(WorkflowNodeResolution).where(
                WorkflowNodeResolution.action_id == action_id
            )
        )
        assert row is not None
        verify_resolution_seal(row)
        return row


async def assert_no_dispatch(sessions, action_id):
    async with sessions() as db:
        assert (
            await db.scalar(
                select(ResearchHumanWorkItem.id).where(
                    ResearchHumanWorkItem.action_id == action_id
                )
            )
            is None
        )
        assert (
            await db.scalar(
                select(ResearchApproval.id).where(
                    ResearchApproval.action_id == action_id
                )
            )
            is None
        )


async def assert_run(sessions, run_id, status):
    async with sessions() as db:
        run = await db.get(ResearchRun, UUID(str(run_id)))
        assert run.status == status
        assert (await db.get(ResearchTask, run.task_id)).status == "review_required"
        assert run.result_package["narrative_conclusion"] == ""
        assert (
            await db.scalar(
                select(func.count())
                .select_from(PersistentJob)
                .where(
                    PersistentJob.kind == "research_run_advance",
                    PersistentJob.idempotency_key.like(f"research-run:{run.id}:%"),
                )
            )
            == 0
        )


@pytest.mark.parametrize(
    "observed,selected", [(6, True), (5, False), (0, False), (-1, False)]
)
def test_actual_condition_decision_uses_pinned_record_value_before_dispatch(
    observed, selected
):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            started, actions = await start(sessions, scope)
            source = await add_record(sessions, scope, observed)
            await submit_record(sessions, scope, actions["first"].id, source)
            rows = await actions_by_node(sessions, started["run_id"])
            resolved = await resolution(sessions, actions["next"].id)
            assert resolved.state == ("ready" if selected else "branch_not_selected")
            assert resolved.receipt["sources"]["first"]["record_id"] == str(source.id)
            assert resolved.receipt["sources"]["first"]["record_version"] == 1
            assert resolved.receipt["sources"]["first"]["record_hash"] == source.hash
            assert resolved.receipt["edges"][0]["observed_value"] == observed
            assert resolved.receipt["edges"][0]["outcome"] == (
                "active" if selected else "inactive"
            )
            assert resolved.receipt["error"] is None
            if selected:
                assert rows["next"].status == "proposed"
                await submit_record(
                    sessions,
                    scope,
                    actions["next"].id,
                    await add_record(sessions, scope, 10, number=2),
                )
            else:
                assert rows["next"].status == "skipped"
                assert rows["next"].error is None
                await assert_no_dispatch(sessions, actions["next"].id)
            await assert_run(sessions, started["run_id"], "completed")

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "changes",
    [{"path": ["var", "missing"]}, {"value_type": "integer"}, {"unit": "g/L"}],
)
def test_unknown_condition_fields_types_or_units_are_rejected_before_publication(
    changes,
):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            with pytest.raises(HTTPException) as error:
                await preview(
                    sessions,
                    scope,
                    draft(
                        scope,
                        nodes=[node(scope), node(scope, "next")],
                        edges=[conditional(**changes)],
                    ),
                )
            assert error.value.status_code == 422
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(WorkflowDefinition)
                        .where(WorkflowDefinition.project_id == scope.project.id)
                    )
                    == 0
                )

    asyncio.run(exercise())


@pytest.mark.parametrize("invalid", ["missing", "null", "string", "boolean"])
def test_invalid_legacy_source_value_fails_not_false_and_blocks_its_descendants(
    invalid,
):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            started, actions = await start(
                sessions,
                scope,
                names=["first", "next", "tail"],
                edges=[conditional(), edge("next", "tail")],
            )
            value = {"missing": 1, "null": None, "string": "10", "boolean": True}[
                invalid
            ]
            source = await add_record(sessions, scope, value)
            if invalid == "missing":
                # Explicit historical-data fault: the pinned variable is absent.
                async with sessions() as db:
                    data = {"var": {"group": "A"}}
                    await db.execute(
                        update(Record)
                        .where(Record.id == source.id, Record.version == source.version)
                        .values(data=data, hash=canonical_digest(data))
                    )
                    await db.commit()
            await submit_record(sessions, scope, actions["first"].id, source)
            failed = await resolution(sessions, actions["next"].id)
            blocked = await resolution(sessions, actions["tail"].id)
            assert failed.state == "failed"
            assert failed.receipt["edges"][0]["outcome"] == "failed"
            assert failed.receipt["error"]
            assert blocked.state == "blocked"
            assert blocked.receipt["edges"][0]["outcome"] == "failed"
            rows = await actions_by_node(sessions, started["run_id"])
            assert rows["next"].status == "failed" and rows["next"].error
            assert rows["tail"].status == "skipped" and rows["tail"].error
            for name in ["next", "tail"]:
                await assert_no_dispatch(sessions, actions[name].id)
            await assert_run(sessions, started["run_id"], "failed")

    asyncio.run(exercise())


def test_false_condition_propagates_non_failure_skip_through_multiple_nodes():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            started, actions = await start(
                sessions,
                scope,
                names=["first", "next", "tail", "last"],
                edges=[conditional(), edge("next", "tail"), edge("tail", "last")],
            )
            source = await add_record(sessions, scope, 1)
            await submit_record(sessions, scope, actions["first"].id, source)
            for name in ["next", "tail", "last"]:
                row = await resolution(sessions, actions[name].id)
                assert row.state == "branch_not_selected"
                assert row.receipt["join"]["state"] == "branch_not_selected"
                assert row.receipt["error"] is None
                await assert_no_dispatch(sessions, actions[name].id)
            await assert_run(sessions, started["run_id"], "completed")

    asyncio.run(exercise())


def test_diamond_join_waits_for_selected_branch_and_ignores_only_proven_false_branch():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            started, actions = await start(
                sessions,
                scope,
                names=["first", "yes", "no", "join"],
                edges=[
                    conditional(target="yes"),
                    conditional(target="no", operator="lte"),
                    edge("yes", "join"),
                    edge("no", "join"),
                ],
            )
            await submit_record(
                sessions,
                scope,
                actions["first"].id,
                await add_record(sessions, scope, 6, number=1),
            )
            rows = await actions_by_node(sessions, started["run_id"])
            assert rows["yes"].status == "proposed"
            assert rows["no"].status == "skipped" and rows["no"].error is None
            assert rows["join"].status == "blocked"
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(WorkflowNodeResolution.id).where(
                            WorkflowNodeResolution.action_id == actions["join"].id
                        )
                    )
                    is None
                )
            await submit_record(
                sessions,
                scope,
                actions["yes"].id,
                await add_record(sessions, scope, 7, number=2),
            )
            joined = await resolution(sessions, actions["join"].id)
            assert joined.state == "ready"
            assert joined.receipt["join"]["active_count"] == 1
            assert joined.receipt["join"]["inactive_count"] == 1
            assert joined.receipt["join"]["failed_count"] == 0
            assert set(joined.receipt["sources"]) == {"yes"}
            await submit_record(
                sessions,
                scope,
                actions["join"].id,
                await add_record(sessions, scope, 8, number=3),
            )
            await assert_run(sessions, started["run_id"], "completed")

    asyncio.run(exercise())


def test_join_with_no_selected_branch_skips_without_execution_failure():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            started, actions = await start(
                sessions,
                scope,
                names=["first", "a", "b", "join"],
                edges=[
                    conditional(target="a"),
                    conditional(target="b", value=10),
                    edge("a", "join"),
                    edge("b", "join"),
                ],
            )
            await submit_record(
                sessions,
                scope,
                actions["first"].id,
                await add_record(sessions, scope, 1),
            )
            resolved = await resolution(sessions, actions["join"].id)
            assert resolved.state == "branch_not_selected"
            assert resolved.receipt["join"]["inactive_count"] == 2
            await assert_no_dispatch(sessions, actions["join"].id)
            await assert_run(sessions, started["run_id"], "completed")

    asyncio.run(exercise())


@pytest.mark.parametrize("failure", ["approval_rejected", "executor_failed"])
def test_parent_failure_is_never_labeled_as_false_condition(failure):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            started, actions = await start(sessions, scope)
            async with sessions() as db:
                action = await db.get(ResearchAction, actions["first"].id)
                if failure == "approval_rejected":
                    approval = await db.scalar(
                        select(ResearchApproval).where(
                            ResearchApproval.action_id == action.id,
                            ResearchApproval.status == "pending",
                        )
                    )
                    await research_tasks.reject_research_action(
                        approval.id,
                        research_tasks.ApprovalRejectParams(
                            expected_revision=approval.revision,
                            expected_action_revision=action.revision,
                            preview_digest=approval.preview_digest,
                            reason="Synthetic operator declines experiment",
                        ),
                        scope.owner,
                        db,
                    )
                else:
                    # Explicit executor failure injection at the existing Action
                    # boundary; subsequent propagation uses the real resolver.
                    action.status = "failed"
                    action.error = "Synthetic executor could not complete"
                    action.completed_at = datetime.now(UTC)
                    action.revision += 1
                    await db.flush()
                    run = await db.get(ResearchRun, UUID(str(started["run_id"])))
                    task = await db.get(ResearchTask, run.task_id)
                    await hold_or_release_aira_action_group(
                        db, task=task, run=run, action=action
                    )
                    await db.commit()
            resolved = await resolution(sessions, actions["next"].id)
            assert resolved.state == "blocked"
            assert resolved.receipt["edges"][0]["outcome"] == (
                "cancelled" if failure == "approval_rejected" else "failed"
            )
            assert resolved.receipt["join"]["inactive_count"] == 0
            await assert_no_dispatch(sessions, actions["next"].id)
            await assert_run(sessions, started["run_id"], "failed")

    asyncio.run(exercise())


def test_record_revision_and_pause_resume_do_not_reinterpret_sealed_condition():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            started, actions = await start(sessions, scope)
            source = await add_record(sessions, scope, 6, number=1)
            await submit_record(sessions, scope, actions["first"].id, source)
            original = await resolution(sessions, actions["next"].id)
            receipt = copy.deepcopy(original.receipt)
            await add_record(
                sessions, scope, 0, record_id=source.id, revision=2, number=1
            )
            for operation in ["pause", "resume"]:
                async with sessions() as db:
                    run = await db.get(ResearchRun, UUID(str(started["run_id"])))
                    task = await db.get(ResearchTask, run.task_id)
                    await getattr(research_tasks, f"{operation}_research_task")(
                        task.id,
                        research_tasks.TaskTransitionParams(
                            expected_revision=task.revision,
                            reason="Synthetic recovery of the exact fixed decision",
                        ),
                        scope.owner,
                        db,
                    )
            restored = await resolution(sessions, actions["next"].id)
            assert (restored.id, restored.digest, restored.receipt) == (
                original.id,
                original.digest,
                receipt,
            )
            assert restored.state == "ready"
            assert restored.receipt["sources"]["first"]["record_version"] == 1
            assert restored.receipt["edges"][0]["observed_value"] == 6
            # Repeating an accepted receipt is read-only and cannot select v2.
            await submit_record(sessions, scope, actions["first"].id, source)
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(WorkflowNodeResolution)
                        .where(WorkflowNodeResolution.action_id == actions["next"].id)
                    )
                    == 1
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(ResearchEvent)
                        .where(
                            ResearchEvent.action_id == actions["next"].id,
                            ResearchEvent.kind == "workflow.node_resolved",
                        )
                    )
                    == 1
                )
            await submit_record(
                sessions,
                scope,
                actions["next"].id,
                await add_record(sessions, scope, 7, number=2),
            )
            await assert_run(sessions, started["run_id"], "completed")

    asyncio.run(exercise())


def test_condition_resolution_cannot_be_edited_in_database():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            started, actions = await start(sessions, scope)
            await submit_record(
                sessions,
                scope,
                actions["first"].id,
                await add_record(sessions, scope, 1),
            )
            original = await resolution(sessions, actions["next"].id)
            async with sessions() as db:
                with pytest.raises(DBAPIError, match="immutable"):
                    await db.execute(
                        update(WorkflowNodeResolution)
                        .where(WorkflowNodeResolution.id == original.id)
                        .values(state="ready")
                    )
                await db.rollback()
            stored = await resolution(sessions, actions["next"].id)
            assert stored.state == "branch_not_selected"
            assert stored.digest == original.digest
            await assert_run(sessions, started["run_id"], "completed")

    asyncio.run(exercise())
