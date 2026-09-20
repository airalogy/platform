"""Migrated immutable asset receipts and exclusive source-kind bindings."""

import asyncio
import os
from importlib import import_module

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from app.config import config
from app.models.knowledge import ResearchFile, ResearchFileBlob
from app.models.research_asset import DataAssetVersion
from app.models.workflow_asset import WorkflowRunAssetInput
from app.models.workflow_file import WorkflowFileBinding
from app.services.workflow_definitions import WorkflowDraft
from tests.test_record_analysis_postgres import database, seed_analysis
from tests.test_workflow_definitions_postgres import node, publish

pytestmark = pytest.mark.skipif(
    not os.environ.get("RESOURCE_TEST_DATABASE_URL"),
    reason="Dedicated migrated PostgreSQL is required for immutable asset inputs",
)


@pytest.fixture(autouse=True)
def deterministic_no_ai(monkeypatch):
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")
    monkeypatch.setattr(config, "AI_ENABLED", False)


def test_workflow_asset_0071_columns_and_exclusive_source_foreign_keys():
    async def scenario():
        async with database() as sessions, sessions() as db:
            connection = await db.connection()

            def structure(connection):
                inspector = inspect(connection)
                return {
                    model.__tablename__: {
                        "columns": inspector.get_columns(model.__tablename__),
                        "foreign_keys": inspector.get_foreign_keys(model.__tablename__),
                        "checks": inspector.get_check_constraints(model.__tablename__),
                    }
                    for model in (WorkflowRunAssetInput, WorkflowFileBinding)
                }

            actual = await connection.run_sync(structure)
            for model in (WorkflowRunAssetInput, WorkflowFileBinding):
                columns = {
                    row["name"]: row for row in actual[model.__tablename__]["columns"]
                }
                assert set(columns) == set(model.__table__.c.keys())
                for name, column in model.__table__.c.items():
                    assert columns[name]["nullable"] == column.nullable
            aliases = actual["workflow_file_bindings"]
            source = next(
                row["sqltext"]
                for row in aliases["checks"]
                if row["name"] == "ck_workflow_file_source"
            )
            assert (
                "source_action_id IS NULL" in source
                and "asset_input_id IS NOT NULL" in source
            )
            assert (
                "source_action_id IS NOT NULL" in source
                and "asset_input_id IS NULL" in source
            )
            fk = next(
                row
                for row in aliases["foreign_keys"]
                if row["constrained_columns"] == ["asset_input_id"]
            )
            assert (
                fk["referred_table"] == "workflow_run_asset_inputs"
                and fk["options"]["ondelete"] == "RESTRICT"
            )
            triggers = (
                (
                    await db.execute(
                        text(
                            "SELECT tgname FROM pg_trigger WHERE tgrelid='workflow_run_asset_inputs'::regclass AND NOT tgisinternal"
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert "immutable_workflow_run_asset_inputs" in triggers

    asyncio.run(scenario())


def test_workflow_asset_0071_downgrade_refuses_unexecuted_asset_capable_graph():
    async def scenario():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            workflow, _ = await publish(
                sessions,
                scope,
                WorkflowDraft(
                    project_id=scope.project.id,
                    title="Immutable asset-capable template",
                    graph={
                        "schema_version": 5,
                        "nodes": [node(scope)],
                        "edges": [],
                        "asset_inputs": [{"input_id": "data", "label": "Measurement"}],
                        "asset_bindings": [
                            {
                                "binding_id": "dose",
                                "input_id": "data",
                                "source_path": ["json", "value"],
                                "target_node_id": "first",
                                "target_path": ["var", "value"],
                                "value_type": "number",
                                "unit": "mg/L",
                            }
                        ],
                    },
                ),
            )
            assert workflow["current_revision"]["graph"]["schema_version"] == 5
            async with sessions() as db:
                connection = await db.connection()

                def downgrade(connection):
                    with Operations.context(MigrationContext.configure(connection)):
                        import_module(
                            "migrations.versions.0071_workflow_asset_inputs"
                        ).downgrade()

                with pytest.raises(RuntimeError, match="Cannot downgrade"):
                    await connection.run_sync(downgrade)
                await db.rollback()
                assert await db.scalar(
                    text("SELECT to_regclass('workflow_run_asset_inputs')")
                )

    asyncio.run(scenario())


def test_workflow_asset_0071_sources_freeze_identity_but_not_access_or_extraction():
    from tests.test_workflow_asset_runtime_postgres import managed_json, setup, start

    async def scenario():
        async with database() as sessions:
            case = await setup(sessions)
            # Unreferenced logical sources retain their ordinary edit lifecycle.
            async with sessions() as db:
                version = await db.get(DataAssetVersion, case.stored.version_id)
                version.change_summary = "Updated before confirmation"
                file = await db.get(ResearchFile, case.stored.file.id)
                file.filename = "renamed-before-confirmation.json"
                await db.commit()
            await start(sessions, case)
            for statement, identity, value, message in (
                (
                    "UPDATE data_asset_versions SET metadata=CAST(:value AS json) WHERE id=:id",
                    case.stored.version_id,
                    '{"changed":true}',
                    "Workflow DataAsset version metadata is immutable",
                ),
                (
                    "UPDATE research_files SET filename=:value WHERE id=:id",
                    case.stored.file.id,
                    "changed-after-confirmation.json",
                    "Workflow DataAsset file metadata is immutable",
                ),
                (
                    "UPDATE research_file_blobs SET storage_object_key=:value WHERE id=:id",
                    case.stored.blob.id,
                    "changed-after-confirmation",
                    "Workflow DataAsset blob metadata is immutable",
                ),
            ):
                async with sessions() as db:
                    with pytest.raises(DBAPIError, match=message):
                        await db.execute(
                            text(statement), {"id": identity, "value": value}
                        )
                    await db.rollback()
            async with sessions() as db:
                await db.execute(
                    text(
                        "UPDATE research_file_blobs SET extracted_text='New searchable text' WHERE id=:id"
                    ),
                    {"id": case.stored.blob.id},
                )
                await db.execute(
                    text(
                        "UPDATE research_files SET visibility='restricted', archived_at=now() WHERE id=:id"
                    ),
                    {"id": case.stored.file.id},
                )
                await db.commit()
                blob = await db.get(ResearchFileBlob, case.stored.blob.id)
                file = await db.get(ResearchFile, case.stored.file.id)
                assert blob.extracted_text == "New searchable text"
                assert file.visibility == "restricted" and file.archived_at is not None
            other = await managed_json(sessions, case.scope)
            async with sessions() as db:
                file = await db.get(ResearchFile, other.file.id)
                file.filename = "still-unbound.json"
                await db.commit()
                assert file.filename == "still-unbound.json"

    asyncio.run(scenario())
