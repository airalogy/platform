"""Real PostgreSQL acceptance for versioned manual Workflow API handlers.

Use the dedicated migrated research-integration database. Asset access, pinning,
transaction locks, confirmation, materialization and receipts are not mocked.
Every fixture is synthetic; no model, instrument or paid service is called.
"""

from __future__ import annotations

import asyncio
import copy
import os
from importlib import import_module
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException, Response
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError

from app.config import config
from app.models.lab import LabUser
from app.models.project import ProjectRole, ProjectUser
from app.models.protocol_version import ProtocolVersion
from app.models.research import (
    ResearchAction,
    ResearchActionDependency,
    ResearchApproval,
    ResearchEvent,
    ResearchHumanWorkItem,
    ResearchPlanVersion,
    ResearchProtocolRun,
    ResearchRun,
    ResearchTask,
)
from app.models.resource import PersistentJob
from app.models.workflow_definition import (
    WorkflowDefinition,
    WorkflowRevision,
    WorkflowRunBinding,
)
from app.routers import (
    research_actions,
    research_compute_jobs,
    research_instrument_jobs,
    research_resources,
    research_service_jobs,
    research_tasks,
)
from app.routers import workflow_definitions as api
from app.services.research_runtime import hold_or_release_aira_action_group
from app.services.workflow_definitions import (
    WorkflowConfirm,
    WorkflowDraft,
    WorkflowRunConfirm,
    WorkflowRunDraft,
)
from tests.test_record_analysis_postgres import add_record, database, seed_analysis

pytestmark = pytest.mark.skipif(
    not os.environ.get("RESOURCE_TEST_DATABASE_URL"),
    reason="Use pnpm research:integration with the isolated migrated PostgreSQL runtime",
)


@pytest.fixture(autouse=True)
def deterministic_no_ai(monkeypatch):
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")
    monkeypatch.setattr(config, "AI_ENABLED", False)


def node(scope, node_id="first", **changes):
    return {
        "node_id": node_id,
        "kind": "protocol",
        "protocol_id": str(scope.protocol.id),
        "protocol_version_id": str(scope.version.id),
        **changes,
    }


def edge(source, target):
    return {
        "edge_id": f"{source}-to-{target}",
        "source_node_id": source,
        "target_node_id": target,
    }


def draft(scope, *, nodes=None, edges=None, bindings=None, **changes):
    return WorkflowDraft(
        project_id=scope.project.id,
        title="Synthetic repeatable measurement",
        description="User-confirmed fixed Protocol cards; AI is disabled.",
        graph={
            "schema_version": 1,
            "nodes": nodes or [node(scope)],
            "edges": edges or [],
            "bindings": bindings or [],
        },
        **changes,
    )


async def preview(sessions, scope, params=None, *, user=None):
    async with sessions() as db:
        return await api.preview_workflow(
            params or draft(scope), user or scope.owner, db
        )


def confirmation(params, preview_result, key=None):
    return WorkflowConfirm(
        **params.model_dump(),
        preview_digest=preview_result["preview_digest"],
        idempotency_key=key or uuid4(),
    )


async def confirm(sessions, scope, params, *, user=None):
    async with sessions() as db:
        return await api.confirm_workflow(params, user or scope.owner, db)


async def publish(sessions, scope, params=None):
    params = params or draft(scope)
    command = confirmation(params, await preview(sessions, scope, params))
    return await confirm(sessions, scope, command), command


async def get(sessions, scope, workflow_id, *, user=None):
    async with sessions() as db:
        response = Response()
        result = await api.get_workflow(
            UUID(str(workflow_id)), user or scope.owner, db, response
        )
        assert response.headers["Cache-Control"] == "private, no-store"
        return result


async def create_task(sessions, scope, *, user=None, protocol_ids=None):
    user = user or scope.owner
    params = research_tasks.ResearchTaskDraft(
        project_id=scope.project.id,
        title="Synthetic fixed Workflow execution",
        goal="Collect independently attributable Protocol Records",
        success_criteria=["Each occurrence has a distinct valid Record"],
        protocol_ids=protocol_ids or [scope.protocol.id],
    )
    async with sessions() as db:
        result = await research_tasks.preview_research_task(params, user, db)
        return await research_tasks.create_research_task(
            research_tasks.ResearchTaskCreate(
                **params.model_dump(), preview_digest=result["preview_digest"]
            ),
            user,
            db,
        )


