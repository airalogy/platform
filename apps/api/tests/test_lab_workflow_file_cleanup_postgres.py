"""Real FK lifecycle and rollback evidence for scoped Workflow alias cleanup.

This tests the new cleanup boundary, not broad Research asset hard deletion.
The latter has existing RESTRICT edges and must roll back rather than lose
lineage if an explicit Lab hard-delete cannot complete.
"""

import asyncio
import os
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.config import config
from app.libs.lab_force_delete import (
    _delete_lab_from_database,
    _delete_lab_workflow_file_references,
    collect_lab_force_delete_manifest,
)
from app.models.airalogy_file import AiralogyFile
from app.models.knowledge import ResearchFileBlob
from app.models.record_export import RecordExport
from app.models.workflow_file import WorkflowFileBinding, WorkflowFileExportReference
from tests.test_record_analysis_postgres import database, seed_analysis
from tests.test_workflow_definitions_postgres import (
    actions_by_node,
    create_task,
    draft,
    edge,
    node,
    publish,
    start_workflow,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("RESOURCE_TEST_DATABASE_URL"),
    reason="Use the isolated migrated research-integration database",
)


@pytest.fixture(autouse=True)
def no_ai(monkeypatch):
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")
    monkeypatch.setattr(config, "AI_ENABLED", False)


async def fixture(sessions, *, shared_blob=None):
    scope = await seed_analysis(sessions)
    workflow, _ = await publish(
        sessions,
        scope,
        draft(
            scope,
            nodes=[node(scope, "source"), node(scope, "target")],
            edges=[edge("source", "target")],
        ),
    )
    task = await create_task(sessions, scope)
    run, _ = await start_workflow(sessions, scope, workflow, task)
    actions = await actions_by_node(sessions, run["run_id"])
    async with sessions() as db:
        blob = shared_blob
        if blob is None:
            blob = ResearchFileBlob(
                id=uuid4(),
                checksum_sha256=uuid4().hex + uuid4().hex,
                content_type="text/csv",
                size_bytes=5,
                storage_backend="minio",
                storage_object_key=f"synthetic-shared/{uuid4()}.csv",
            )
            db.add(blob)
            await db.flush()
        source = AiralogyFile(
            id=uuid4(),
            filename="source.csv",
            protocol_id=scope.protocol.id,
            project_id=scope.project.id,
            user_id=scope.owner.id,
            storage_backend="minio",
        )
        alias = AiralogyFile(
            id=uuid4(),
            filename="alias.csv",
            protocol_id=scope.protocol.id,
            project_id=scope.project.id,
            user_id=scope.owner.id,
            storage_backend="workflow_reference",
        )
        export = RecordExport(
            id=uuid4(),
            lab_id=scope.lab.id,
            scope_type="lab",
            export_format="aira",
            snapshot_at=datetime.now(UTC),
            requested_by_user_id=scope.owner.id,
        )
        db.add_all([source, alias, export])
        await db.flush()
        binding = WorkflowFileBinding(
            file_id=alias.id,
            workflow_revision_id=workflow["current_revision"]["id"],
            task_id=UUID(str(task["id"])),
            run_id=UUID(str(run["run_id"])),
            action_id=actions["target"].id,
            binding_id="synthetic_cleanup",
            source_action_id=actions["source"].id,
            source_file_id=source.id,
            blob_id=blob.id,
            source_kind="record",
            source_ref={},
            snapshot={},
            digest="1" * 64,
            created_by_user_id=scope.owner.id,
        )
        db.add(binding)
        await db.flush()
        db.add(WorkflowFileExportReference(export_id=export.id, file_id=alias.id))
        await db.commit()
    return SimpleNamespace(
        scope=scope,
        blob=blob,
        source=source,
        alias=alias,
        export=export,
        binding=binding,
    )


def test_lab_alias_cleanup_preserves_other_lab_and_shared_blob_and_original_file():
    async def exercise():
        async with database() as sessions:
            first = await fixture(sessions)
            other = await fixture(sessions, shared_blob=first.blob)
            async with sessions() as db:
                await _delete_lab_workflow_file_references(db, first.scope.lab.id)
                await db.commit()
            async with sessions() as db:
                assert await db.get(WorkflowFileBinding, first.alias.id) is None
                assert await db.get(AiralogyFile, first.alias.id) is None
                assert (
                    await db.scalar(
                        select(WorkflowFileExportReference).where(
                            WorkflowFileExportReference.file_id == first.alias.id
                        )
                    )
                    is None
                )
                assert await db.get(AiralogyFile, first.source.id) is not None
                assert await db.get(ResearchFileBlob, first.blob.id) is not None
                assert await db.get(WorkflowFileBinding, other.alias.id) is not None
                assert await db.get(AiralogyFile, other.alias.id) is not None
                assert await db.get(RecordExport, first.export.id) is not None

    asyncio.run(exercise())


def test_foreign_export_reference_blocks_cleanup_without_deleting_any_lineage():
    async def exercise():
        async with database() as sessions:
            first = await fixture(sessions)
            other = await fixture(sessions)
            async with sessions() as db:
                db.add(
                    WorkflowFileExportReference(
                        export_id=other.export.id, file_id=first.alias.id
                    )
                )
                await db.commit()
            async with sessions() as db:
                with pytest.raises(ValueError, match="Another Lab"):
                    await _delete_lab_workflow_file_references(db, first.scope.lab.id)
                await db.rollback()
            async with sessions() as db:
                assert await db.get(WorkflowFileBinding, first.alias.id) is not None
                assert await db.get(WorkflowFileBinding, other.alias.id) is not None
                assert await db.get(AiralogyFile, first.alias.id) is not None

    asyncio.run(exercise())


def test_existing_research_fk_failure_rolls_back_new_alias_cleanup_in_same_transaction():
    async def exercise():
        async with database() as sessions:
            first = await fixture(sessions)
            async with sessions() as db:
                manifest = await collect_lab_force_delete_manifest(db, first.scope.lab)
                with pytest.raises(DBAPIError) as protected:
                    await _delete_lab_from_database(db, first.scope.lab, manifest)
                assert any(
                    table in str(protected.value)
                    for table in ("research_task_protocols", "research_protocol_runs")
                )
                await db.rollback()
            async with sessions() as db:
                # ResearchTaskProtocol -> ProtocolVersion/Protocol is already
                # RESTRICT. This is a known wider hard-delete boundary, not a
                # reason to permanently drop the newly protected file lineage.
                assert await db.get(WorkflowFileBinding, first.alias.id) is not None
                assert await db.get(AiralogyFile, first.alias.id) is not None
                assert (
                    await db.scalar(
                        select(WorkflowFileExportReference).where(
                            WorkflowFileExportReference.file_id == first.alias.id
                        )
                    )
                    is not None
                )
                assert await db.get(ResearchFileBlob, first.blob.id) is not None

    asyncio.run(exercise())
