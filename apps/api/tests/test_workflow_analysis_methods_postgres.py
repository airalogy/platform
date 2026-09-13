"""Real explicit publication, privacy and immutable method acceptance."""

import asyncio
import copy
import json
from importlib import import_module
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import event, func, select, text, update
from sqlalchemy.exc import DBAPIError

from app.models.analysis import AnalysisPipelineRevision
from app.models.protocol_version import ProtocolVersion
from app.models.workflow_analysis import WorkflowAnalysisMethod
from app.models.workflow_definition import WorkflowRevision
from app.routers import analyses
from app.routers import workflow_analysis_methods as api
from app.services.analysis_engine import AnalysisRecipe
from app.services.workflow_analysis_methods import (
    MethodPublicationConfirm,
    MethodPublicationDraft,
    get_method,
    publication_payload,
    schema_digest,
)
from app.services.workflow_definitions import WorkflowDraft
from tests.test_record_analysis_postgres import (
    add_record,
    confirm,
    database,
    execute_job,
    preview,
    seed_analysis,
)
from tests.test_workflow_definitions_postgres import (
    deterministic_no_ai as deterministic_no_ai,
)
from tests.test_workflow_definitions_postgres import node as workflow_node
from tests.test_workflow_definitions_postgres import publish as publish_workflow
from tests.test_workflow_definitions_postgres import pytestmark as pytestmark


async def saved_method(sessions, scope, *, selected_recipe=None):
    original = await add_record(sessions, scope, 8173.125)
    selected_recipe = selected_recipe or AnalysisRecipe(
        numeric_fields=["value"], group_by=[]
    )
    analysis = await confirm(
        sessions,
        scope,
        await preview(
            sessions, scope, user=scope.owner, selected_recipe=selected_recipe
        ),
        user=scope.owner,
    )
    await execute_job(sessions, analysis)
    async with sessions() as db:
        saved = await analyses.create_analysis_pipeline(
            analyses.PipelineCreateRequest(
                run_id=analysis["id"], title="Private synthetic method"
            ),
            db,
            scope.owner,
        )
    return saved, original


def publication_draft(scope, saved):
    return MethodPublicationDraft(
        project_id=scope.project.id,
        pipeline_revision_id=saved["revisions"][0]["id"],
        protocol_version_id=scope.version.id,
        title="Shared measurement method",
    )


async def publish_method(sessions, scope, saved):
    params = publication_draft(scope, saved)
    async with sessions() as db:
        result = await api.preview_method(params, scope.owner, db, Response())
    command = MethodPublicationConfirm(
        **params.model_dump(),
        preview_digest=result["preview_digest"],
        idempotency_key=uuid4(),
    )
    async with sessions() as db:
        published = await api.confirm_method(command, scope.owner, db)
    return published, command


def test_explicit_publication_does_not_disclose_private_records_selection_or_lineage():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions, public=True)
            saved, original = await saved_method(sessions, scope)
            params = publication_draft(scope, saved)
            async with sessions() as db:
                before = await api.get_methods(
                    scope.project.id, scope.recorder, db, Response()
                )
                assert before == {"items": [], "unavailable": []}
                result = await api.preview_method(params, scope.owner, db, Response())
                assert result["publication"]["recipe"] == saved["current_recipe"]
                assert result["excluded_fields"] == [
                    "source_selection",
                    "source_records",
                    "results",
                    "ai_provenance",
                ]
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(WorkflowAnalysisMethod)
                        .where(WorkflowAnalysisMethod.project_id == scope.project.id)
                    )
                    == 0
                )
                with pytest.raises(HTTPException) as denied:
                    await api.preview_method(params, scope.analyst, db, Response())
                assert denied.value.status_code in {403, 404}
            published, _command = await publish_method(sessions, scope, saved)
            async with sessions() as db:
                listing = jsonable_encoder(
                    await api.get_methods(
                        scope.project.id, scope.recorder, db, Response()
                    )
                )
                assert listing["items"] == [published]
                assert listing["unavailable"] == []
                encoded = json.dumps(listing)
                assert "8173.125" not in encoded
                for private_id in (
                    original.id,
                    saved["id"],
                    saved["revisions"][0]["id"],
                ):
                    assert str(private_id) not in encoded
                assert "source_selection" not in encoded and "provenance" not in encoded
                with pytest.raises(HTTPException) as private:
                    await analyses.get_analysis_pipeline(
                        UUID(str(saved["id"])), db, scope.recorder, Response()
                    )
                assert private.value.status_code == 404
                with pytest.raises(HTTPException) as outsider:
                    await api.get_methods(
                        scope.project.id, scope.outsider, db, Response()
                    )
                assert outsider.value.status_code == 403

    asyncio.run(exercise())