async def start_workflow(sessions, scope, workflow, task, *, key=None, user=None):
    user = user or scope.owner
    workflow_id = UUID(str(workflow["id"]))
    params = WorkflowRunDraft(
        workflow_revision_id=workflow["current_revision"]["id"],
        task_id=task["id"],
        expected_task_revision=task["revision"],
    )
    async with sessions() as db:
        result = await api.preview_workflow_run(workflow_id, params, user, db)
    command = WorkflowRunConfirm(
        **params.model_dump(),
        preview_digest=result["preview_digest"],
        idempotency_key=key or uuid4(),
    )
    async with sessions() as db:
        started = await api.confirm_workflow_run(workflow_id, command, user, db)
    return started, command


async def actions_by_node(sessions, run_id):
    async with sessions() as db:
        actions = list(
            (
                await db.scalars(
                    select(ResearchAction).where(
                        ResearchAction.run_id == UUID(str(run_id))
                    )
                )
            ).all()
        )
        return {
            action.input_data["action_graph"]["node_id"]: action for action in actions
        }


async def submit_record(sessions, scope, action_id, record):
    await approve_action(sessions, scope, action_id)
    async with sessions() as db:
        item = await db.scalar(
            select(ResearchHumanWorkItem).where(
                ResearchHumanWorkItem.action_id == action_id
            )
        )
        assert item is not None
        assert item.assignee_user_id == scope.owner.id
        return await research_tasks.submit_research_work_item(
            item.id,
            research_tasks.WorkItemSubmitParams(
                expected_revision=item.revision,
                record_id=record.id,
                record_version=record.version,
                note="Synthetic independently performed measurement",
            ),
            scope.owner,
            db,
        )


async def approve_action(sessions, scope, action_id):
    async with sessions() as db:
        approval = await db.scalar(
            select(ResearchApproval).where(
                ResearchApproval.action_id == action_id,
                ResearchApproval.status == "pending",
            )
        )
        if approval is None:
            return
        action = await db.get(ResearchAction, action_id)
        return await research_tasks.approve_research_action(
            approval.id,
            research_tasks.ApprovalDecisionParams(
                expected_revision=approval.revision,
                expected_action_revision=action.revision,
                preview_digest=approval.preview_digest,
                reason="Explicit approval of this synthetic Protocol occurrence",
            ),
            scope.owner,
            db,
        )


def test_preview_is_read_only_and_confirmation_creates_versioned_project_asset():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            params = draft(scope, nodes=[node(scope, initial_values={"value": 3.5})])
            result = await preview(sessions, scope, params)
            assert result["pins"][0]["protocol_version_id"] == str(scope.version.id)
            assert result["pins"][0]["node_id"] == "first"
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(WorkflowDefinition)
                        .where(WorkflowDefinition.project_id == scope.project.id)
                    )
                    == 0
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(ResearchTask)
                        .where(ResearchTask.project_id == scope.project.id)
                    )
                    == 0
                )
            published = await confirm(sessions, scope, confirmation(params, result))
            assert published["revision"] == 1
            assert len(published["revisions"]) == 1
            assert published["current_revision"]["graph"]["nodes"][0][
                "initial_values"
            ] == {"value": 3.5}
            retrieved = await get(sessions, scope, published["id"])
            assert retrieved["runs"] == []
            assert retrieved["capabilities"] == {
                "read": True,
                "write": True,
                "run": True,
            }
            async with sessions() as db:
                listed = await api.list_definitions(
                    scope.project.id, scope.owner, db, Response()
                )
                context = await api.workflow_context(
                    scope.project.id, scope.owner, db, Response()
                )
                assert [item["id"] for item in listed["items"]] == [published["id"]]
                assert context["protocols"][0]["versions"][0]["id"] == scope.version.id
                assert context["tasks"] == []

    asyncio.run(exercise())


def test_new_revision_preserves_original_pins_layout_and_idempotent_request_history():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            original, original_command = await publish(sessions, scope)
            original_revision = copy.deepcopy(original["current_revision"])
            params = draft(
                scope,
                nodes=[
                    node(
                        scope, position={"x": 500, "y": 40}, initial_values={"value": 8}
                    )
                ],
                definition_id=original["id"],
                expected_revision=1,
            )
            revised, _ = await publish(sessions, scope, params)
            assert revised["revision"] == 2
            assert revised["revisions"][1] == original_revision
            assert revised["current_revision"]["id"] != original_revision["id"]
            assert (
                revised["current_revision"]["graph"]["nodes"][0]["node_id"] == "first"
            )
            replay = await confirm(sessions, scope, original_command)
            assert replay["id"] == original["id"]
            assert replay["revision"] == 2
            assert len(replay["revisions"]) == 2
            assert replay["revisions"][1] == original_revision

    asyncio.run(exercise())


