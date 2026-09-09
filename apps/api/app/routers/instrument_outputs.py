"""Lease-scoped raw-file delivery, draft assets and explicit Record association."""

import asyncio
import hashlib
import hmac
import tempfile
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.database import DBSession
from app.libs.file_storage import (
    default_storage_backend,
    default_storage_namespace,
    upload_file,
)
from app.models.instrument_output import (
    InstrumentOutput,
    InstrumentOutputAssociation,
    InstrumentOutputBatch,
)
from app.models.knowledge import ResearchFile, ResearchFileBlob
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.record import Record
from app.models.research import ResearchAction, ResearchRun, ResearchTask
from app.models.research_asset import DataAsset, DataAssetVersion
from app.models.research_execution import ResearchInstrumentJob
from app.models.user import User
from app.routers.depends import CurrentUser
from app.routers.permission import check_user_permission
from app.routers.research_instrument_jobs import (
    GatewayToken,
    LeaseToken,
    _authenticate_gateway,
    _gateway_job_context,
)
from app.services.instrument_output_contract import validate_capture
from app.services.instrument_outputs import authorize_intake, batch_rows, batch_snapshot
from app.services.knowledge import (
    assert_research_file_upload_quota,
    authorize_research_file,
)
from app.services.research_runtime import canonical_digest, emit_research_event, utcnow

router = APIRouter(tags=["Instrument files"])
RUNTIME = "/instrument-gateway/v1/jobs/{job_id}/outputs"
PUBLIC = "/research-instrument-jobs/{job_id}/outputs"


class CaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capture: dict


async def _runtime(db, job_id, token, lease):
    gateway = await _authenticate_gateway(db, token)
    job, action, run, task = await _gateway_job_context(
        db, gateway=gateway, job_id=job_id, lease_token=lease
    )
    batch = await db.get(InstrumentOutputBatch, job.id)
    if batch is None:
        raise HTTPException(404, "No file intake was declared for this job")
    actor = await db.get(User, batch.created_by_user_id)
    if actor is None:
        raise HTTPException(403, "File intake authority is unavailable")
    await authorize_intake(db, actor, task)
    if job.status != "completed":
        raise HTTPException(
            409, "Acknowledge instrument execution before delivering files"
        )
    if batch.lineage["destination"]["project_id"] != str(
        task.project_id
    ) or batch.lineage["destination"]["lab_id"] != str(task.lab_id):
        raise HTTPException(409, "The pinned file destination changed")
    return batch, job, action, run, task, actor


async def _public(db, job_id, user, *, write=False):
    job = await db.get(ResearchInstrumentJob, job_id)
    batch = await db.get(InstrumentOutputBatch, job_id)
    action = await db.get(ResearchAction, job.action_id) if job else None
    run = await db.get(ResearchRun, action.run_id) if action else None
    task = await db.get(ResearchTask, run.task_id) if run else None
    if batch is None or task is None:
        raise HTTPException(404, "Instrument output not found")
    await authorize_intake(db, user, task, read=not write)
    return batch, job, action, run, task


@router.post(RUNTIME + "/capture")
async def report_capture(
    job_id: UUID,
    params: CaptureRequest,
    gateway_token: GatewayToken,
    lease_token: LeaseToken,
    db_session: DBSession,
):
    batch, job, action, run, task, actor = await _runtime(
        db_session, job_id, gateway_token, lease_token
    )
    try:
        capture = validate_capture(batch.plan, params.capture)
    except (ValueError, TypeError, KeyError) as error:
        raise HTTPException(422, str(error)) from error
    if batch.capture is not None and batch.capture != capture:
        raise HTTPException(
            409, "Different source files were already fixed to this job"
        )
    if batch.capture is None:
        batch.capture = capture
        await emit_research_event(
            db_session,
            task_id=task.id,
            run_id=run.id,
            action_id=action.id,
            kind="instrument_outputs.captured",
            actor_user_id=None,
            payload={"job_id": str(job.id), "file_count": len(capture["files"])},
            idempotency_key=f"instrument-output:{job.id}:capture",
        )
    snapshot = await batch_snapshot(db_session, batch, user=actor)
    await db_session.commit()
    return snapshot


def _captured(batch, output):
    if batch.capture is None:
        raise HTTPException(409, "A source capture manifest is required before upload")
    item = next(
        (item for item in batch.capture["files"] if item["name"] == output.name), None
    )
    if item is None:
        raise HTTPException(404, "This output was not captured")
    return item


