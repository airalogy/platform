"""Protocol release governance, Record migration, and projection endpoints."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from jsonschema import Draft202012Validator
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.database import DBSession
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.resource import (
    Resource,
    ResourceRevision,
    ResourceType,
    ResourceTypeRevision,
)
from app.routers.permission import check_user_permission
from app.services.access_control import resolve_resource_access
from app.services.persistent_jobs import enqueue_job
from app.services.resource_bindings import (
    ResourceBindingError,
    extract_resource_bindings,
)
from app.services.schema_governance import (
    GovernanceError,
    find_migration_path,
    get_or_create_projection,
    preview_migration_path,
    run_schema_migration,
)
from app.services.resource_inventory import InventoryError, commit_record_resources

from .depends import CurrentUser

router = APIRouter(tags=["schema-governance"])


class MigrationPreviewParams(BaseModel):
    target_version: str


class MigrationRunParams(MigrationPreviewParams):
    confirmed: bool
    reason: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1, max_length=255)


class ProjectionParams(BaseModel):
    target_version: str


class ProjectionJobParams(BaseModel):
    source_version: str | None = None
    target_version: str
    idempotency_key: str = Field(min_length=1, max_length=255)


class ResourceMigrationJobParams(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    dry_run: bool = True


async def _protocol_context(
    db_session: DBSession,
    *,
    protocol_id: UUID,
    current_user: CurrentUser,
    action: str,
) -> tuple[Protocol, Project]:
    protocol = await db_session.get(Protocol, protocol_id)
    if protocol is None or protocol.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Protocol not found")
    project = await db_session.get(Project, protocol.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await check_user_permission(
        db_session,
        project=project,
        protocol=protocol,
        user=current_user,
        action=action,
    )
    return protocol, project


async def _version(
    db_session: DBSession, protocol_id: UUID, version: str
) -> ProtocolVersion:
    value = await db_session.scalar(
        select(ProtocolVersion).where(
            ProtocolVersion.protocol_id == protocol_id,
            ProtocolVersion.version == version,
        )
    )
    if value is None:
        raise HTTPException(status_code=404, detail="Protocol version not found")
    return value


async def _latest_record(
    db_session: DBSession, protocol_id: UUID, record_id: UUID
) -> Record:
    value = await db_session.scalar(
        select(Record)
        .where(
            Record.id == record_id,
            Record.protocol_id == protocol_id,
            Record.deleted_at.is_(None),
        )
        .order_by(Record.version.desc())
        .limit(1)
    )
    if value is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return value


async def _migration_context(
    db_session: DBSession,
    protocol_id: UUID,
    source: ProtocolVersion,
    target: ProtocolVersion,
) -> tuple[list[dict[str, Any]], dict[str, ProtocolVersion]]:
    versions = (
        await db_session.scalars(
            select(ProtocolVersion).where(
                ProtocolVersion.protocol_id == protocol_id
            )
        )
    ).all()
    versions_by_name = {item.version: item for item in versions}
    manifests: list[dict[str, Any]] = []
    for version in versions:
        stored = version.migration_manifest
        candidates = [stored] if isinstance(stored, dict) else (stored or [])
        manifests.extend(
            item for item in candidates if isinstance(item, dict)
        )
    try:
        path = find_migration_path(manifests, source.version, target.version)
    except GovernanceError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return path, versions_by_name


def _schema_issues(schema: dict, data: dict) -> list[dict[str, str]]:
    return [
        {
            "path": ".".join(str(item) for item in error.absolute_path),
            "message": error.message,
        }
        for error in Draft202012Validator(schema).iter_errors(data)
    ]


@router.get("/protocols/{protocol_id}/governance/versions/{target_version}")
async def protocol_version_governance(
    protocol_id: UUID,
    target_version: str,
    current_user: CurrentUser,
    db_session: DBSession,
):
    protocol, _ = await _protocol_context(
        db_session,
        protocol_id=protocol_id,
        current_user=current_user,
        action="read_protocol",
    )
    target = await _version(db_session, protocol_id, target_version)
    record_count = await db_session.scalar(
        select(func.count(func.distinct(Record.id))).where(
            Record.protocol_id == protocol_id,
            Record.protocol_version != target.version,
            Record.deleted_at.is_(None),
        )
    )
    registered_resource_count = await db_session.scalar(
        select(func.count(ResourceTypeRevision.id)).where(
            ResourceTypeRevision.protocol_id == protocol_id,
            ResourceTypeRevision.protocol_version != target.version,
        )
    )
    return {
        "protocol_id": protocol.id,
        "target_version": target.version,
        "compatibility_report": target.compatibility_report,
        "migration_manifest": target.migration_manifest,
        "affected_records": record_count or 0,
        "affected_resource_type_revisions": registered_resource_count or 0,
    }


@router.post(
    "/protocols/{protocol_id}/records/{record_id}/migration-preview"
)
async def record_migration_preview(
    protocol_id: UUID,
    record_id: UUID,
    params: MigrationPreviewParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _protocol_context(
        db_session,
        protocol_id=protocol_id,
        current_user=current_user,
        action="read_record",
    )
    record = await _latest_record(db_session, protocol_id, record_id)
    source = await _version(db_session, protocol_id, record.protocol_version)
    target = await _version(db_session, protocol_id, params.target_version)
    path, versions_by_name = await _migration_context(
        db_session, protocol_id, source, target
    )
    preview = await preview_migration_path(
        record.data,
        path,
        source_version=source,
        target_version=target,
        versions_by_name=versions_by_name,
    )
    return {
        **preview,
        "source_version": source.version,
        "target_version": target.version,
        "original_data": record.data,
        "schema_issues": (
            []
            if preview["requires_sandbox"]
            else _schema_issues(target.json_schema, preview["data"])
        ),
    }


@router.post("/protocols/{protocol_id}/records/{record_id}/migrations")
async def migrate_record(
    protocol_id: UUID,
    record_id: UUID,
    params: MigrationRunParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    if not params.confirmed:
        raise HTTPException(
            status_code=422,
            detail="Migration must be explicitly confirmed after preview",
        )
    _, project = await _protocol_context(
        db_session,
        protocol_id=protocol_id,
        current_user=current_user,
        action="create_record",
    )
    record = await _latest_record(db_session, protocol_id, record_id)
    source = await _version(db_session, protocol_id, record.protocol_version)
    target = await _version(db_session, protocol_id, params.target_version)
    path, versions_by_name = await _migration_context(
        db_session, protocol_id, source, target
    )
    try:
        run, migrated = await run_schema_migration(
            db_session,
            record=record,
            target_version=target,
            source_version=source,
            manifests=path,
            versions_by_name=versions_by_name,
            user_id=current_user.id,
            reason=params.reason,
            idempotency_key=params.idempotency_key,
        )
        issues = _schema_issues(target.json_schema, migrated.data)
        if issues:
            raise GovernanceError(
                "Migrated Record does not match the target Schema: "
                + "; ".join(item["message"] for item in issues)
            )
        bindings = extract_resource_bindings(target.fields, migrated.data)
        await commit_record_resources(
            db_session,
            lab_id=project.lab_id,
            record=migrated,
            actor_user_id=current_user.id,
            bindings=bindings,
            apply_inventory=False,
        )
        await db_session.commit()
    except (GovernanceError, ResourceBindingError, InventoryError) as error:
        await db_session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"migration": run.as_dict(), "record": migrated.as_dict()}


@router.post("/protocols/{protocol_id}/records/{record_id}/projections")
async def project_record(
    protocol_id: UUID,
    record_id: UUID,
    params: ProjectionParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _protocol_context(
        db_session,
        protocol_id=protocol_id,
        current_user=current_user,
        action="read_record",
    )
    record = await _latest_record(db_session, protocol_id, record_id)
    source = await _version(db_session, protocol_id, record.protocol_version)
    target = await _version(db_session, protocol_id, params.target_version)
    path: list[dict[str, Any]] | None = None
    versions_by_name = {source.version: source, target.version: target}
    if source.version != target.version:
        path, versions_by_name = await _migration_context(
            db_session, protocol_id, source, target
        )
    try:
        projection = await get_or_create_projection(
            db_session,
            record=record,
            source_version=source,
            target_version=target,
            manifests=path,
            versions_by_name=versions_by_name,
        )
        await db_session.commit()
    except GovernanceError as error:
        await db_session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    return projection.as_dict()


@router.post("/protocols/{protocol_id}/projection-jobs")
async def create_projection_job(
    protocol_id: UUID,
    params: ProjectionJobParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    _, project = await _protocol_context(
        db_session,
        protocol_id=protocol_id,
        current_user=current_user,
        action="read_record",
    )
    await _version(db_session, protocol_id, params.target_version)
    job = await enqueue_job(
        db_session,
        lab_id=project.lab_id,
        kind="record_projection",
        payload={
            "protocol_id": str(protocol_id),
            "source_version": params.source_version,
            "target_version": params.target_version,
        },
        idempotency_key=params.idempotency_key,
    )
    await db_session.commit()
    return job.as_dict()


@router.post(
    "/labs/{lab_id}/resource-library/types/{resource_type_id}/migration-jobs"
)
async def create_resource_migration_job(
    lab_id: UUID,
    resource_type_id: UUID,
    params: ResourceMigrationJobParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    resource_type = await db_session.get(ResourceType, resource_type_id)
    if resource_type is None or resource_type.lab_id != lab_id:
        raise HTTPException(status_code=404, detail="Resource type not found")
    decision = await resolve_resource_access(
        db_session,
        current_user.id,
        lab_id,
        resource_type_id=resource_type_id,
    )
    if "resource.manage" not in decision.capabilities:
        raise HTTPException(status_code=403, detail="Permission denied")
    current_revision = await db_session.get(
        ResourceTypeRevision, resource_type.current_revision_id
    )
    if current_revision is None:
        raise HTTPException(
            status_code=409, detail="Resource type has no active revision"
        )
    resources = (
        await db_session.scalars(
            select(Resource).where(
                Resource.resource_type_id == resource_type.id,
                Resource.archived_at.is_(None),
            )
        )
    ).all()
    target_version = await db_session.get(
        ProtocolVersion, current_revision.protocol_version_id
    )
    if target_version is None:
        raise HTTPException(
            status_code=409, detail="Target resource Schema was not found"
        )
    preview = []
    for resource in resources:
        revision = await db_session.get(ResourceRevision, resource.current_revision_id)
        if revision.resource_type_revision_id == current_revision.id:
            preview.append(
                {
                    "resource_id": resource.id,
                    "resource_revision": revision.revision,
                    "ready": False,
                    "status": "already_current",
                    "issues": [],
                    "not_collected": [],
                }
            )
            continue
        source_type_revision = await db_session.get(
            ResourceTypeRevision, revision.resource_type_revision_id
        )
        source_version = (
            await db_session.get(
                ProtocolVersion, source_type_revision.protocol_version_id
            )
            if source_type_revision
            else None
        )
        migration_issues: list[dict[str, str]] = []
        not_collected: list[str] = []
        migrated_data = revision.data
        status = "needs_review"
        if source_version is None:
            migration_issues.append(
                {
                    "path": "",
                    "message": "Source resource Schema version was not found",
                }
            )
        else:
            try:
                path, versions_by_name = await _migration_context(
                    db_session,
                    current_revision.protocol_id,
                    source_version,
                    target_version,
                )
                result = await preview_migration_path(
                    revision.data,
                    path,
                    source_version=source_version,
                    target_version=target_version,
                    versions_by_name=versions_by_name,
                )
                migrated_data = result["data"]
                status = result["status"]
                migration_issues.extend(result["issues"])
                not_collected = result["not_collected"]
            except HTTPException as error:
                migration_issues.append(
                    {"path": "", "message": str(error.detail)}
                )
        issues = [
            *migration_issues,
            *_schema_issues(target_version.json_schema, migrated_data),
        ]
        preview.append(
            {
                "resource_id": resource.id,
                "resource_revision": revision.revision,
                "ready": status == "completed" and not issues,
                "status": status,
                "issues": issues,
                "not_collected": not_collected,
            }
        )
    if params.dry_run:
        return {
            "dry_run": True,
            "ready": sum(1 for item in preview if item["ready"]),
            "needs_review": sum(1 for item in preview if not item["ready"]),
            "items": preview,
        }
    job = await enqueue_job(
        db_session,
        lab_id=lab_id,
        kind="resource_schema_migration",
        payload={
            "resource_type_id": str(resource_type_id),
            "target_resource_type_revision_id": str(current_revision.id),
            "actor_user_id": str(current_user.id),
            "resource_ids": [
                str(item["resource_id"]) for item in preview if item["ready"]
            ],
            "needs_review": [
                str(item["resource_id"]) for item in preview if not item["ready"]
            ],
        },
        idempotency_key=params.idempotency_key,
    )
    await db_session.commit()
    return job.as_dict()