def test_stale_definition_revision_and_changed_preview_body_are_rejected():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            original, _ = await publish(sessions, scope)
            params = draft(scope, definition_id=original["id"], expected_revision=1)
            stale_command = confirmation(params, await preview(sessions, scope, params))
            changed = stale_command.model_copy(
                update={"title": "Altered after preview"}
            )
            with pytest.raises(HTTPException) as error:
                await confirm(sessions, scope, changed)
            assert error.value.status_code == 409
            await publish(sessions, scope, params)
            with pytest.raises(HTTPException) as error:
                await confirm(sessions, scope, stale_command)
            assert error.value.status_code == 409
            assert (await get(sessions, scope, original["id"]))["revision"] == 2

    asyncio.run(exercise())


def test_protocol_content_change_after_preview_requires_new_confirmation():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            params = draft(scope)
            command = confirmation(params, await preview(sessions, scope, params))
            # Explicit fault injection simulates a pinned source changed out of band.
            async with sessions() as db:
                await db.execute(
                    update(ProtocolVersion)
                    .where(ProtocolVersion.id == scope.version.id)
                    .values(aimd="Changed pinned content")
                )
                await db.commit()
            with pytest.raises(HTTPException) as error:
                await confirm(sessions, scope, command)
            assert error.value.status_code == 409
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


def test_parallel_replay_creates_one_definition_and_reusing_key_for_other_body_fails():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            params = draft(scope)
            command = confirmation(params, await preview(sessions, scope, params))
            first, second = await asyncio.gather(
                confirm(sessions, scope, command), confirm(sessions, scope, command)
            )
            assert first["id"] == second["id"]
            assert first["current_revision"]["id"] == second["current_revision"]["id"]
            with pytest.raises(HTTPException) as error:
                await confirm(
                    sessions,
                    scope,
                    command.model_copy(update={"description": "Different request"}),
                )
            assert error.value.status_code == 409
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(WorkflowDefinition)
                        .where(WorkflowDefinition.project_id == scope.project.id)
                    )
                    == 1
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(WorkflowRevision)
                        .where(WorkflowRevision.definition_id == first["id"])
                    )
                    == 1
                )

    asyncio.run(exercise())


def test_concurrent_distinct_revision_confirmations_do_not_overwrite_each_other():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            original, _ = await publish(sessions, scope)
            params = draft(scope, definition_id=original["id"], expected_revision=1)
            result = await preview(sessions, scope, params)
            outcomes = await asyncio.gather(
                confirm(sessions, scope, confirmation(params, result)),
                confirm(sessions, scope, confirmation(params, result)),
                return_exceptions=True,
            )
            errors = [item for item in outcomes if isinstance(item, HTTPException)]
            assert len(errors) == 1 and errors[0].status_code == 409
            assert len([item for item in outcomes if isinstance(item, dict)]) == 1
            retrieved = await get(sessions, scope, original["id"])
            assert retrieved["revision"] == 2
            assert len(retrieved["revisions"]) == 2

    asyncio.run(exercise())


def test_public_project_does_not_publish_workflow_to_outsiders():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions, public=True)
            published, command = await publish(sessions, scope)
            calls = [
                get(sessions, scope, published["id"], user=scope.outsider),
                preview(sessions, scope, user=scope.outsider),
                confirm(sessions, scope, command, user=scope.outsider),
            ]
            outcomes = await asyncio.gather(*calls, return_exceptions=True)
            assert all(
                isinstance(item, HTTPException) and item.status_code == 403
                for item in outcomes
            )
            for handler in [api.list_definitions, api.workflow_context]:
                async with sessions() as db:
                    with pytest.raises(HTTPException) as error:
                        await handler(scope.project.id, scope.outsider, db, Response())
                    assert error.value.status_code == 403

    asyncio.run(exercise())


def test_cross_project_protocol_and_mismatched_version_are_not_resolved():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            other = await seed_analysis(sessions)
            for invalid in [
                node(other),
                node(scope, protocol_version_id=str(other.version.id)),
            ]:
                with pytest.raises(HTTPException) as error:
                    await preview(sessions, scope, draft(scope, nodes=[invalid]))
                assert error.value.status_code == 404

    asyncio.run(exercise())


def test_membership_revocation_after_preview_blocks_confirmation_and_read():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            published, _ = await publish(sessions, scope)
            params = draft(scope)
            command = confirmation(
                params, await preview(sessions, scope, params, user=scope.analyst)
            )
            async with sessions() as db:
                await db.execute(
                    delete(LabUser).where(
                        LabUser.lab_id == scope.lab.id,
                        LabUser.user_id == scope.analyst.id,
                    )
                )
                await db.commit()
            with pytest.raises(HTTPException) as error:
                await confirm(sessions, scope, command, user=scope.analyst)
            assert error.value.status_code == 403
            with pytest.raises(HTTPException) as error:
                await get(sessions, scope, published["id"], user=scope.analyst)
            assert error.value.status_code == 403

    asyncio.run(exercise())