async def _registered(db, output, actor):
    file = await db.get(ResearchFile, output.research_file_id)
    if file is None or file.archived_at:
        raise HTTPException(409, "Previously registered output is unavailable")
    await authorize_research_file(db, actor, file)
    version = await db.get(DataAssetVersion, output.data_asset_version_id)
    return {
        "status": "registered",
        "output_id": str(output.id),
        "research_file_id": str(file.id),
        "data_asset_id": str(version.data_asset_id),
        "data_asset_version_id": str(version.id),
        "sha256": version.checksum,
        "byte_size": version.byte_size,
    }


@router.put(RUNTIME + "/{output_id}")
async def receive_file(
    job_id: UUID,
    output_id: UUID,
    request: Request,
    gateway_token: GatewayToken,
    lease_token: LeaseToken,
    db_session: DBSession,
    content_length: Annotated[int, Header(alias="Content-Length", ge=0)],
    checksum: Annotated[
        str, Header(alias="X-Airalogy-Content-SHA256", min_length=64, max_length=64)
    ],
    content_type: Annotated[
        str, Header(alias="Content-Type", min_length=3, max_length=128)
    ],
):
    batch, job, action, run, task, actor = await _runtime(
        db_session, job_id, gateway_token, lease_token
    )
    output = await db_session.get(InstrumentOutput, output_id)
    if output is None or output.job_id != job.id:
        raise HTTPException(404, "Output was not declared for this job")
    expected = _captured(batch, output)
    if (content_length, checksum, content_type) != (
        expected["byte_size"],
        expected["sha256"],
        expected["media_type"],
    ):
        raise HTTPException(409, "Upload headers differ from the pinned capture")
    if output.research_file_id:
        result = await _registered(db_session, output, actor)
        await db_session.commit()
        return result
    await assert_research_file_upload_quota(db_session, actor.id, content_length)
    # No database lock is held while a station sends bytes. Reauthorize after
    # streaming and again before committing the logical, scope-bearing file.
    await db_session.commit()
    received, observed = 0, hashlib.sha256()
    with tempfile.SpooledTemporaryFile(max_size=8 * 1024**2, mode="w+b") as staged:
        try:
            async with asyncio.timeout(900):
                async for chunk in request.stream():
                    received += len(chunk)
                    if received > content_length:
                        raise HTTPException(413, "Upload exceeded its pinned size")
                    observed.update(chunk)
                    staged.write(chunk)
        except TimeoutError as error:
            raise HTTPException(
                408, "File upload exceeded its receiving window; retry the same file"
            ) from error
        if received != content_length or not hmac.compare_digest(
            observed.hexdigest(), checksum
        ):
            raise HTTPException(
                422, "Raw file content does not match its captured digest and size"
            )
        # Instrument outputs are untrusted binary attachments, never inline HTML
        # or automatically extracted PDFs. Preserve declared media type on the
        # immutable DataAsset version, not as permission to execute/preview bytes.
        db_session.expire_all()
        batch, job, action, run, task, actor = await _runtime(
            db_session, job_id, gateway_token, lease_token
        )
        output = await db_session.get(InstrumentOutput, output_id)
        if _captured(batch, output) != expected:
            raise HTTPException(409, "Capture changed while receiving data")
        if output.research_file_id:
            result = await _registered(db_session, output, actor)
            await db_session.commit()
            return result
        # Serialize instrument uploads by quota owner, including across Gateways.
        await db_session.scalar(
            select(User.id).where(User.id == actor.id).with_for_update()
        )
        await assert_research_file_upload_quota(db_session, actor.id, content_length)
        blob = await db_session.scalar(
            select(ResearchFileBlob).where(ResearchFileBlob.checksum_sha256 == checksum)
        )
        if blob is None:
            object_key = f"knowledge/blobs/{checksum[:2]}/{checksum}"
            staged.seek(0)
            await upload_file(
                object_key,
                staged,
                content_type="application/octet-stream",
                length=content_length,
            )
            inserted = await db_session.scalar(
                insert(ResearchFileBlob)
                .values(
                    checksum_sha256=checksum,
                    content_type="application/octet-stream",
                    size_bytes=content_length,
                    storage_backend=default_storage_backend(),
                    storage_namespace=default_storage_namespace(),
                    storage_object_key=object_key,
                    extracted_text="",
                )
                .on_conflict_do_nothing(index_elements=["checksum_sha256"])
                .returning(ResearchFileBlob.id)
            )
            blob = (
                await db_session.get(ResearchFileBlob, inserted)
                if inserted
                else await db_session.scalar(
                    select(ResearchFileBlob).where(
                        ResearchFileBlob.checksum_sha256 == checksum
                    )
                )
            )
        if blob.size_bytes != content_length:
            raise HTTPException(409, "Stored output content has conflicting metadata")
        blob_id = blob.id
        db_session.expire_all()
        batch, job, action, run, task, actor = await _runtime(
            db_session, job_id, gateway_token, lease_token
        )
        output = await db_session.get(InstrumentOutput, output_id)
        if _captured(batch, output) != expected:
            raise HTTPException(409, "Capture changed during storage")
        now = utcnow()
        file = ResearchFile(
            blob_id=blob_id,
            filename=output.name,
            scope_type="project",
            owner_user_id=None,
            lab_id=task.lab_id,
            project_id=task.project_id,
            visibility="project",
            uploaded_by_user_id=actor.id,
        )
        db_session.add(file)
        await db_session.flush()
        asset = DataAsset(
            lab_id=task.lab_id,
            project_id=task.project_id,
            task_id=task.id,
            name=output.name,
            description="Captured instrument file; scientific review and Record association are pending.",
            kind="file",
            status="draft",
            current_version=1,
            created_by_user_id=actor.id,
        )
        db_session.add(asset)
        await db_session.flush()
        version = DataAssetVersion(
            data_asset_id=asset.id,
            version=1,
            research_file_id=file.id,
            external_uri="",
            media_type=content_type,
            checksum=checksum,
            byte_size=content_length,
            data_schema={},
            version_metadata={**expected, "received_at": now.isoformat()},
            source={
                **batch.lineage,
                "output_id": str(output.id),
                "capture_digest": canonical_digest(batch.capture),
            },
            change_summary="Original checksum-verified instrument file; not validated scientific evidence",
            created_by_user_id=actor.id,
        )
        db_session.add(version)
        await db_session.flush()
        output.research_file_id, output.data_asset_version_id, output.received_at = (
            file.id,
            version.id,
            now,
        )
        await emit_research_event(
            db_session,
            task_id=task.id,
            run_id=run.id,
            action_id=action.id,
            kind="instrument_output.registered",
            actor_user_id=None,
            payload={
                "job_id": str(job.id),
                "output_id": str(output.id),
                "data_asset_id": str(asset.id),
            },
            idempotency_key=f"instrument-output:{output.id}:registered",
        )
        result = await _registered(db_session, output, actor)
        await db_session.commit()
        return result


