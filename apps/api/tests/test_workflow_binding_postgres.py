"""Real governed Workflow data transfer; no mocked permission or execution."""

import asyncio
import copy
from datetime import UTC, datetime
from importlib import import_module
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError

from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.research import (
    ResearchAction,
    ResearchApproval,
    ResearchHumanWorkItem,
    ResearchProtocolRun,
    ResearchRun,
)
from app.models.research_asset import ResearchActionOutputSnapshot
from app.models.research_execution import ResearchExecutorBinding
from app.models.workflow_definition import WorkflowNodeResolution
from tests.test_workflow_definitions_postgres import (
    actions_by_node,
    add_record,
    approve_action,
    create_task,
    database,
    draft,
    edge,
    get,
    node,
    preview,
    publish,
    seed_analysis,
    start_workflow,
    submit_record,
)
from tests.test_workflow_definitions_postgres import (
    deterministic_no_ai as deterministic_no_ai,
)
from tests.test_workflow_definitions_postgres import (
    pytestmark as pytestmark,
)


def mapping(source="first", target="second", **changes):
    return {
        "binding_id": "measurement",
        "source_node_id": source,
        "source_path": ["var", "value"],
        "target_node_id": target,
        "target_path": ["var", "value"],
        "value_type": "number",
        "unit": "mg/L",
        "cardinality": "one",
        **changes,
    }


async def setup_bound(sessions, scope):
    workflow, _ = await publish(
        sessions,
        scope,
        draft(
            scope,
            nodes=[node(scope), node(scope, "second")],
            edges=[edge("first", "second")],
            bindings=[mapping()],
        ),
    )
    task = await create_task(sessions, scope)
    started, _ = await start_workflow(sessions, scope, workflow, task)
    return workflow, started, await actions_by_node(sessions, started["run_id"])


def test_exact_record_binding_is_previewed_approved_and_preserved_after_new_record_revision():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            workflow, started, actions = await setup_bound(sessions, scope)
            record = await add_record(sessions, scope, 3.5)
            await submit_record(sessions, scope, actions["first"].id, record)
            actions = await actions_by_node(sessions, started["run_id"])
            target = actions["second"]
            assert target.input_data["initial_values"] == {"value": 3.5}
            assert target.requirements["approval_policy"] == "always_ask"
            async with sessions() as db:
                receipt = await db.scalar(
                    select(WorkflowNodeResolution).where(
                        WorkflowNodeResolution.action_id == target.id
                    )
                )
                assert receipt.state == "ready"
                assert receipt.initial_values == {"value": 3.5}
                source = receipt.receipt["sources"]["first"]
                assert source["record_id"] == str(record.id)
                assert source["record_version"] == 1
                snapshot = await db.get(
                    ResearchActionOutputSnapshot, UUID(source["snapshot_id"])
                )
                assert snapshot.output_data["record"]["data"] == record.data
                approval = await db.scalar(
                    select(ResearchApproval).where(
                        ResearchApproval.action_id == target.id,
                        ResearchApproval.status == "pending",
                    )
                )
                assert approval.preview_digest == target.preview_digest
                assert (
                    await db.scalar(
                        select(ResearchHumanWorkItem.id).where(
                            ResearchHumanWorkItem.action_id == target.id
                        )
                    )
                    is None
                )
                assert (
                    await db.scalar(
                        select(ResearchProtocolRun).where(
                            ResearchProtocolRun.action_id == target.id
                        )
                    )
                ).initial_values == {"value": 3.5}
            # A later revision must not silently replace the exact accepted input.
            await add_record(sessions, scope, 99, record_id=record.id, revision=2)
            await approve_action(sessions, scope, target.id)
            await submit_record(
                sessions,
                scope,
                target.id,
                await add_record(sessions, scope, 3.5, number=2),
            )
            async with sessions() as db:
                assert (
                    await db.get(ResearchRun, UUID(str(started["run_id"])))
                ).status == "completed"
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(WorkflowNodeResolution)
                        .where(
                            WorkflowNodeResolution.run_id
                            == UUID(str(started["run_id"]))
                        )
                    )
                    == 1
                )
            detail = await get(sessions, scope, workflow["id"])
            assert all(
                item["status"] == "completed" for item in detail["runs"][0]["actions"]
            )

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "change",
    [
        {"unit": "g/L"},
        {"value_type": "string", "unit": None},
        {"target_path": ["var", "unknown"]},
        {"source_path": ["var", "unknown"]},
    ],
)
def test_binding_preview_rejects_unknown_fields_and_mismatched_type_or_unit(change):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            with pytest.raises(HTTPException) as error:
                await preview(
                    sessions,
                    scope,
                    draft(
                        scope,
                        nodes=[node(scope), node(scope, "second")],
                        edges=[edge("first", "second")],
                        bindings=[mapping(**change)],
                    ),
                )
            assert error.value.status_code == 422

    asyncio.run(exercise())