def test_viewer_can_read_but_cannot_publish_workflow_or_start_run():
    async def exercise():
        async with database() as sessions:
            # The legacy private-Project matrix deliberately does not grant a
            # Viewer Protocol access; the public member Viewer may read pins.
            scope = await seed_analysis(sessions, public=True)
            published, _ = await publish(sessions, scope)
            async with sessions() as db:
                await db.execute(
                    update(ProjectUser)
                    .where(
                        ProjectUser.project_id == scope.project.id,
                        ProjectUser.user_id == scope.analyst.id,
                    )
                    .values(role=ProjectRole.VIEWER)
                )
                await db.commit()
            retrieved = await get(sessions, scope, published["id"], user=scope.analyst)
            assert retrieved["capabilities"] == {
                "read": True,
                "write": False,
                "run": False,
            }
            with pytest.raises(HTTPException) as error:
                await preview(sessions, scope, user=scope.analyst)
            assert error.value.status_code == 403
            task = await create_task(sessions, scope)
            with pytest.raises(HTTPException) as error:
                await start_workflow(
                    sessions, scope, published, task, user=scope.analyst
                )
            assert error.value.status_code == 403

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "values", [{"unknown": 1}, {"value": "not a number"}, {"value": True}, {"group": 2}]
)
def test_initial_values_are_checked_against_pinned_protocol_schema(values):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            with pytest.raises(HTTPException) as error:
                await preview(
                    sessions,
                    scope,
                    draft(scope, nodes=[node(scope, initial_values=values)]),
                )
            assert error.value.status_code == 422

    asyncio.run(exercise())


def test_current_adapter_rejects_unsupported_analysis_and_unknown_condition_fields():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            with pytest.raises(HTTPException) as error:
                await preview(
                    sessions,
                    scope,
                    draft(
                        scope,
                        nodes=[
                            {
                                "node_id": "analyze",
                                "kind": "analysis",
                                "pipeline_revision_id": str(uuid4()),
                            }
                        ],
                    ),
                )
            assert error.value.status_code == 422
            conditional = edge("first", "second") | {
                "condition": {
                    "path": ["var", "unknown"],
                    "value_type": "number",
                    "operator": "gt",
                    "value": 1,
                }
            }
            with pytest.raises(HTTPException) as error:
                await preview(
                    sessions,
                    scope,
                    draft(
                        scope,
                        nodes=[node(scope), node(scope, "second")],
                        edges=[conditional],
                    ),
                )
            assert error.value.status_code == 422

    asyncio.run(exercise())


def test_revision_is_immutable_in_postgres_and_populated_downgrade_refuses_data_loss():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            published, _ = await publish(sessions, scope)
            revision_id = UUID(str(published["current_revision"]["id"]))
            async with sessions() as db:
                with pytest.raises(DBAPIError, match="immutable"):
                    await db.execute(
                        update(WorkflowRevision)
                        .where(WorkflowRevision.id == revision_id)
                        .values(title="Tampered history")
                    )
                await db.rollback()
                assert (await db.get(WorkflowRevision, revision_id)).title == published[
                    "title"
                ]

            def downgrade(connection):
                context = MigrationContext.configure(connection)
                with Operations.context(context):
                    import_module(
                        "migrations.versions.0063_workflow_definitions"
                    ).downgrade()

            async with sessions() as db:
                connection = await db.connection()
                with pytest.raises(RuntimeError, match="Workflow assets exist"):
                    await connection.run_sync(downgrade)
                await db.rollback()
                assert (
                    await db.scalar(text("SELECT to_regclass('workflow_revisions')"))
                    == "workflow_revisions"
                )
                assert await db.get(WorkflowRevision, revision_id) is not None

    asyncio.run(exercise())


