"""Real persisted private attachment receipts, managed storage and live ACLs.

Run only in the shared isolated research-integration stack. No permission,
metadata, checksum, preview, confirmation or storage implementation is mocked.
"""

import asyncio
import json
import os
from importlib import import_module
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError

from app.config import config
from app.libs.lab_force_delete import _delete_lab_analysis_input_file_references
from app.models.airalogy_file import AiralogyFile
from app.models.analysis_compute import AnalysisCompute, AnalysisComputeInputFile
from app.models.knowledge import ResearchFileBlob
from app.models.project import Project, ProjectRole, ProjectType, ProjectUser
from app.models.record import Record
from app.models.research_asset import DataAsset
from app.models.research_execution import ResearchComputeJobInput
from app.models.workflow_file import WorkflowFileBinding
from app.services.analysis_compute import analysis_compute_input_bytes, owned_compute
from app.services.analysis_compute_contracts import AnalysisComputeDraft
from app.services.analysis_compute_files import (
    authorize_preview_input_files,
    manifest_bytes,
    sealed_input_file,
)
from app.services.record_analyses import owned_run
from app.services.workflow_files import verified_blob_spool
from tests.test_record_analysis_compute_postgres import (
    compute_draft,
    confirm,
    count_runs_and_jobs,
    preview,
    seed_compute,
)
from tests.test_record_analysis_postgres import database, seed_analysis
from tests.test_workflow_files_postgres import (
    file_record,
    file_schema,
    revoke_source,
    setup_files,
    source_upload,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("RESOURCE_TEST_DATABASE_URL"),
    reason="Use the isolated migrated research-integration database and storage",
)


@pytest.fixture(autouse=True)
def no_ai(monkeypatch):
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")
    monkeypatch.setattr(config, "AI_ENABLED", False)


def attachment_draft(scope, compute, *, selection=None):
    params = compute_draft(scope, compute).model_dump(mode="json")
    params["recipe"]["input_files"] = [
        {"input_id": "observations", "field_path": ["var", "attachment"]}
    ]
    if selection is not None:
        params["selection"] = selection
    return AnalysisComputeDraft.model_validate(params)


async def fixture(sessions, *, count=2):
    scope = await seed_analysis(sessions, public=True)
    await file_schema(sessions, scope)
    compute = await seed_compute(sessions, scope)
    records, uploads, bodies = [], [], []
    for index in range(count):
        body = json.dumps({"value": index + 1, "synthetic": uuid4().hex}).encode()
        uploaded = await source_upload(sessions, scope, content=body)
        records.append(
            await file_record(
                sessions,
                scope,
                {"attachment": uploaded["airalogy_file_id"]},
                number=index + 1,
            )
        )
        uploads.append(uploaded)
        bodies.append(body)
    return scope, compute, records, uploads, bodies


async def receipts(sessions, run_id):
    async with sessions() as db:
        return list(
            (
                await db.scalars(
                    select(AnalysisComputeInputFile).where(
                        AnalysisComputeInputFile.analysis_run_id == run_id
                    )
                )
            ).all()
        )


def test_managed_attachments_preview_without_blob_writes_concurrent_confirm_and_exact_bytes():
    async def exercise():
        async with database() as sessions:
            sessions.configure(autoflush=False)
            scope, compute, records, _, bodies = await fixture(sessions)
            async with sessions() as db:
                before_blobs = await db.scalar(
                    select(func.count()).select_from(ResearchFileBlob)
                )
            draft = await preview(sessions, scope, attachment_draft(scope, compute))
            manifest = draft.summary["compute"]["input_files"]
            assert manifest["count"] == 2
            assert manifest["total_bytes"] == sum(map(len, bodies))
            async with sessions() as db:
                assert (
                    await db.scalar(select(func.count()).select_from(ResearchFileBlob))
                    == before_blobs
                )
            assert await count_runs_and_jobs(sessions, scope) == (0, 0)
            first, replay = await asyncio.gather(
                confirm(sessions, scope, draft, key="synthetic-attachment-one"),
                confirm(sessions, scope, draft, key="synthetic-attachment-two"),
            )
            assert first.id == replay.id
            assert await count_runs_and_jobs(sessions, scope) == (1, 1)
            async with sessions() as db:
                analysis, details, job = await owned_compute(
                    db, first.id, scope.analyst
                )
                inputs = list(
                    (
                        await db.scalars(
                            select(ResearchComputeJobInput)
                            .where(ResearchComputeJobInput.compute_job_id == job.id)
                            .order_by(ResearchComputeJobInput.position)
                        )
                    ).all()
                )
                assert [item.position for item in inputs] == [1, 2, 3, 4]
                assert (
                    inputs[0].mount_name == "records.json"
                    and inputs[1].mount_name == "attachments.json"
                )
                assert details.input_file_manifest == manifest
                assert "input_files" not in analysis.source_snapshot
                assert "attachments" not in analysis.source_snapshot
                assert (
                    json.loads(analysis_compute_input_bytes(analysis))
                    == analysis.source_snapshot
                )
                safe = manifest_bytes(manifest)
                assert (
                    b"storage_object_key" not in safe
                    and b"storage_namespace" not in safe
                )
                assert all(
                    item.data_asset_id is None and item.data_asset_version_id is None
                    for item in inputs
                )
                expected = {
                    str(record.id): body
                    for record, body in zip(records, bodies, strict=True)
                }
                for item in inputs[2:]:
                    receipt, blob = await sealed_input_file(db, analysis, item)
                    handle = await verified_blob_spool(blob)
                    try:
                        assert handle.read() == expected[str(receipt.record_id)]
                    finally:
                        handle.close()
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(DataAsset)
                        .where(DataAsset.project_id == scope.project.id)
                    )
                    == 0
                )
            assert len(await receipts(sessions, first.id)) == 2

    asyncio.run(exercise())


