from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.database import DBSession
from app.libs.file_storage import delete_file
from app.models.lab import Lab, LabRole, LabUser
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.record_export import (
    RecordExport,
    RecordExportAuditAction,
    RecordExportFormat,
    RecordExportScope,
    RecordExportStatus,
)
from app.routers.depends import CurrentUser
from app.services.access_control import resolve_structured_access
from app.services.persistent_jobs import enqueue_job
from app.services.record_exports import (
    RecordExportError,
    add_export_audit,
    preview_record_export,
    record_export_download_url,
    utcnow,
)

router = APIRouter(prefix="/record-exports", tags=["record-exports"])


class RecordExportParams(BaseModel):
    scope_type: Literal["lab", "project", "protocol"]
    lab_id: UUID
    project_id: UUID | None = None
    protocol_id: UUID | None = None
    export_format: Literal["aira", "jsonl", "csv"] = "aira"
    include_revision_history: bool = False
    include_attachments: bool | None = None
    date_from: date | None = None
    date_to: date | None = None
    submitter_user_id: UUID | None = None
    protocol_version: str | None = Field(None, max_length=64)
    record_number: int | None = Field(None, ge=1)
    record_version: int | None = Field(None, ge=1)
    query: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def validate_scope_and_options(self):
        if self.scope_type == RecordExportScope.LAB.value:
            if self.project_id is not None or self.protocol_id is not None:
                raise ValueError("Lab exports cannot target a Project or Protocol")
        elif self.scope_type == RecordExportScope.PROJECT.value:
            if self.project_id is None or self.protocol_id is not None:
                raise ValueError("Project exports require project_id only")
        elif self.project_id is None or self.protocol_id is None:
            raise ValueError("Protocol exports require project_id and protocol_id")
        if self.export_format == RecordExportFormat.CSV.value:
            if self.scope_type != RecordExportScope.PROTOCOL.value:
                raise ValueError("CSV export is only available for a Protocol")
            if self.include_revision_history:
                raise ValueError("CSV export does not include revision history")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from cannot be after date_to")
        return self


class RecordExportCreateParams(RecordExportParams):
    idempotency_key: str | None = Field(None, min_length=8, max_length=128)