def test_single_protocol_workflow_starts_real_governed_action_with_ai_off_and_replays_once():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            workflow, _ = await publish(sessions, scope)
            task = await create_task(sessions, scope)
            started, command = await start_workflow(sessions, scope, workflow, task)
            assert len(started["actions"]) == 1
            assert started["actions"][0]["node_id"] == "first"
            async with sessions() as db:
                replay = await api.confirm_workflow_run(
                    UUID(str(workflow["id"])), command, scope.owner, db
                )
                assert replay == started
                run = await db.get(ResearchRun, UUID(str(started["run_id"])))
                assert run.environment_snapshot["manual_workflow"][
                    "revision_id"
                ] == str(workflow["current_revision"]["id"])
                plans = list(
                    (
                        await db.scalars(
                            select(ResearchPlanVersion).where(
                                ResearchPlanVersion.run_id == run.id
                            )
                        )
                    ).all()
                )
                assert plans[-1].kind == "manual_workflow"
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(WorkflowRunBinding)
                        .where(WorkflowRunBinding.run_id == run.id)
                    )
                    == 1
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(ResearchAction)
                        .where(ResearchAction.run_id == run.id)
                    )
                    == 1
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(PersistentJob)
                        .where(
                            PersistentJob.kind == "research_run_advance",
                            PersistentJob.idempotency_key.like(
                                f"research-run:{run.id}:%"
                            ),
                        )
                    )
                    == 0
                )

    asyncio.run(exercise())


def test_repeated_protocol_sequence_creates_distinct_actions_and_independent_records():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            workflow, _ = await publish(
                sessions,
                scope,
                draft(
                    scope,
                    nodes=[node(scope), node(scope, "second")],
                    edges=[edge("first", "second")],
                ),
            )
            task = await create_task(sessions, scope)
            started, _ = await start_workflow(sessions, scope, workflow, task)
            actions = await actions_by_node(sessions, started["run_id"])
            assert set(actions) == {"first", "second"}
            assert actions["first"].id != actions["second"].id
            assert actions["second"].status == "blocked"
            async with sessions() as db:
                dependency = await db.scalar(
                    select(ResearchActionDependency).where(
                        ResearchActionDependency.action_id == actions["second"].id
                    )
                )
                assert dependency.depends_on_action_id == actions["first"].id
                assert (
                    await db.scalar(
                        select(ResearchHumanWorkItem.id).where(
                            ResearchHumanWorkItem.action_id == actions["second"].id
                        )
                    )
                    is None
                )
            first_record = await add_record(sessions, scope, 3, number=1)
            await submit_record(sessions, scope, actions["first"].id, first_record)
            released = await actions_by_node(sessions, started["run_id"])
            assert released["first"].status == "completed"
            assert released["second"].status != "blocked"
            with pytest.raises(HTTPException) as error:
                await submit_record(sessions, scope, actions["second"].id, first_record)
            assert error.value.status_code == 409
            second_record = await add_record(sessions, scope, 4, number=2)
            await submit_record(sessions, scope, actions["second"].id, second_record)
            async with sessions() as db:
                protocol_runs = list(
                    (
                        await db.scalars(
                            select(ResearchProtocolRun)
                            .join(
                                ResearchAction,
                                ResearchAction.id == ResearchProtocolRun.action_id,
                            )
                            .where(
                                ResearchAction.run_id == UUID(str(started["run_id"]))
                            )
                        )
                    ).all()
                )
                assert {item.record_id for item in protocol_runs} == {
                    first_record.id,
                    second_record.id,
                }
                assert len({item.id for item in protocol_runs}) == 2
                run = await db.get(ResearchRun, UUID(str(started["run_id"])))
                assert run.status == "completed"
                assert (
                    await db.get(ResearchTask, run.task_id)
                ).status == "review_required"
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(PersistentJob)
                        .where(
                            PersistentJob.kind == "research_run_advance",
                            PersistentJob.idempotency_key.like(
                                f"research-run:{run.id}:%"
                            ),
                        )
                    )
                    == 0
                )

    asyncio.run(exercise())


def test_parallel_roots_and_join_only_release_after_all_real_receipts_complete():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            workflow, _ = await publish(
                sessions,
                scope,
                draft(
                    scope,
                    nodes=[node(scope, "a"), node(scope, "b"), node(scope, "join")],
                    edges=[edge("a", "join"), edge("b", "join")],
                ),
            )
            task = await create_task(sessions, scope)
            started, _ = await start_workflow(sessions, scope, workflow, task)
            actions = await actions_by_node(sessions, started["run_id"])
            assert actions["a"].status != "blocked"
            assert actions["b"].status != "blocked"
            assert actions["join"].status == "blocked"
            await submit_record(
                sessions,
                scope,
                actions["a"].id,
                await add_record(sessions, scope, 2, number=1),
            )
            assert (await actions_by_node(sessions, started["run_id"]))[
                "join"
            ].status == "blocked"
            await submit_record(
                sessions,
                scope,
                actions["b"].id,
                await add_record(sessions, scope, 3, number=2),
            )
            assert (await actions_by_node(sessions, started["run_id"]))[
                "join"
            ].status != "blocked"
            await submit_record(
                sessions,
                scope,
                actions["join"].id,
                await add_record(sessions, scope, 4, number=3),
            )
            assert all(
                action.status == "completed"
                for action in (
                    await actions_by_node(sessions, started["run_id"])
                ).values()
            )

    asyncio.run(exercise())