def test_concurrent_confirm_is_idempotent_and_rejects_changed_preview_command():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            saved, _record = await saved_method(sessions, scope)
            params = publication_draft(scope, saved)
            async with sessions() as db:
                result = await api.preview_method(params, scope.owner, db, Response())
            command = MethodPublicationConfirm(
                **params.model_dump(),
                preview_digest=result["preview_digest"],
                idempotency_key=uuid4(),
            )

            async def publish():
                async with sessions() as db:
                    return await api.confirm_method(command, scope.owner, db)

            first, second = await asyncio.gather(publish(), publish())
            assert first == second
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(WorkflowAnalysisMethod)
                        .where(WorkflowAnalysisMethod.project_id == scope.project.id)
                    )
                    == 1
                )
                for key in (command.idempotency_key, uuid4()):
                    changed = command.model_copy(
                        update={
                            "title": "Different shared method",
                            "idempotency_key": key,
                        }
                    )
                    with pytest.raises(HTTPException) as stale:
                        await api.confirm_method(changed, scope.owner, db)
                    assert stale.value.status_code == 409

    asyncio.run(exercise())


def test_private_method_revision_does_not_change_published_method():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            saved, _record = await saved_method(sessions, scope)
            published, _command = await publish_method(sessions, scope, saved)
            async with sessions() as db:
                revised = await analyses.revise_analysis_pipeline(
                    UUID(str(saved["id"])),
                    analyses.PipelineReviseRequest(
                        recipe=AnalysisRecipe(numeric_fields=["value"], chart="none"),
                        expected_revision=1,
                    ),
                    db,
                    scope.owner,
                )
                assert revised["recipe"]["chart"] == "none"
            async with sessions() as db:
                fixed = publication_payload(
                    await get_method(db, scope.owner, UUID(published["id"]))
                )
                assert fixed == published
                assert fixed["recipe"]["chart"] == "bar"
                original = await db.get(
                    AnalysisPipelineRevision, UUID(str(saved["revisions"][0]["id"]))
                )
                assert original.recipe == published["recipe"]

    asyncio.run(exercise())


def test_schema_change_invalidates_unconfirmed_publication_and_fixed_method():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            saved, _record = await saved_method(sessions, scope)
            published, command = await publish_method(sessions, scope, saved)
            schema = copy.deepcopy(scope.version.json_schema)
            schema["vars"]["properties"]["value"]["unit"] = "g/L"
            async with sessions() as db:
                await db.execute(
                    update(ProtocolVersion)
                    .where(ProtocolVersion.id == scope.version.id)
                    .values(json_schema=schema)
                )
                await db.commit()
            async with sessions() as db:
                with pytest.raises(HTTPException) as stale:
                    await api.confirm_method(
                        command.model_copy(update={"idempotency_key": uuid4()}),
                        scope.owner,
                        db,
                    )
                assert stale.value.status_code == 409
                with pytest.raises(HTTPException) as changed:
                    await get_method(db, scope.owner, UUID(published["id"]))
                assert changed.value.status_code == 409

    asyncio.run(exercise())


def test_schema_property_reordering_preserves_publication_preview_and_fixed_method():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            saved, _record = await saved_method(
                sessions,
                scope,
                selected_recipe=AnalysisRecipe(
                    numeric_fields=["value"], group_by=["group"]
                ),
            )
            params = publication_draft(scope, saved)
            async with sessions() as db:
                before = await api.preview_method(params, scope.owner, db, Response())
            published, command = await publish_method(sessions, scope, saved)
            assert [field["key"] for field in published["input_fields"]] == [
                "group",
                "value",
            ]
            original_digest = schema_digest(scope.version)
            schema = copy.deepcopy(scope.version.json_schema)
            properties = schema["vars"]["properties"]
            schema["vars"]["properties"] = dict(reversed(list(properties.items())))
            assert list(properties) != list(schema["vars"]["properties"])
            async with sessions() as db:
                await db.execute(
                    update(ProtocolVersion)
                    .where(ProtocolVersion.id == scope.version.id)
                    .values(json_schema=schema)
                )
                await db.commit()
            async with sessions() as db:
                current = await db.get(ProtocolVersion, scope.version.id)
                assert schema_digest(current) == original_digest
                assert (
                    await api.preview_method(params, scope.owner, db, Response())
                    == before
                )
                assert (
                    publication_payload(
                        await get_method(db, scope.owner, UUID(published["id"]))
                    )
                    == published
                )
                assert await api.confirm_method(command, scope.owner, db) == published

    asyncio.run(exercise())


def test_unavailable_method_does_not_block_another_valid_method_in_the_project():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            saved, _record = await saved_method(sessions, scope)
            stale, _command = await publish_method(sessions, scope, saved)
            second_version = ProtocolVersion(
                id=uuid4(),
                protocol_id=scope.protocol.id,
                version="1.0.1",
                json_schema=copy.deepcopy(scope.version.json_schema),
                fields=copy.deepcopy(scope.version.fields),
                assigners={},
                assigner_graph={},
                aimd=scope.version.aimd,
                meta_data={
                    "id": scope.protocol.uid,
                    "version": "1.0.1",
                    "name": scope.protocol.name,
                },
            )
            async with sessions() as db:
                db.add(second_version)
                await db.commit()
            second_scope = copy.copy(scope)
            second_scope.version = second_version
            valid, _command = await publish_method(sessions, second_scope, saved)
            schema = copy.deepcopy(scope.version.json_schema)
            schema["vars"]["properties"]["value"]["unit"] = "g/L"
            async with sessions() as db:
                await db.execute(
                    update(ProtocolVersion)
                    .where(ProtocolVersion.id == scope.version.id)
                    .values(json_schema=schema)
                )
                await db.commit()
            async with sessions() as db:
                response = Response()
                listing = await api.get_methods(
                    scope.project.id, scope.recorder, db, response
                )
                assert response.headers["Cache-Control"] == "private, no-store"
                assert listing == {
                    "items": [valid],
                    "unavailable": [{"id": stale["id"], "code": "method_unavailable"}],
                }
                assert "Private synthetic method" not in json.dumps(listing)
                assert str(saved["revisions"][0]["id"]) not in json.dumps(listing)
                with pytest.raises(HTTPException) as refused:
                    await get_method(db, scope.recorder, UUID(stale["id"]))
                assert refused.value.status_code == 409
                assert (
                    publication_payload(
                        await get_method(db, scope.recorder, UUID(valid["id"]))
                    )
                    == valid
                )

    asyncio.run(exercise())


