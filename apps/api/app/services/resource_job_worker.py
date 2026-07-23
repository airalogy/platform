"""Durable worker for Record projections and resource Schema migrations."""

from __future__ import annotations

import asyncio
import logging
import socket
from uuid import UUID

from jsonschema import Draft202012Validator
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import sessionmanager
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.resource import (
    PersistentJob,
    Resource,
    ResourceRevision,
    ResourceTypeRevision,
)
from app.services.persistent_jobs import (
    claim_job,
    complete_job,
    fail_job,
)
from app.services.resource_index import build_resource_indexes
from app.services.resource_inventory import (
    release_expired_inventory_reservations,
)
from app.services.schema_governance import (
    find_migration_path,
    get_or_create_projection,
    preview_migration_path,
)

logger = logging.getLogger(__name__)


async def _protocol_versions(
    db_session: AsyncSession, protocol_id: UUID
) -> tuple[dict[str, ProtocolVersion], list[dict]]:
    versions = (
        await db_session.scalars(
            select(ProtocolVersion).where(
                ProtocolVersion.protocol_id == protocol_id
            )
        )
    ).all()
    versions_by_name = {item.version: item for item in versions}
    manifests: list[dict] = []
    for version in versions:
        stored = version.migration_manifest
        candidates = [stored] if isinstance(stored, dict) else (stored or [])
        manifests.extend(item for item in candidates if isinstance(item, dict))
    return versions_by_name, manifests


async def _project_records(
    db_session: AsyncSession, job: PersistentJob
) -> dict:
    protocol_id = UUID(str(job.payload["protocol_id"]))
    target_name = str(job.payload["target_version"])
    source_name = job.payload.get("source_version")
    versions, manifests = await _protocol_versions(db_session, protocol_id)
    target = versions.get(target_name)
    if target is None:
        raise ValueError(f"Protocol version {target_name} was not found")

    latest = (
        select(
            Record.id.label("record_id"),
            func.max(Record.version).label("record_version"),
        )
        .where(
            Record.protocol_id == protocol_id,
            Record.deleted_at.is_(None),
        )
        .group_by(Record.id)
        .subquery()
    )
    conditions = [
        Record.id == latest.c.record_id,
        Record.version == latest.c.record_version,
    ]
    if source_name:
        conditions.append(Record.protocol_version == source_name)
    records = (
        await db_session.scalars(
            select(Record).join(latest, and_(*conditions))
        )
    ).all()
    completed = 0
    needs_review = 0
    for record in records:
        source = versions.get(record.protocol_version)
        if source is None:
            needs_review += 1
            continue
        path = (
            []
            if source.version == target.version
            else find_migration_path(manifests, source.version, target.version)
        )
        projection = await get_or_create_projection(
            db_session,
            record=record,
            source_version=source,
            target_version=target,
            manifests=path,
            versions_by_name=versions,
        )
        if projection.status == "completed":
            completed += 1
        else:
            needs_review += 1
    return {
        "records": len(records),
        "completed": completed,
        "needs_review": needs_review,
    }