def test_private_viewer_cannot_use_workflow_to_bypass_protocol_permissions():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            workflow, _ = await publish(sessions, scope)
            async with sessions() as db:
                await db.execute(
                    update(ProjectUser)
                    .where(
                        ProjectUser.project_id == scope.project.id,
                        ProjectUser.user_id == scope.analyst.id,
                    )
                    .values(role=ProjectRole.VIEWER)
                )
                await db.commit()
            async with sessions() as db:
                context = await api.workflow_context(
                    scope.project.id, scope.analyst, db, Response()
                )
                listed = await api.list_definitions(
                    scope.project.id, scope.analyst, db, Response()
                )
                assert context["protocols"] == []
                assert listed["items"] == []
            with pytest.raises(HTTPException) as error:
                await get(sessions, scope, workflow["id"], user=scope.analyst)
            assert error.value.status_code == 403

    asyncio.run(exercise())


@pytest.mark.parametrize("operation", ["pause", "cancel"])
def test_paused_or_cancelled_fixed_run_rejects_new_record_receipts(operation):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            workflow, _ = await publish(sessions, scope)
            task = await create_task(sessions, scope)
            started, _ = await start_workflow(sessions, scope, workflow, task)
            action = (await actions_by_node(sessions, started["run_id"]))["first"]
            await approve_action(sessions, scope, action.id)
            async with sessions() as db:
                current = await db.get(ResearchTask, UUID(str(task["id"])))
                await getattr(research_tasks, f"{operation}_research_task")(
                    current.id,
                    research_tasks.TaskTransitionParams(
                        expected_revision=current.revision,
                        reason="Synthetic operator stop",
                    ),
                    scope.owner,
                    db,
                )
            record = await add_record(sessions, scope, 5)
            with pytest.raises(HTTPException) as error:
                await submit_record(sessions, scope, action.id, record)
            assert error.value.status_code == 409
            async with sessions() as db:
                protocol_run = await db.scalar(
                    select(ResearchProtocolRun).where(
                        ResearchProtocolRun.action_id == action.id
                    )
                )
                assert protocol_run.record_id is None
                run = await db.get(ResearchRun, UUID(str(started["run_id"])))
                assert (
                    run.status == {"pause": "paused", "cancel": "cancelled"}[operation]
                )
                if operation == "pause":
                    current = await db.get(ResearchTask, run.task_id)
                    await research_tasks.resume_research_task(
                        current.id,
                        research_tasks.TaskTransitionParams(
                            expected_revision=current.revision,
                            reason="Explicit synthetic resume",
                        ),
                        scope.owner,
                        db,
                    )
            if operation == "pause":
                await submit_record(sessions, scope, action.id, record)
                assert (await actions_by_node(sessions, started["run_id"]))[
                    "first"
                ].status == "completed"

    asyncio.run(exercise())


def test_recalled_member_cannot_submit_already_assigned_workflow_work():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            workflow, _ = await publish(sessions, scope)
            task = await create_task(sessions, scope)
            started, _ = await start_workflow(sessions, scope, workflow, task)
            action = (await actions_by_node(sessions, started["run_id"]))["first"]
            await approve_action(sessions, scope, action.id)
            record = await add_record(sessions, scope, 5)
            async with sessions() as db:
                await db.execute(
                    delete(LabUser).where(
                        LabUser.lab_id == scope.lab.id,
                        LabUser.user_id == scope.owner.id,
                    )
                )
                await db.commit()
            with pytest.raises(HTTPException) as error:
                await submit_record(sessions, scope, action.id, record)
            assert error.value.status_code == 403
            async with sessions() as db:
                protocol_run = await db.scalar(
                    select(ResearchProtocolRun).where(
                        ResearchProtocolRun.action_id == action.id
                    )
                )
                assert protocol_run.record_id is None

    asyncio.run(exercise())