def test_missing_record_attachment_and_stale_metadata_never_drop_samples_or_confirm():
    async def exercise():
        async with database() as sessions:
            scope, compute, records, uploaded, _ = await fixture(sessions)
            params = attachment_draft(scope, compute)
            draft = await preview(sessions, scope, params)
            async with sessions() as db:
                file = await db.get(AiralogyFile, UUID(str(uploaded[0]["id"])))
                file.filename = "renamed.json"
                await db.commit()
            with pytest.raises(HTTPException) as stale:
                await confirm(sessions, scope, draft)
            assert stale.value.status_code == 409
            assert await count_runs_and_jobs(sessions, scope) == (0, 0)
            async with sessions() as db:
                source = await db.get(Record, (records[0].id, records[0].version))
                source.data = {"var": {"value": 9, "group": "A", "attachment": None}}
                await db.commit()
            with pytest.raises(HTTPException) as missing:
                await preview(sessions, scope, params)
            assert missing.value.status_code == 409
            assert await count_runs_and_jobs(sessions, scope) == (0, 0)

    asyncio.run(exercise())


def test_receipt_source_blob_manifest_and_job_inputs_are_database_immutable():
    async def exercise():
        async with database() as sessions:
            scope, compute, _, _, _ = await fixture(sessions, count=1)
            draft = await preview(sessions, scope, attachment_draft(scope, compute))
            analysis = await confirm(sessions, scope, draft)
            receipt = (await receipts(sessions, analysis.id))[0]
            statements = [
                update(AnalysisComputeInputFile)
                .where(AnalysisComputeInputFile.input_row_id == receipt.input_row_id)
                .values(digest="a" * 64),
                update(AnalysisCompute)
                .where(AnalysisCompute.analysis_run_id == analysis.id)
                .values(input_file_manifest={}),
                update(AiralogyFile)
                .where(AiralogyFile.id == receipt.source_file_id)
                .values(filename="mutated.json"),
                update(ResearchFileBlob)
                .where(ResearchFileBlob.id == receipt.blob_id)
                .values(storage_object_key="mutated/path"),
                update(ResearchComputeJobInput)
                .where(ResearchComputeJobInput.id == receipt.input_row_id)
                .values(mount_name="mutated.json"),
            ]
            for statement in statements:
                async with sessions() as db:
                    with pytest.raises(DBAPIError):
                        await db.execute(statement)
                        await db.commit()
                    await db.rollback()
            async with sessions() as db:
                await owned_compute(db, analysis.id, scope.analyst)
                # The exact-scope cleanup is transactional and never deletes blobs.
                await _delete_lab_analysis_input_file_references(db, scope.lab.id)
                assert await db.get(ResearchFileBlob, receipt.blob_id) is not None
                await db.rollback()
            assert len(await receipts(sessions, analysis.id)) == 1

    asyncio.run(exercise())