def test_protocol_only_v2_graph_prevents_downgrade_and_locks_its_revision_table():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            workflow, _command = await publish_workflow(
                sessions,
                scope,
                WorkflowDraft(
                    project_id=scope.project.id,
                    title="Synthetic v2 Protocol-only graph",
                    graph={
                        "schema_version": 2,
                        "nodes": [workflow_node(scope)],
                        "edges": [],
                        "bindings": [],
                    },
                ),
            )
            async with sessions() as db:
                revision_id = UUID(str(workflow["current_revision"]["id"]))
                revision = await db.get(WorkflowRevision, revision_id)
                assert revision.graph["schema_version"] == 2
                # Previous integration cases may have real method rows. Isolate
                # the actual SQL guard using transaction-local shadow tables,
                # without deleting or modifying any unrelated test assets.
                for name in ("workflow_analysis_methods", "research_analysis_actions"):
                    await db.execute(
                        text(
                            f"CREATE TEMP TABLE {name} (id UUID PRIMARY KEY) ON COMMIT DROP"
                        )
                    )
                    assert await db.scalar(text(f"SELECT COUNT(*) FROM {name}")) == 0
                await db.execute(
                    text(
                        "CREATE TEMP TABLE workflow_revisions (id UUID PRIMARY KEY, graph JSON NOT NULL) ON COMMIT DROP"
                    )
                )
                await db.execute(
                    text(
                        "INSERT INTO workflow_revisions (id, graph) VALUES (:id, CAST(:graph AS JSON))"
                    ),
                    {"id": revision_id, "graph": json.dumps(revision.graph)},
                )
                connection = await db.connection()
                migration = import_module("migrations.versions.0065_workflow_analysis")
                lock_statements = []

                def observe_sql(
                    _connection, _cursor, statement, _parameters, _context, _many
                ):
                    if statement.lstrip().upper().startswith("LOCK TABLE"):
                        lock_statements.append(statement)

                def downgrade(sync_connection):
                    event.listen(sync_connection, "before_cursor_execute", observe_sql)
                    try:
                        with Operations.context(
                            MigrationContext.configure(sync_connection)
                        ):
                            migration.downgrade()
                    finally:
                        event.remove(
                            sync_connection, "before_cursor_execute", observe_sql
                        )

                with pytest.raises(RuntimeError, match="version 2 Workflow graphs"):
                    await connection.run_sync(downgrade)
                # CREATE TEMP TABLE itself also takes a strong lock. Inspect the
                # real executed migration SQL so that cannot mask a missing lock.
                assert any(
                    "workflow_revisions" in statement for statement in lock_statements
                )
                # The refusal's transaction still owns its locks. Without this
                # lock, another connection could insert a v2 graph after the scan.
                assert await db.scalar(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM pg_locks l JOIN pg_class c ON c.oid=l.relation WHERE l.pid=pg_backend_pid() AND c.relname='workflow_revisions' AND c.relnamespace=pg_my_temp_schema() AND l.mode='AccessExclusiveLock' AND l.granted)"
                    )
                )
                await db.rollback()
            async with sessions() as db:
                assert (await db.get(WorkflowRevision, revision_id)).graph[
                    "schema_version"
                ] == 2

    asyncio.run(exercise())


def test_published_method_cannot_be_updated_or_downgraded_away():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            saved, _record = await saved_method(sessions, scope)
            published, _command = await publish_method(sessions, scope, saved)
            async with sessions() as db:
                with pytest.raises(DBAPIError):
                    await db.execute(
                        update(WorkflowAnalysisMethod)
                        .where(WorkflowAnalysisMethod.id == UUID(published["id"]))
                        .values(title="Silently changed")
                    )
                await db.rollback()
            async with sessions() as db:
                connection = await db.connection()
                migration = import_module("migrations.versions.0065_workflow_analysis")

                def downgrade(sync_connection):
                    with Operations.context(
                        MigrationContext.configure(sync_connection)
                    ):
                        migration.downgrade()

                with pytest.raises(RuntimeError, match="Cannot downgrade"):
                    await connection.run_sync(downgrade)
                await db.rollback()

    asyncio.run(exercise())
