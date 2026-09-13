"""Legacy structure conversion through actual permissions and PostgreSQL locks.

Fixtures are synthetic. No AI is called; existing legacy execution paths and
Records remain unchanged. Run only in the dedicated research-integration stack.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
from importlib import import_module
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError

from app.config import config
from app.models.lab import LabUser
from app.models.project import ProjectRole, ProjectUser
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.research import ResearchRun, ResearchTask
from app.models.workflow import ProtocolWorkflow
from app.models.workflow_conversion import WorkflowLegacyConversion
from app.models.workflow_definition import WorkflowDefinition, WorkflowRevision
from app.routers import workflow as legacy_api
from app.routers import workflow_conversions as api
from app.routers import workflow_definitions as workflow_api
from app.services.workflow_conversions import (
    LegacyConversionConfirm,
    LegacyConversionDraft,
)
from app.services.workflow_definitions import WorkflowDraft
from tests.test_record_analysis_postgres import add_record, database, seed_analysis
from tests.test_workflow_definitions_postgres import publish

pytestmark = pytest.mark.skipif(
    not os.environ.get("RESOURCE_TEST_DATABASE_URL"),
    reason="Use the isolated migrated research-integration PostgreSQL database",
)


@pytest.fixture(autouse=True)
def no_ai(monkeypatch):
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")
    monkeypatch.setattr(config, "AI_ENABLED", False)


async def seed_legacy(sessions, *, public=False, owner_name="owner", edges=None):
    scope = await seed_analysis(sessions, public=public)
    owner = getattr(scope, owner_name)
    record = await add_record(sessions, scope, 7, author=owner)
    async with sessions() as db:
        second = ProtocolVersion(
            id=uuid4(),
            protocol_id=scope.protocol.id,
            version="2.0.0",
            json_schema=copy.deepcopy(scope.version.json_schema),
            fields={},
            assigners={},
            assigner_graph={},
            meta_data={"id": scope.protocol.uid, "version": "2.0.0"},
            aimd="Synthetic second version",
        )
        db.add(second)
        protocol = await db.get(Protocol, scope.protocol.id)
        protocol.latest_version = "2.0.0"
        prefix = f"airalogy.id.lab.{scope.lab.uid}.project.{scope.project.uid}.protocol.{scope.protocol.uid}.v."
        workflow = ProtocolWorkflow(
            id=uuid4(),
            project_id=scope.project.id,
            user_id=owner.id,
            root_protocol_id=scope.protocol.id,
            title="Synthetic private legacy study",
            workflow_info={
                "title": "Synthetic private legacy study",
                "protocols": [
                    {
                        "protocol_index": 1,
                        "protocol_name": "First occurrence",
                        "airalogy_protocol_id": prefix + "1.0.0",
                    },
                    {
                        "protocol_index": 2,
                        "protocol_name": "Second occurrence",
                        "airalogy_protocol_id": prefix + "2.0.0",
                    },
                ],
                "edges": ["1 -> 2"] if edges is None else edges,
                "logic": "Private synthetic rule: repeat until the scientist decides to stop.",
                "default_initial_protocol_index": 2,
                "default_research_goal": "Private goal not published",
                "default_research_strategy": "Private strategy not published",
            },
            path_data={
                "path_status": "waiting_for_record",
                "steps": [
                    {
                        "step": "add_record",
                        "mode": "user",
                        "path_index": 0,
                        "data": {
                            "protocol_index": 1,
                            "airalogy_record_id": record.airalogy_id,
                        },
                    },
                ],
            },
        )
        db.add(workflow)
        await db.commit()
    return scope, workflow, record, second


async def context(sessions, scope, source, *, user=None):
    async with sessions() as db:
        response = Response()
        result = await api.legacy_conversion_context(
            source.id, user or scope.owner, db, response
        )
        assert response.headers["Cache-Control"] == "private, no-store"
        return result


def draft(value, *, edges=None):
    return LegacyConversionDraft(
        project_id=value["source"]["project_id"],
        source_digest=value["source"]["digest"],
        title="Explicitly published structure",
        description="Synthetic reviewed deterministic workflow",
        nodes=[
            {
                "protocol_index": node["protocol_index"],
                "protocol_id": node["protocol_id"],
                "protocol_version_id": node["suggested_version_id"],
            }
            for node in value["nodes"]
        ],
        edges=[{"source_protocol_index": 1, "target_protocol_index": 2}]
        if edges is None
        else edges,
        acknowledge_versions=True,
        acknowledge_structure_only=True,
        acknowledge_logic_omission=True,
    )


async def preview(sessions, scope, source, command, *, user=None):
    async with sessions() as db:
        return await api.preview_legacy_conversion(
            source.id, command, user or scope.owner, db
        )


async def confirmed_command(sessions, scope, source, *, user=None, edges=None):
    selected = draft(await context(sessions, scope, source, user=user), edges=edges)
    result = await preview(sessions, scope, source, selected, user=user)
    return LegacyConversionConfirm(
        **selected.model_dump(),
        preview_digest=result["preview_digest"],
        idempotency_key=uuid4(),
    ), result


async def confirm(sessions, scope, source, command, *, user=None):
    async with sessions() as db:
        return await api.confirm_legacy_conversion(
            source.id, command, user or scope.owner, db
        )


async def stored_bytes(sessions, source_id, record):
    async with sessions() as db:
        source = (
            await db.execute(
                text(
                    "SELECT title, workflow_info::text, path_data::text, updated_at, root_protocol_id FROM protocol_workflows WHERE id=:id"
                ),
                {"id": source_id},
            )
        ).one()
        data = (
            await db.execute(
                select(Record.data, Record.hash, Record.version).where(
                    Record.id == record.id, Record.version == record.version
                )
            )
        ).one()
        return tuple(source), tuple(data)


def test_conversion_preserves_legacy_bytes_exact_versions_and_private_history():
    async def exercise():
        async with database() as sessions:
            scope, source, record, second = await seed_legacy(sessions)
            original = await stored_bytes(sessions, source.id, record)
            value = await context(sessions, scope, source)
            assert value["nodes"][0]["suggested_version_id"] == scope.version.id
            assert value["nodes"][1]["suggested_version_id"] == second.id
            assert value["logic_text"] == source.workflow_info["logic"]
            command, checked = await confirmed_command(sessions, scope, source)
            assert await stored_bytes(sessions, source.id, record) == original
            result = await confirm(sessions, scope, source, command)
            assert await stored_bytes(sessions, source.id, record) == original
            graph = result["current_revision"]["graph"]
            assert [node["node_id"] for node in graph["nodes"]] == [
                "legacy_1",
                "legacy_2",
            ]
            assert [node["protocol_version_id"] for node in graph["nodes"]] == [
                str(scope.version.id),
                str(second.id),
            ]
            assert graph["edges"][0]["condition"] is None
            async with sessions() as db:
                public_result = await workflow_api.get_workflow(
                    result["id"], scope.analyst, db, Response()
                )
                body = json.dumps(jsonable_encoder(public_result))
                for private in (
                    str(source.id),
                    str(record.id),
                    source.workflow_info["logic"],
                    "Private goal",
                    "Private strategy",
                ):
                    assert private not in body
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(ResearchRun)
                        .join(ResearchTask, ResearchTask.id == ResearchRun.task_id)
                        .where(ResearchTask.project_id == scope.project.id)
                    )
                    == 0
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(Record)
                        .where(Record.protocol_id == scope.protocol.id)
                    )
                    == 1
                )
                receipt = await api.get_conversion_receipt(
                    result["conversion_receipt_id"], scope.owner, db, Response()
                )
                assert receipt["source_workflow_id"] == source.id
                assert [item["node_id"] for item in receipt["node_mapping"]] == [
                    "legacy_1",
                    "legacy_2",
                ]
                with pytest.raises(HTTPException) as hidden:
                    await api.get_conversion_receipt(
                        result["conversion_receipt_id"], scope.analyst, db, Response()
                    )
                assert hidden.value.status_code == 404
                old = await legacy_api.get_workflow(source.id, scope.owner, db)
                assert old["path_data"]["path_status"] == "waiting_for_record"
            # Continuing the old non-AI path remains available after conversion.
            async with sessions() as db:
                continued = await legacy_api.generate_workflow_step(
                    legacy_api.WorkflowStepPayload(
                        workflow_id=source.id, path_data=source.path_data
                    ),
                    scope.owner,
                    db,
                )
                assert continued["path_data"]["path_status"] == "waiting_for_record"
            assert checked["graph"] == graph

    asyncio.run(exercise())


@pytest.mark.parametrize("changed", ["path", "logic", "version"])
def test_stale_source_or_selected_version_prevents_any_new_asset(changed):
    async def exercise():
        async with database() as sessions:
            scope, source, _, _ = await seed_legacy(sessions)
            command, _ = await confirmed_command(sessions, scope, source)
            async with sessions() as db:
                if changed == "version":
                    await db.execute(
                        update(ProtocolVersion)
                        .where(ProtocolVersion.id == scope.version.id)
                        .values(aimd="Synthetic changed pinned content")
                    )
                else:
                    item = await db.get(ProtocolWorkflow, source.id)
                    if changed == "path":
                        item.path_data = {**item.path_data, "path_status": "completed"}
                    else:
                        item.workflow_info = {
                            **item.workflow_info,
                            "logic": "Changed private decision",
                        }
                await db.commit()
            with pytest.raises(HTTPException) as stale:
                await confirm(sessions, scope, source, command)
            assert stale.value.status_code == 409
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


def test_concurrent_replay_is_single_asset_and_old_confirmation_stays_pinned():
    async def exercise():
        async with database() as sessions:
            scope, source, _, _ = await seed_legacy(sessions)
            command, _ = await confirmed_command(sessions, scope, source)
            first, repeated = await asyncio.gather(
                confirm(sessions, scope, source, command),
                confirm(sessions, scope, source, command),
            )
            assert first["id"] == repeated["id"]
            assert first["confirmed_revision_id"] == repeated["confirmed_revision_id"]
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(WorkflowLegacyConversion)
                        .where(WorkflowLegacyConversion.source_workflow_id == source.id)
                    )
                    == 1
                )
                item = await db.get(ProtocolWorkflow, source.id)
                item.path_data = {**item.path_data, "additional_progress": True}
                await db.commit()
            updated, _ = await publish(
                sessions,
                scope,
                WorkflowDraft(
                    project_id=scope.project.id,
                    definition_id=first["id"],
                    expected_revision=1,
                    title="New public revision",
                    graph=first["current_revision"]["graph"],
                ),
            )
            replayed = await confirm(sessions, scope, source, command)
            assert replayed["confirmed_revision_id"] == first["confirmed_revision_id"]
            assert (
                replayed["current_revision"]["id"] == updated["current_revision"]["id"]
            )
            conflicting = command.model_copy(update={"title": "Different conversion"})
            with pytest.raises(HTTPException) as reused:
                await confirm(sessions, scope, source, conflicting)
            assert reused.value.status_code == 409

    asyncio.run(exercise())


def test_conversion_cannot_reuse_a_normal_workflow_confirmation_key():
    async def exercise():
        async with database() as sessions:
            scope, source, _, _ = await seed_legacy(sessions)
            conversion, checked = await confirmed_command(sessions, scope, source)
            original, existing_command = await publish(
                sessions,
                scope,
                WorkflowDraft(
                    project_id=scope.project.id,
                    title="Independent ordinary definition",
                    graph=checked["graph"],
                ),
            )
            with pytest.raises(HTTPException) as collision:
                await confirm(
                    sessions,
                    scope,
                    source,
                    conversion.model_copy(
                        update={"idempotency_key": existing_command.idempotency_key}
                    ),
                )
            assert collision.value.status_code == 409
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(WorkflowLegacyConversion)
                        .where(WorkflowLegacyConversion.source_workflow_id == source.id)
                    )
                    == 0
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(WorkflowDefinition)
                        .where(WorkflowDefinition.project_id == scope.project.id)
                    )
                    == 1
                )
                assert await db.get(WorkflowDefinition, original["id"]) is not None

    asyncio.run(exercise())


def test_legacy_owner_project_permission_and_cross_project_boundaries():
    async def exercise():
        async with database() as sessions:
            scope, source, _, _ = await seed_legacy(sessions, public=True)
            for user in (scope.analyst, scope.outsider):
                with pytest.raises(HTTPException) as hidden:
                    await context(sessions, scope, source, user=user)
                assert hidden.value.status_code == 404
            async with sessions() as db:
                listing = await api.list_legacy_workflows(
                    scope.project.id, scope.analyst, db, Response()
                )
                assert listing["items"] == []
                with pytest.raises(HTTPException) as denied:
                    await api.list_legacy_workflows(
                        scope.project.id, scope.outsider, db, Response()
                    )
                assert denied.value.status_code == 403
            other = await seed_analysis(sessions)
            command, _ = await confirmed_command(sessions, scope, source)
            substituted = copy.deepcopy(command.model_dump())
            substituted["nodes"][0]["protocol_version_id"] = other.version.id
            with pytest.raises(HTTPException) as wrong_version:
                await preview(
                    sessions,
                    scope,
                    source,
                    LegacyConversionConfirm.model_validate(substituted),
                )
            assert wrong_version.value.status_code == 422
            with pytest.raises(HTTPException):
                await preview(
                    sessions,
                    scope,
                    source,
                    command.model_copy(update={"project_id": other.project.id}),
                )
            async with sessions() as db:
                stored = await db.get(ProtocolWorkflow, source.id)
                stored.user_id = scope.analyst.id
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
                listing = await api.list_legacy_workflows(
                    scope.project.id, scope.analyst, db, Response()
                )
                assert listing["items"][0]["can_convert"] is False
            readonly = draft(await context(sessions, scope, source, user=scope.analyst))
            with pytest.raises(HTTPException) as denied:
                await preview(sessions, scope, source, readonly, user=scope.analyst)
            assert denied.value.status_code == 403

    asyncio.run(exercise())


def test_membership_revocation_blocks_initial_confirmation_and_replay():
    async def exercise():
        async with database() as sessions:
            scope, source, _, _ = await seed_legacy(sessions, owner_name="analyst")
            command, _ = await confirmed_command(
                sessions, scope, source, user=scope.analyst
            )
            result = await confirm(sessions, scope, source, command, user=scope.analyst)
            async with sessions() as db:
                await db.execute(
                    delete(ProjectUser).where(
                        ProjectUser.project_id == scope.project.id,
                        ProjectUser.user_id == scope.analyst.id,
                    )
                )
                await db.execute(
                    delete(LabUser).where(
                        LabUser.lab_id == scope.lab.id,
                        LabUser.user_id == scope.analyst.id,
                    )
                )
                await db.commit()
            for key in (command.idempotency_key, uuid4()):
                with pytest.raises(HTTPException) as denied:
                    await confirm(
                        sessions,
                        scope,
                        source,
                        command.model_copy(update={"idempotency_key": key}),
                        user=scope.analyst,
                    )
                assert denied.value.status_code == 403
            assert result["confirmed_revision_id"]

    asyncio.run(exercise())


def test_bidirectional_cycle_requires_explicit_repair_and_unselected_edges_stay_omitted():
    async def exercise():
        async with database() as sessions:
            scope, source, _, _ = await seed_legacy(
                sessions, edges=["1 <-> 2", "1 -> 2", "2 -> 1"]
            )
            value = await context(sessions, scope, source)
            assert value["edges"][0]["supported"] is False
            bad = draft(
                value,
                edges=[
                    {"source_protocol_index": 1, "target_protocol_index": 2},
                    {"source_protocol_index": 2, "target_protocol_index": 1},
                ],
            )
            with pytest.raises(HTTPException) as cycle:
                await preview(sessions, scope, source, bad)
            assert cycle.value.status_code == 422
            command, checked = await confirmed_command(
                sessions, scope, source, edges=[]
            )
            assert any(
                item["code"] == "dependencies_changed" for item in checked["warnings"]
            )
            result = await confirm(sessions, scope, source, command)
            assert result["current_revision"]["graph"]["edges"] == []
            assert all(
                node["initial_values"] == {}
                for node in result["current_revision"]["graph"]["nodes"]
            )

    asyncio.run(exercise())


def test_unavailable_original_reference_never_falls_back_to_latest_or_other_project():
    async def exercise():
        async with database() as sessions:
            scope, source, _, second = await seed_legacy(sessions)
            async with sessions() as db:
                item = await db.get(ProtocolWorkflow, source.id)
                info = copy.deepcopy(item.workflow_info)
                info["protocols"][0]["airalogy_protocol_id"] = str(scope.protocol.id)
                item.workflow_info = info
                await db.commit()
            value = await context(sessions, scope, source)
            assert value["nodes"][0]["suggested_version_id"] is None
            assert {item["id"] for item in value["nodes"][0]["versions"]} == {
                scope.version.id,
                second.id,
            }
            async with sessions() as db:
                await db.execute(
                    update(Protocol)
                    .where(Protocol.id == scope.protocol.id)
                    .values(deleted_at=source.created_at)
                )
                await db.commit()
            value = await context(sessions, scope, source)
            assert value["blockers"]
            assert all(
                node["protocol_id"] is None and node["versions"] == []
                for node in value["nodes"]
            )

    asyncio.run(exercise())


def test_conversion_receipt_is_immutable_and_blocks_destructive_downgrade():
    async def exercise():
        async with database() as sessions:
            scope, source, _, _ = await seed_legacy(sessions)
            command, _ = await confirmed_command(sessions, scope, source)
            result = await confirm(sessions, scope, source, command)
            async with sessions() as db:
                with pytest.raises(DBAPIError):
                    await db.execute(
                        update(WorkflowLegacyConversion)
                        .where(
                            WorkflowLegacyConversion.id
                            == result["conversion_receipt_id"]
                        )
                        .values(source_digest="0" * 64)
                    )
                await db.rollback()
            async with sessions() as db:
                connection = await db.connection()
                migration = import_module(
                    "migrations.versions.0067_workflow_legacy_conversions"
                )

                def downgrade(sync_connection):
                    with Operations.context(
                        MigrationContext.configure(sync_connection)
                    ):
                        migration.downgrade()

                with pytest.raises(RuntimeError, match="conversion receipts"):
                    await connection.run_sync(downgrade)
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(WorkflowRevision)
                        .where(WorkflowRevision.id == result["confirmed_revision_id"])
                    )
                    == 1
                )

    asyncio.run(exercise())