def test_exact_attachment_sources_are_rechecked_for_readers_approver_and_owner():
    async def exercise():
        async with database() as sessions:
            scope, compute, records, _, _ = await fixture(sessions)
            draft = await preview(sessions, scope, attachment_draft(scope, compute))
            analysis = await confirm(sessions, scope, draft)
            async with sessions() as db:
                # Public source access does not publish this user's private run.
                await authorize_preview_input_files(
                    db,
                    analysis.source_snapshot,
                    draft.summary["compute"]["input_files"],
                    scope.outsider,
                )
                with pytest.raises(HTTPException) as outsider:
                    await owned_run(db, analysis.id, scope.outsider)
                assert outsider.value.status_code == 404
            async with sessions() as db:
                role = await db.scalar(
                    select(ProjectUser).where(
                        ProjectUser.project_id == scope.project.id,
                        ProjectUser.user_id == scope.analyst.id,
                    )
                )
                role.role = ProjectRole.RECORDER_SELF_ONLY
                await db.commit()
            async with sessions() as db:
                with pytest.raises(HTTPException) as owner_denied:
                    await owned_run(db, analysis.id, scope.analyst)
                assert owner_denied.value.status_code == 403
            async with sessions() as db:
                project = await db.get(Project, scope.project.id)
                project.type = ProjectType.PRIVATE
                await db.commit()
            async with sessions() as db:
                with pytest.raises(HTTPException) as private_source:
                    await authorize_preview_input_files(
                        db,
                        analysis.source_snapshot,
                        draft.summary["compute"]["input_files"],
                        scope.outsider,
                    )
                assert private_source.value.status_code in {400, 403}
            # Deleting a source Record logically is allowed, but even the Lab
            # Owner cannot read its dependent attachment analysis after that.
            await revoke_source(sessions, records[0])
            async with sessions() as db:
                with pytest.raises(HTTPException):
                    await authorize_preview_input_files(
                        db,
                        analysis.source_snapshot,
                        draft.summary["compute"]["input_files"],
                        scope.owner,
                    )

    asyncio.run(exercise())


def test_previously_bound_alias_reuses_blob_and_retains_original_source_acl():
    async def exercise():
        async with database() as sessions:
            scope, _, actions, original, _ = await setup_files(sessions)
            alias_value = actions["next"].input_data["initial_values"]["attachment"]
            selected = await file_record(
                sessions, scope, {"attachment": alias_value}, number=2
            )
            compute = await seed_compute(sessions, scope)
            params = attachment_draft(
                scope,
                compute,
                selection={
                    "mode": "selected",
                    "records": [{"id": str(selected.id), "version": selected.version}],
                },
            )
            draft = await preview(sessions, scope, params, user=scope.owner)
            analysis = await confirm(sessions, scope, draft, user=scope.owner)
            receipt = (await receipts(sessions, analysis.id))[0]
            async with sessions() as db:
                alias = await db.get(WorkflowFileBinding, receipt.source_file_id)
                assert alias is not None and alias.blob_id == receipt.blob_id
                assert receipt.source_metadata["binding_digest"] == alias.digest
                await owned_compute(db, analysis.id, scope.owner)
            await revoke_source(sessions, original)
            async with sessions() as db:
                with pytest.raises(HTTPException):
                    await owned_compute(db, analysis.id, scope.owner)
            assert len(await receipts(sessions, analysis.id)) == 1

    asyncio.run(exercise())


def test_actual_downgrade_refuses_attachment_contracts_and_rolls_back():
    async def exercise():
        async with database() as sessions:
            scope, compute, _, _, _ = await fixture(sessions, count=1)
            draft = await preview(sessions, scope, attachment_draft(scope, compute))
            async with sessions() as db:
                version_before = await db.scalar(
                    text("SELECT version_num FROM alembic_version")
                )
                connection = await db.connection()
                migration = import_module(
                    "migrations.versions.0069_analysis_compute_input_files"
                )

                def downgrade(sync_connection):
                    with Operations.context(
                        MigrationContext.configure(sync_connection)
                    ):
                        migration.downgrade()

                with pytest.raises(RuntimeError, match="Cannot downgrade"):
                    await connection.run_sync(downgrade)
                await db.rollback()
                assert (
                    await db.scalar(text("SELECT version_num FROM alembic_version"))
                    == version_before
                )
                # Actual protected tables/columns still exist after rollback,
                # and the newly sealed preview has not been removed or changed.
                await db.execute(select(AnalysisCompute.input_file_manifest).limit(1))
                await db.execute(select(AnalysisComputeInputFile.input_row_id).limit(1))
                assert await db.scalar(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM analysis_previews WHERE id = :identity AND COALESCE(recipe->'input_files', '[]'::json)::jsonb <> '[]'::jsonb)"
                    ),
                    {"identity": draft.id},
                )

    asyncio.run(exercise())