@router.post(RUNTIME + "/finalize")
async def finalize_delivery(
    job_id: UUID,
    params: CaptureRequest,
    gateway_token: GatewayToken,
    lease_token: LeaseToken,
    db_session: DBSession,
):
    batch, job, action, run, task, actor = await _runtime(
        db_session, job_id, gateway_token, lease_token
    )
    if batch.capture is None or batch.capture != params.capture:
        raise HTTPException(409, "Finalize exactly the pinned source capture")
    for output in await batch_rows(db_session, batch):
        if output.name in {item["name"] for item in batch.capture["files"]}:
            if not output.research_file_id:
                raise HTTPException(
                    409, "Required captured files have not all been registered"
                )
            await _registered(db_session, output, actor)
    if not batch.finalized_at:
        batch.finalized_at = utcnow()
        from app.routers.research_instrument_jobs import finish_instrument_action

        await finish_instrument_action(
            db_session,
            job,
            action,
            run,
            task,
            outputs=await batch_snapshot(db_session, batch, user=actor),
        )
        await emit_research_event(
            db_session,
            task_id=task.id,
            run_id=run.id,
            action_id=action.id,
            kind="instrument_outputs.delivered",
            actor_user_id=None,
            payload={"job_id": str(job.id)},
            idempotency_key=f"instrument-output:{job.id}:delivered",
        )
    result = await batch_snapshot(db_session, batch, user=actor)
    await db_session.commit()
    return result


async def _record(db, task, user, record_id, version):
    record = await db.get(Record, (record_id, version))
    protocol = await db.get(Protocol, record.protocol_id) if record else None
    if (
        record is None
        or record.deleted_at
        or protocol is None
        or protocol.project_id != task.project_id
        or protocol.deleted_at
    ):
        raise HTTPException(404, "Record not found")
    project = await db.get(Project, task.project_id)
    try:
        await check_user_permission(
            db, project, user, "read_record", protocol=protocol, record=record
        )
    except HTTPException as error:
        raise HTTPException(404, "Record not found") from error
    return record, protocol


@router.get(PUBLIC)
async def list_outputs(job_id: UUID, current_user: CurrentUser, db_session: DBSession):
    batch, _job, _action, _run, task = await _public(db_session, job_id, current_user)
    result = await batch_snapshot(db_session, batch, user=current_user)
    for item in result["items"]:
        association = await db_session.scalar(
            select(InstrumentOutputAssociation)
            .where(InstrumentOutputAssociation.output_id == UUID(item["id"]))
            .order_by(InstrumentOutputAssociation.revision.desc())
            .limit(1)
        )
        item["association"] = None
        if association:
            try:
                record, protocol = await _record(
                    db_session,
                    task,
                    current_user,
                    association.record_id,
                    association.record_version,
                )
                item["association"] = {
                    "id": str(association.id),
                    "state": "associated",
                    "record_id": str(record.id),
                    "record_version": record.version,
                    "protocol_id": str(protocol.id),
                    "sample_reference": association.sample_reference,
                }
            except HTTPException:
                item["association"] = {"id": str(association.id), "state": "restricted"}
    return result


class AssociationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    record_id: UUID
    record_version: int = Field(ge=1, strict=True)
    sample_reference: str = Field(default="", max_length=1024)
    expected_association_id: UUID | None = None


class AssociationConfirm(AssociationDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


async def _association_preview(db, user, job_id, output_id, params, *, confirm=False):
    _batch, job, action, run, task = await _public(db, job_id, user, write=True)
    output = await db.scalar(
        select(InstrumentOutput)
        .where(InstrumentOutput.id == output_id, InstrumentOutput.job_id == job_id)
        .with_for_update()
    )
    if output is None or not output.research_file_id:
        raise HTTPException(404, "Registered instrument output not found")
    await _registered(db, output, user)
    # Recheck idempotency after the output lock, including concurrent retries.
    existing = await db.get(InstrumentOutputAssociation, params.id) if confirm else None
    record, protocol = await _record(
        db, task, user, params.record_id, params.record_version
    )
    previous = await db.scalar(
        select(InstrumentOutputAssociation)
        .where(InstrumentOutputAssociation.output_id == output.id)
        .order_by(InstrumentOutputAssociation.revision.desc())
        .limit(1)
    )
    if (
        existing is None
        and (previous.id if previous else None) != params.expected_association_id
    ):
        raise HTTPException(
            409, "Output association changed; refresh and preview again"
        )
    command = {
        **params.model_dump(mode="json", exclude={"preview_digest"}),
        "output_id": str(output.id),
        "data_asset_version_id": str(output.data_asset_version_id),
        "record_hash": record.hash,
        "protocol_id": str(protocol.id),
        "protocol_version": record.protocol_version,
        "actor_id": str(user.id),
        "association_revision": existing.revision
        if existing
        else (previous.revision + 1 if previous else 1),
    }
    return command, output, (job, action, run, task), existing


@router.post(PUBLIC + "/{output_id}/associations/preview")
async def preview_association(
    job_id: UUID,
    output_id: UUID,
    params: AssociationDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    command, _output, _context, _existing = await _association_preview(
        db_session, current_user, job_id, output_id, params
    )
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "effects": [
            "Associate the original captured DataAsset version with this exact Record version",
            "Preserve existing Record data and prior associations; no Record submission or scientific validation",
        ],
    }


@router.post(PUBLIC + "/{output_id}/associations")
async def confirm_association(
    job_id: UUID,
    output_id: UUID,
    params: AssociationConfirm,
    current_user: CurrentUser,
    db_session: DBSession,
):
    command, output, (_job, action, run, task), existing = await _association_preview(
        db_session, current_user, job_id, output_id, params, confirm=True
    )
    expected = canonical_digest(command)
    if params.preview_digest != expected:
        raise HTTPException(409, "Record association preview changed")
    if existing:
        if existing.output_id != output.id or existing.confirmation_digest != expected:
            raise HTTPException(
                409, "Association identifier already belongs to a different request"
            )
        return {"id": str(existing.id), "state": "associated"}
    row = InstrumentOutputAssociation(
        id=params.id,
        revision=command["association_revision"],
        output_id=output.id,
        record_id=params.record_id,
        record_version=params.record_version,
        record_hash=command["record_hash"],
        sample_reference=params.sample_reference,
        confirmation_digest=expected,
        created_by_user_id=current_user.id,
    )
    # UUID reuse across outputs must produce a conflict rather than a DB error.
    inserted = await db_session.scalar(
        insert(InstrumentOutputAssociation)
        .values(
            id=row.id,
            revision=row.revision,
            output_id=row.output_id,
            record_id=row.record_id,
            record_version=row.record_version,
            record_hash=row.record_hash,
            sample_reference=row.sample_reference,
            confirmation_digest=row.confirmation_digest,
            created_by_user_id=row.created_by_user_id,
            created_at=utcnow(),
        )
        .on_conflict_do_nothing(index_elements=["id"])
        .returning(InstrumentOutputAssociation.id)
    )
    if inserted is None:
        raise HTTPException(409, "Association identifier belongs to another request")
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="instrument_output.associated",
        actor_user_id=current_user.id,
        payload={"output_id": str(output.id), "association_id": str(row.id)},
        idempotency_key=f"instrument-output-association:{row.id}",
    )
    await db_session.commit()
    return {"id": str(row.id), "state": "associated"}