def test_inactive_source_cannot_supply_required_binding_to_join_selected_by_another_edge():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            conditional = edge("first", "second") | {
                "condition": {
                    "path": ["var", "value"],
                    "value_type": "number",
                    "unit": "mg/L",
                    "operator": "gt",
                    "value": 10,
                }
            }
            workflow, _ = await publish(
                sessions,
                scope,
                draft(
                    scope,
                    nodes=[node(scope), node(scope, "other"), node(scope, "second")],
                    edges=[conditional, edge("other", "second")],
                    bindings=[mapping()],
                ),
            )
            started, _ = await start_workflow(
                sessions, scope, workflow, await create_task(sessions, scope)
            )
            actions = await actions_by_node(sessions, started["run_id"])
            await submit_record(
                sessions,
                scope,
                actions["first"].id,
                await add_record(sessions, scope, 3),
            )
            assert (await actions_by_node(sessions, started["run_id"]))[
                "second"
            ].status == "blocked"
            await submit_record(
                sessions,
                scope,
                actions["other"].id,
                await add_record(sessions, scope, 4, number=2),
            )
            actions = await actions_by_node(sessions, started["run_id"])
            assert actions["second"].status == "failed"
            assert (
                actions["second"].output_data["workflow_resolution"]["state"]
                == "failed"
            )
            async with sessions() as db:
                assert (
                    await db.get(ResearchRun, UUID(str(started["run_id"])))
                ).status == "failed"

    asyncio.run(exercise())


def test_resolution_receipts_are_immutable_and_populated_downgrade_refuses_loss():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            _, started, actions = await setup_bound(sessions, scope)
            await submit_record(
                sessions,
                scope,
                actions["first"].id,
                await add_record(sessions, scope, 3),
            )
            async with sessions() as db:
                with pytest.raises(DBAPIError, match="immutable"):
                    await db.execute(
                        update(WorkflowNodeResolution)
                        .where(WorkflowNodeResolution.action_id == actions["second"].id)
                        .values(initial_values={"value": 99})
                    )
                await db.rollback()
                migration = import_module(
                    "migrations.versions.0064_workflow_node_resolutions"
                )
                connection = await db.connection()

                def downgrade(sync):
                    with Operations.context(MigrationContext.configure(sync)):
                        migration.downgrade()

                with pytest.raises(RuntimeError, match="receipts exist"):
                    await connection.run_sync(downgrade)
                await db.rollback()
                assert (
                    await db.scalar(
                        select(WorkflowNodeResolution.id).where(
                            WorkflowNodeResolution.run_id
                            == UUID(str(started["run_id"]))
                        )
                    )
                    is not None
                )

    asyncio.run(exercise())


@pytest.mark.parametrize("mutation", ["deleted", "same_revision_tampered"])
def test_source_is_rechecked_before_downstream_approval(mutation):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            _, started, actions = await setup_bound(sessions, scope)
            record = await add_record(sessions, scope, 3)
            await submit_record(sessions, scope, actions["first"].id, record)
            async with sessions() as db:
                change = (
                    {"deleted_at": datetime.now(UTC).replace(tzinfo=None)}
                    if mutation == "deleted"
                    else {"data": {"var": {"value": 99, "group": "A"}}}
                )
                await db.execute(
                    update(Record)
                    .where(Record.id == record.id, Record.version == 1)
                    .values(**change)
                )
                await db.commit()
            with pytest.raises(HTTPException):
                await approve_action(sessions, scope, actions["second"].id)
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(ResearchHumanWorkItem.id).where(
                            ResearchHumanWorkItem.action_id == actions["second"].id
                        )
                    )
                    is None
                )
                assert (
                    await db.get(ResearchAction, actions["first"].id)
                ).status == "completed"
                receipt = await db.scalar(
                    select(WorkflowNodeResolution).where(
                        WorkflowNodeResolution.action_id == actions["second"].id
                    )
                )
                assert receipt.initial_values == {"value": 3}

    asyncio.run(exercise())