def test_new_template_revision_does_not_change_in_progress_graph_or_inputs():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            original_draft = draft(
                scope,
                nodes=[node(scope), node(scope, "second")],
                edges=[edge("first", "second")],
            )
            workflow, _ = await publish(sessions, scope, original_draft)
            task = await create_task(sessions, scope)
            started, _ = await start_workflow(sessions, scope, workflow, task)
            original_revision_id = UUID(str(workflow["current_revision"]["id"]))
            updated, _ = await publish(
                sessions,
                scope,
                draft(
                    scope,
                    nodes=[
                        node(scope, "second", position={"x": -100, "y": 80}),
                        node(scope, initial_values={"value": 1000}),
                    ],
                    edges=[edge("second", "first")],
                    definition_id=workflow["id"],
                    expected_revision=1,
                ),
            )
            assert updated["revision"] == 2
            actions = await actions_by_node(sessions, started["run_id"])
            assert actions["second"].status == "blocked"
            await submit_record(
                sessions,
                scope,
                actions["first"].id,
                await add_record(sessions, scope, 2, number=1),
            )
            await submit_record(
                sessions,
                scope,
                actions["second"].id,
                await add_record(sessions, scope, 3, number=2),
            )
            async with sessions() as db:
                binding = await db.scalar(
                    select(WorkflowRunBinding).where(
                        WorkflowRunBinding.run_id == UUID(str(started["run_id"]))
                    )
                )
                assert binding.workflow_revision_id == original_revision_id
                run = await db.get(ResearchRun, binding.run_id)
                assert run.environment_snapshot["manual_workflow"][
                    "revision_id"
                ] == str(original_revision_id)
                first = await db.scalar(
                    select(ResearchProtocolRun).where(
                        ResearchProtocolRun.action_id == actions["first"].id
                    )
                )
                assert first.initial_values == {}
                assert run.status == "completed"

    asyncio.run(exercise())


def test_fixed_workflow_rejects_all_generic_out_of_graph_action_entry_points():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            workflow, _ = await publish(sessions, scope)
            task = await create_task(sessions, scope)
            started, _ = await start_workflow(sessions, scope, workflow, task)
            requests = [
                (
                    research_tasks.preview_manual_protocol_action,
                    research_tasks.ManualProtocolActionDraft(
                        protocol_id=scope.protocol.id, idempotency_key=uuid4().hex
                    ),
                ),
                (
                    research_actions.preview_tool_action,
                    research_actions.ToolActionDraft(
                        tool_key="knowledge.search",
                        arguments={"query": "not executed"},
                        idempotency_key=uuid4().hex,
                    ),
                ),
                (
                    research_resources.preview_resource_action,
                    research_resources.ResourceActionDraft(
                        kind="inventory",
                        resource_id=uuid4(),
                        container_id=uuid4(),
                        quantity=1,
                        unit="mL",
                        purpose="Not reserved",
                        idempotency_key=uuid4().hex,
                    ),
                ),
                (
                    research_compute_jobs.preview_compute_action,
                    research_compute_jobs.ComputeActionDraft(
                        compute_environment_revision_id=uuid4(),
                        language="python",
                        source_code="print('not executed')",
                        idempotency_key=uuid4().hex,
                    ),
                ),
                (
                    research_instrument_jobs.preview_instrument_action,
                    research_instrument_jobs.InstrumentActionDraft(
                        command_id=uuid4(),
                        equipment_booking_id=uuid4(),
                        idempotency_key=uuid4().hex,
                    ),
                ),
                (
                    research_service_jobs.preview_service_action,
                    research_service_jobs.ServiceActionDraft(
                        service_offering_id=uuid4(), idempotency_key=uuid4().hex
                    ),
                ),
            ]
            for handler, params in requests:
                async with sessions() as db:
                    with pytest.raises(HTTPException) as error:
                        await handler(UUID(str(task["id"])), params, scope.owner, db)
                    assert error.value.status_code == 409, handler.__name__
                    assert "workflow" in error.value.detail.lower(), handler.__name__
            assert len(await actions_by_node(sessions, started["run_id"])) == 1

    asyncio.run(exercise())