async def _resolve_scope_and_authorize(
    db_session: DBSession,
    params: RecordExportParams,
    user_id: UUID,
) -> tuple[Lab, Project | None, Protocol | None]:
    lab = await db_session.get(Lab, params.lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    membership = await LabUser.find_by(
        db_session,
        [LabUser.lab_id == lab.id, LabUser.user_id == user_id],
    )
    is_lab_owner = membership is not None and membership.role == LabRole.OWNER

    if params.scope_type == RecordExportScope.LAB.value:
        if not is_lab_owner:
            raise HTTPException(
                status_code=403,
                detail="Only the Lab Owner can export all Lab Records",
            )
        return lab, None, None

    project = await db_session.get(Project, params.project_id)
    if project is None or project.lab_id != lab.id:
        raise HTTPException(status_code=404, detail="Project not found in Lab")
    access = await resolve_structured_access(
        db_session,
        user_id,
        lab.id,
        project,
        include_legacy=True,
    )
    can_export_project = is_lab_owner or (
        "project_manager" in access.role_keys and access.allows("export_records")
    )
    if not can_export_project:
        raise HTTPException(
            status_code=403,
            detail=(
                "Only the Lab Owner or Project Owner/Manager can export these Records"
            ),
        )

    if params.scope_type == RecordExportScope.PROJECT.value:
        return lab, project, None
    protocol = await db_session.get(Protocol, params.protocol_id)
    if (
        protocol is None
        or protocol.project_id != project.id
        or protocol.deleted_at is not None
    ):
        raise HTTPException(status_code=404, detail="Protocol not found in Project")
    return lab, project, protocol


def _build_export(params: RecordExportParams, user_id: UUID) -> RecordExport:
    include_attachments = (
        params.export_format == RecordExportFormat.AIRA.value
        if params.include_attachments is None
        else params.include_attachments
    )
    if params.export_format != RecordExportFormat.AIRA.value:
        include_attachments = False
    options = {
        key: value
        for key, value in {
            "date_from": params.date_from.isoformat() if params.date_from else None,
            "date_to": params.date_to.isoformat() if params.date_to else None,
            "submitter_user_id": (
                str(params.submitter_user_id) if params.submitter_user_id else None
            ),
            "protocol_version": params.protocol_version,
            "record_number": params.record_number,
            "record_version": params.record_version,
            "query": (
                params.query.strip()
                if params.query and params.query.strip()
                else None
            ),
        }.items()
        if value is not None
    }
    return RecordExport(
        lab_id=params.lab_id,
        project_id=params.project_id,
        protocol_id=params.protocol_id,
        scope_type=params.scope_type,
        export_format=params.export_format,
        include_revision_history=params.include_revision_history,
        include_attachments=include_attachments,
        options=options,
        snapshot_at=utcnow(),
        requested_by_user_id=user_id,
        status=RecordExportStatus.PENDING.value,
    )


def _export_payload(record_export: RecordExport) -> dict:
    progress_percent = (
        round(
            (record_export.progress_current / record_export.progress_total) * 100,
            1,
        )
        if record_export.progress_total
        else 0
    )
    return {
        **record_export.as_dict(),
        "download_available": bool(
            record_export.status == RecordExportStatus.SUCCEEDED.value
            and record_export.output_object_key
            and record_export.expires_at
            and record_export.expires_at > utcnow()
        ),
        "progress_percent": progress_percent,
    }


async def _owned_export(
    db_session: DBSession,
    export_id: UUID,
    user_id: UUID,
) -> RecordExport:
    record_export = await db_session.get(RecordExport, export_id)
    if record_export is None or record_export.requested_by_user_id != user_id:
        raise HTTPException(status_code=404, detail="Record export not found")
    return record_export


async def _reauthorize_export_download(
    db_session: DBSession,
    record_export: RecordExport,
    user_id: UUID,
) -> None:
    # Export ownership alone is insufficient: a Project manager who has since
    # lost access must not be able to mint another download URL.
    params = RecordExportParams(
        scope_type=record_export.scope_type,
        lab_id=record_export.lab_id,
        project_id=record_export.project_id,
        protocol_id=record_export.protocol_id,
        export_format=record_export.export_format,
        include_revision_history=record_export.include_revision_history,
        include_attachments=record_export.include_attachments,
    )
    await _resolve_scope_and_authorize(db_session, params, user_id)


@router.post("/preview")
async def preview_export(
    params: RecordExportParams,
    db_session: DBSession,
    current_user: CurrentUser,
):
    await _resolve_scope_and_authorize(db_session, params, current_user.id)
    record_export = _build_export(params, current_user.id)
    try:
        return await preview_record_export(db_session, record_export)
    except RecordExportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("")
async def create_export(
    params: RecordExportCreateParams,
    db_session: DBSession,
    current_user: CurrentUser,
):
    await _resolve_scope_and_authorize(db_session, params, current_user.id)
    if params.idempotency_key:
        existing = await RecordExport.find_by(
            db_session,
            [
                RecordExport.requested_by_user_id == current_user.id,
                RecordExport.client_idempotency_key == params.idempotency_key,
            ],
        )
        if existing is not None:
            return _export_payload(existing)
    record_export = _build_export(params, current_user.id)
    record_export.client_idempotency_key = params.idempotency_key
    preview = await preview_record_export(db_session, record_export)
    if preview["record_count"] == 0:
        raise HTTPException(
            status_code=400, detail="No Records matched the export scope"
        )
    if (
        params.export_format == RecordExportFormat.CSV.value
        and not preview["csv_eligible"]
    ):
        raise HTTPException(
            status_code=400,
            detail="CSV export requires exactly one Protocol version",
        )

    record_export.progress_total = preview["record_count"]
    record_export.record_count = preview["record_count"]
    record_export.protocol_count = preview["protocol_count"]
    record_export.attachment_count = preview["attachment_count"]
    record_export.attachment_bytes = preview["attachment_bytes"]
    record_export.warnings = preview["warnings"]
    db_session.add(record_export)
    try:
        await db_session.flush()
    except IntegrityError:
        await db_session.rollback()
        if params.idempotency_key:
            existing = await RecordExport.find_by(
                db_session,
                [
                    RecordExport.requested_by_user_id == current_user.id,
                    RecordExport.client_idempotency_key == params.idempotency_key,
                ],
            )
            if existing is not None:
                return _export_payload(existing)
        raise
    await add_export_audit(
        db_session,
        record_export,
        RecordExportAuditAction.REQUESTED,
        actor_user_id=current_user.id,
        details={
            "scope_type": record_export.scope_type,
            "export_format": record_export.export_format,
            "record_count": record_export.record_count,
            "options": record_export.options,
        },
    )
    await enqueue_job(
        db_session,
        kind="record_export",
        lab_id=record_export.lab_id,
        payload={"export_id": str(record_export.id)},
        idempotency_key=(
            f"record-export-client:{current_user.id}:{params.idempotency_key}"
            if params.idempotency_key
            else f"record-export:{record_export.id}"
        ),
    )
    await db_session.commit()
    return _export_payload(record_export)


@router.get("")
async def list_exports(
    db_session: DBSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unseen_only: bool = False,
):
    conditions = [RecordExport.requested_by_user_id == current_user.id]
    if unseen_only:
        conditions.extend(
            [
                RecordExport.seen_at.is_(None),
                RecordExport.status.in_(
                    [
                        RecordExportStatus.SUCCEEDED.value,
                        RecordExportStatus.FAILED.value,
                    ]
                ),
            ]
        )
    total = await db_session.scalar(
        select(func.count()).select_from(RecordExport).where(*conditions)
    )
    items = list(
        (
            await db_session.scalars(
                select(RecordExport)
                .where(*conditions)
                .order_by(RecordExport.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return {
        "items": [_export_payload(item) for item in items],
        "total_count": total or 0,
    }


@router.get("/{export_id}")
async def get_export(
    export_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
):
    return _export_payload(await _owned_export(db_session, export_id, current_user.id))


@router.post("/{export_id}/download-url")
async def create_download_url(
    export_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
):
    record_export = await _owned_export(db_session, export_id, current_user.id)
    await _reauthorize_export_download(
        db_session,
        record_export,
        current_user.id,
    )
    try:
        url = await record_export_download_url(record_export)
    except RecordExportError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await add_export_audit(
        db_session,
        record_export,
        RecordExportAuditAction.DOWNLOADED,
        actor_user_id=current_user.id,
    )
    record_export.seen_at = record_export.seen_at or utcnow()
    await db_session.commit()
    return {
        "url": url,
        "filename": record_export.output_filename,
        "expires_in_seconds": 3600,
        "checksum_sha256": record_export.checksum_sha256,
    }


@router.post("/{export_id}/seen")
async def mark_export_seen(
    export_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
):
    record_export = await _owned_export(db_session, export_id, current_user.id)
    record_export.seen_at = record_export.seen_at or utcnow()
    await db_session.commit()
    return {"seen": True}


@router.delete("/{export_id}")
async def cancel_or_delete_export(
    export_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
):
    record_export = await _owned_export(db_session, export_id, current_user.id)
    if record_export.output_object_key:
        await delete_file(
            record_export.output_object_key,
            backend=record_export.output_backend,
        )
        record_export.output_object_key = None
    if record_export.status != RecordExportStatus.EXPIRED.value:
        record_export.status = RecordExportStatus.CANCELLED.value
        record_export.finished_at = record_export.finished_at or utcnow()
        await add_export_audit(
            db_session,
            record_export,
            RecordExportAuditAction.CANCELLED,
            actor_user_id=current_user.id,
        )
    await db_session.commit()
    return _export_payload(record_export)