async def second_protocol(sessions, scope, *, assignee=None, maximum=None):
    target = Protocol(
        id=uuid4(),
        project_id=scope.project.id,
        user_id=scope.owner.id,
        uid=f"target_{uuid4().hex}",
        name="Synthetic target",
        latest_version="1.0.0",
    )
    schema = copy.deepcopy(scope.version.json_schema)
    if maximum is not None:
        schema["vars"]["properties"]["value"]["maximum"] = maximum
    version = ProtocolVersion(
        id=uuid4(),
        protocol_id=target.id,
        version="1.0.0",
        json_schema=schema,
        meta_data={"id": target.uid, "version": "1.0.0", "name": target.name},
        fields={},
        assigners={},
        assigner_graph={},
        aimd="Synthetic bounded target",
    )
    async with sessions() as db:
        db.add(target)
        await db.flush()
        db.add(version)
        if assignee is not None:
            db.add(
                ResearchExecutorBinding(
                    lab_id=scope.lab.id,
                    capability_key=f"protocol:{target.id}",
                    capability_version="1.0.0",
                    executor_type="human",
                    executor_ref_type="user",
                    executor_ref_id=str(assignee.id),
                    mode="protocol_record",
                    approval_policy="always_ask",
                    created_by_user_id=scope.owner.id,
                    updated_by_user_id=scope.owner.id,
                )
            )
        await db.commit()
    return target, version


@pytest.mark.parametrize("restriction", ["recipient_access", "target_constraint"])
def test_real_target_policy_cannot_bypass_record_access_or_target_schema(restriction):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            target, version = await second_protocol(
                sessions,
                scope,
                assignee=scope.recorder if restriction == "recipient_access" else None,
                maximum=2 if restriction == "target_constraint" else None,
            )
            workflow, _ = await publish(
                sessions,
                scope,
                draft(
                    scope,
                    nodes=[
                        node(scope),
                        node(
                            scope,
                            "second",
                            protocol_id=str(target.id),
                            protocol_version_id=str(version.id),
                        ),
                    ],
                    edges=[edge("first", "second")],
                    bindings=[mapping()],
                ),
            )
            task = await create_task(
                sessions, scope, protocol_ids=[scope.protocol.id, target.id]
            )
            started, _ = await start_workflow(sessions, scope, workflow, task)
            actions = await actions_by_node(sessions, started["run_id"])
            await submit_record(
                sessions,
                scope,
                actions["first"].id,
                await add_record(sessions, scope, 3),
            )
            actions = await actions_by_node(sessions, started["run_id"])
            assert actions["first"].status == "completed"
            assert actions["second"].status == (
                "blocked" if restriction == "recipient_access" else "failed"
            )
            async with sessions() as db:
                run = await db.get(ResearchRun, UUID(str(started["run_id"])))
                assert run.status == (
                    "paused" if restriction == "recipient_access" else "failed"
                )
                assert (
                    await db.scalar(
                        select(ResearchHumanWorkItem.id).where(
                            ResearchHumanWorkItem.action_id == actions["second"].id
                        )
                    )
                    is None
                )

    asyncio.run(exercise())


@pytest.mark.parametrize("shape", ["legacy_var_wrapper", "local_root_reference"])
def test_historical_schema_roots_use_the_same_catalog_and_complete_target_validation(
    shape,
):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            variables = copy.deepcopy(scope.version.json_schema["vars"])
            schema = (
                {"type": "object", "properties": {"var": variables}}
                if shape == "legacy_var_wrapper"
                else {"$defs": {"Variables": variables}, "$ref": "#/$defs/Variables"}
            )
            async with sessions() as db:
                await db.execute(
                    update(ProtocolVersion)
                    .where(ProtocolVersion.id == scope.version.id)
                    .values(json_schema=schema)
                )
                await db.commit()
            _, started, actions = await setup_bound(sessions, scope)
            await submit_record(
                sessions,
                scope,
                actions["first"].id,
                await add_record(sessions, scope, 4),
            )
            target = (await actions_by_node(sessions, started["run_id"]))["second"]
            assert target.status == "proposed"
            assert target.input_data["initial_values"] == {"value": 4}
            await approve_action(sessions, scope, target.id)

    asyncio.run(exercise())