@pytest.mark.parametrize("tamper", ["protocol_content", "node_inputs", "environment"])
def test_execution_integrity_change_pauses_next_dispatch_and_preserves_old_evidence(
    tamper,
):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            workflow, _ = await publish(
                sessions,
                scope,
                draft(
                    scope,
                    nodes=[node(scope, "a"), node(scope, "b"), node(scope, "join")],
                    edges=[edge("a", "join"), edge("b", "join")],
                ),
            )
            task = await create_task(sessions, scope)
            started, _ = await start_workflow(sessions, scope, workflow, task)
            actions = await actions_by_node(sessions, started["run_id"])
            record = await add_record(sessions, scope, 7)
            await submit_record(sessions, scope, actions["a"].id, record)
            # Explicit out-of-band fault injection, never a supported edit path.
            async with sessions() as db:
                if tamper == "protocol_content":
                    await db.execute(
                        update(ProtocolVersion)
                        .where(ProtocolVersion.id == scope.version.id)
                        .values(aimd="Tampered source")
                    )
                elif tamper == "node_inputs":
                    await db.execute(
                        update(ResearchProtocolRun)
                        .where(ResearchProtocolRun.action_id == actions["join"].id)
                        .values(initial_values={"value": 999})
                    )
                else:
                    run = await db.get(ResearchRun, UUID(str(started["run_id"])))
                    run.environment_snapshot = {
                        **run.environment_snapshot,
                        "unconfirmed_environment_change": True,
                    }
                await db.commit()
            async with sessions() as db:
                run = await db.get(ResearchRun, UUID(str(started["run_id"])))
                current_task = await db.get(ResearchTask, run.task_id)
                completed_action = await db.get(ResearchAction, actions["a"].id)
                assert (
                    await hold_or_release_aira_action_group(
                        db, task=current_task, run=run, action=completed_action
                    )
                    is False
                )
                await db.commit()
            async with sessions() as db:
                run = await db.get(ResearchRun, UUID(str(started["run_id"])))
                assert run.status == "paused"
                assert run.last_error
                assert (await db.get(ResearchTask, run.task_id)).status == "paused"
                first = await db.scalar(
                    select(ResearchProtocolRun).where(
                        ResearchProtocolRun.action_id == actions["a"].id
                    )
                )
                assert first.record_id == record.id
                assert (
                    await db.get(ResearchAction, actions["join"].id)
                ).status == "blocked"
                assert (
                    await db.scalar(
                        select(ResearchHumanWorkItem.id).where(
                            ResearchHumanWorkItem.action_id == actions["join"].id
                        )
                    )
                    is None
                )
            with pytest.raises(HTTPException) as error:
                await approve_action(sessions, scope, actions["b"].id)
            assert error.value.status_code == 409

    asyncio.run(exercise())


def test_replayed_confirmation_identifies_original_revision_not_newer_published_head():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            original, original_command = await publish(sessions, scope)
            original_revision_id = str(original["current_revision"]["id"])
            assert str(original["confirmed_revision_id"]) == original_revision_id
            revised, _ = await publish(
                sessions,
                scope,
                draft(
                    scope,
                    nodes=[node(scope, initial_values={"value": 8})],
                    definition_id=original["id"],
                    expected_revision=1,
                ),
            )
            revised_revision_id = str(revised["current_revision"]["id"])
            assert revised_revision_id != original_revision_id
            assert str(revised["confirmed_revision_id"]) == revised_revision_id
            replay = await confirm(sessions, scope, original_command)
            assert replay["revision"] == 2
            assert str(replay["current_revision"]["id"]) == revised_revision_id
            assert str(replay["confirmed_revision_id"]) == original_revision_id
            assert len(replay["revisions"]) == 2
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(WorkflowRevision)
                        .where(
                            WorkflowRevision.definition_id == UUID(str(original["id"]))
                        )
                    )
                    == 2
                )

    asyncio.run(exercise())


def test_authorized_other_member_is_pinned_as_actual_starter_without_replacing_task_owner():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            workflow, _ = await publish(sessions, scope)
            task = await create_task(sessions, scope)
            started, _ = await start_workflow(
                sessions, scope, workflow, task, user=scope.analyst
            )
            action = (await actions_by_node(sessions, started["run_id"]))["first"]
            assert action.status == "proposed"
            assert action.assignee_user_id == scope.owner.id
            async with sessions() as db:
                run = await db.get(ResearchRun, UUID(str(started["run_id"])))
                assert run.requested_by_user_id == scope.analyst.id
                assert run.status == "waiting_for_approval"
                binding = await db.scalar(
                    select(WorkflowRunBinding).where(
                        WorkflowRunBinding.run_id == run.id
                    )
                )
                assert binding.created_by_user_id == scope.analyst.id
                stored_task = await db.get(ResearchTask, run.task_id)
                assert stored_task.owner_user_id == scope.owner.id
                assert stored_task.created_by_user_id == scope.owner.id
                event = await db.scalar(
                    select(ResearchEvent).where(
                        ResearchEvent.run_id == run.id,
                        ResearchEvent.kind == "run.started",
                    )
                )
                assert event.actor_user_id == scope.analyst.id
                # The owner remains authorized, but withdrawing the actual
                # requester's membership must block further execution too.
                await db.execute(
                    delete(LabUser).where(
                        LabUser.lab_id == scope.lab.id,
                        LabUser.user_id == scope.analyst.id,
                    )
                )
                await db.commit()
            with pytest.raises(HTTPException) as error:
                await approve_action(sessions, scope, action.id)
            assert error.value.status_code == 403
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(ResearchHumanWorkItem.id).where(
                            ResearchHumanWorkItem.action_id == action.id
                        )
                    )
                    is None
                )
                assert (await db.get(ResearchAction, action.id)).status == "proposed"

    asyncio.run(exercise())