async def _migrate_resources(
    db_session: AsyncSession, job: PersistentJob
) -> dict:
    target_revision_id = UUID(
        str(job.payload["target_resource_type_revision_id"])
    )
    actor_user_id = UUID(str(job.payload["actor_user_id"]))
    target_type_revision = await db_session.get(
        ResourceTypeRevision, target_revision_id
    )
    if target_type_revision is None:
        raise ValueError("Target resource type revision was not found")
    versions, manifests = await _protocol_versions(
        db_session, target_type_revision.protocol_id
    )
    target_version = versions.get(target_type_revision.protocol_version)
    if target_version is None:
        raise ValueError("Target Protocol version was not found")

    migrated = 0
    needs_review: list[dict] = []
    for raw_resource_id in job.payload.get("resource_ids", []):
        resource = await db_session.get(Resource, UUID(str(raw_resource_id)))
        if resource is None or resource.archived_at is not None:
            needs_review.append(
                {"resource_id": raw_resource_id, "issue": "resource_not_found"}
            )
            continue
        current = await db_session.get(
            ResourceRevision, resource.current_revision_id
        )
        source_type_revision = await db_session.get(
            ResourceTypeRevision, current.resource_type_revision_id
        )
        source_version = versions.get(source_type_revision.protocol_version)
        if source_version is None:
            needs_review.append(
                {
                    "resource_id": str(resource.id),
                    "issue": "source_protocol_version_not_found",
                }
            )
            continue
        try:
            path = find_migration_path(
                manifests, source_version.version, target_version.version
            )
            preview = await preview_migration_path(
                current.data,
                path,
                source_version=source_version,
                target_version=target_version,
                versions_by_name=versions,
            )
        except ValueError as error:
            needs_review.append(
                {"resource_id": str(resource.id), "issue": str(error)}
            )
            continue
        schema_issues = [
            {
                "path": ".".join(
                    str(segment) for segment in issue.absolute_path
                ),
                "message": issue.message,
            }
            for issue in Draft202012Validator(
                target_version.json_schema
            ).iter_errors(preview["data"])
        ]
        if preview["status"] != "completed" or schema_issues:
            needs_review.append(
                {
                    "resource_id": str(resource.id),
                    "issues": [*preview["issues"], *schema_issues],
                }
            )
            continue
        revision = ResourceRevision(
            resource_id=resource.id,
            resource_type_revision_id=target_type_revision.id,
            revision=current.revision + 1,
            data=preview["data"],
            revision_kind="schema_migration",
            reason=(
                f"Resource Schema migration "
                f"{source_version.version}->{target_version.version}"
            ),
            source_revision_id=current.id,
            created_by_user_id=actor_user_id,
        )
        db_session.add(revision)
        await db_session.flush()
        db_session.add_all(
            build_resource_indexes(
                resource_type_id=resource.resource_type_id,
                resource_id=resource.id,
                revision=revision,
            )
        )
        resource.current_revision_id = revision.id
        migrated += 1
    return {
        "requested": len(job.payload.get("resource_ids", [])),
        "migrated": migrated,
        "needs_review": needs_review,
    }


async def process_persistent_job(
    db_session: AsyncSession, job: PersistentJob
) -> dict:
    if job.kind == "record_projection":
        return await _project_records(db_session, job)
    if job.kind == "resource_schema_migration":
        return await _migrate_resources(db_session, job)
    raise ValueError(f"Unsupported persistent job kind: {job.kind}")


async def run_persistent_job_worker(
    stop_event: asyncio.Event,
    *,
    poll_seconds: float = 2.0,
) -> None:
    worker_id = f"{socket.gethostname()}:{id(stop_event)}"
    while not stop_event.is_set():
        try:
            async with sessionmanager.session() as db_session:
                async with db_session.begin():
                    await release_expired_inventory_reservations(db_session)
                    job = await claim_job(
                        db_session,
                        worker_id=worker_id,
                        kinds={"record_projection", "resource_schema_migration"},
                        lease_seconds=120,
                    )
                if job is None:
                    await asyncio.wait_for(
                        stop_event.wait(), timeout=poll_seconds
                    )
                    continue
                try:
                    result = await process_persistent_job(db_session, job)
                    await complete_job(
                        db_session,
                        job=job,
                        worker_id=worker_id,
                        result=result,
                    )
                    await db_session.commit()
                except Exception as error:
                    await db_session.rollback()
                    job = await db_session.get(PersistentJob, job.id)
                    if job is not None:
                        await fail_job(
                            db_session,
                            job=job,
                            worker_id=worker_id,
                            error=str(error),
                        )
                        await db_session.commit()
        except TimeoutError:
            continue
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Persistent resource job worker iteration failed")
            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=max(poll_seconds, 2.0)
                )
            except TimeoutError:
                pass
