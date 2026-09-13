"""Private, version-pinned Record analysis with deterministic confirmation."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import and_, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.models.analysis import (
    AnalysisPipeline,
    AnalysisPipelineRevision,
    AnalysisPreview,
    AnalysisRun,
)
from app.models.lab import Lab
from app.models.project import PermissionType, Project, ProjectRole, ProjectType
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.resource import JobStatus, PersistentJob
from app.models.user import User
from app.services.analysis_engine import (
    ENGINE_VERSION,
    MAX_RECORDS,
    AnalysisError,
    AnalysisRecipe,
    canonical_digest,
    compute_analysis,
    preview_analysis,
)
from app.services.analysis_schema import schema_fields
from app.services.persistent_jobs import enqueue_job

MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024
PREVIEW_MINUTES = 15


def utcnow() -> datetime:
    return datetime.now(UTC)


class RecordSelectionFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID | None = None
    protocol_version: str | None = Field(None, max_length=64)
    number: int | None = Field(None, ge=1, strict=True)
    version: int | None = Field(None, ge=1, strict=True)
    q: str | None = Field(None, max_length=500)


class SelectedRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    version: int = Field(ge=1, strict=True)


class AnalysisSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["latest", "selected"] = "latest"
    filters: RecordSelectionFilters = Field(default_factory=RecordSelectionFilters)
    records: list[SelectedRecord] = Field(default_factory=list, max_length=MAX_RECORDS)

    @model_validator(mode="after")
    def validate_mode(self):
        if self.mode == "latest" and self.records:
            raise ValueError("Latest selection cannot also select explicit revisions")
        if self.mode == "selected":
            if not self.records:
                raise ValueError("Select at least one exact Record revision")
            if self.filters.model_dump(exclude_none=True):
                raise ValueError(
                    "Explicit selection cannot silently filter selected Records"
                )
            if len({item.id for item in self.records}) != len(self.records):
                raise ValueError("Select only one revision of each Record")
        return self


class AnalysisPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_id: UUID
    selection: AnalysisSelection = Field(default_factory=AnalysisSelection)
    recipe: AnalysisRecipe
    question: str = Field(default="", max_length=4000)
    pipeline_revision_id: UUID | None = None
    rerun_of_id: UUID | None = None
    ai_draft_id: UUID | None = None

    @model_validator(mode="after")
    def independent_ai_draft(self):
        if self.ai_draft_id and self.pipeline_revision_id:
            raise ValueError(
                "Apply an Aira draft as a new analysis before saving a method revision"
            )
        return self


async def analysis_scope(
    db: AsyncSession, protocol_id: UUID, user: User
) -> tuple[Protocol, Project, bool]:
    # Import lazily: router registration already imports the persistent worker.
    from app.routers.permission import (
        check_user_permission,
        get_user_project_role,
        get_user_protocol_role,
    )

    protocol = await db.get(Protocol, protocol_id, populate_existing=True)
    if protocol is None or protocol.deleted_at is not None:
        raise HTTPException(404, "Protocol not found")
    project = await db.get(Project, protocol.project_id, populate_existing=True)
    if project is None or project.deleted_at is not None:
        raise HTTPException(404, "Project not found")
    lab = await db.get(Lab, project.lab_id)
    if lab is None:
        raise HTTPException(404, "Lab not found")
    if (
        project.permission_type == PermissionType.PROTOCOL_LEVEL
        or not protocol.inherit_permissions
    ):
        # A public fallback role is not an explicit grant to a restricted Protocol.
        # Do not alter legacy listing semantics while adding a new data consumer.
        project_role = await get_user_project_role(db, user.id, project.id)
        protocol_role = await get_user_protocol_role(db, user.id, protocol.id)
        explicitly_allowed = (
            protocol.user_id == user.id
            or (project_role is not None and project_role <= ProjectRole.MANAGER)
            or protocol_role is not None
        )
        if config.effective_lab_structure_mode == "structured":
            from app.services.access_control import resolve_structured_access

            access = await resolve_structured_access(
                db, user.id, project.lab_id, project, protocol, include_legacy=False
            )
            explicitly_allowed = explicitly_allowed or access.allows("read_record")
        if not explicitly_allowed:
            raise HTTPException(
                403, "Explicit Protocol access is required for analysis"
            )
    try:
        role = await check_user_permission(
            db, project=project, user=user, action="read_record", protocol=protocol
        )
    except HTTPException as exc:
        raise HTTPException(403, "Record analysis access denied") from exc
    own_only = (
        project.type == ProjectType.PRIVATE and role == ProjectRole.RECORDER
    ) or (
        project.type == ProjectType.PUBLIC
        and role
        in {
            ProjectRole.RECORDER_SELF_ONLY,
            ProjectRole.EXPLORER_SELF_ONLY,
            ProjectRole.VIEWER_SELF_ONLY,
        }
    )
    return protocol, project, own_only


async def capture_sources(
    db: AsyncSession, *, protocol_id: UUID, user: User, selection: AnalysisSelection
) -> tuple[dict, Protocol, Project]:
    protocol, project, own_only = await analysis_scope(db, protocol_id, user)
    readable = [Record.protocol_id == protocol.id, Record.deleted_at.is_(None)]
    if own_only:
        readable.append(Record.user_id == user.id)
    if selection.mode == "selected":
        query = select(Record).where(
            *readable,
            tuple_(Record.id, Record.version).in_(
                [(r.id, r.version) for r in selection.records]
            ),
        )
    else:
        latest = (
            select(Record.id.label("id"), func.max(Record.version).label("version"))
            .where(*readable)
            .group_by(Record.id)
            .subquery()
        )
        query = select(Record).join(
            latest, and_(Record.id == latest.c.id, Record.version == latest.c.version)
        )
        filters = selection.filters
        for attr in ("user_id", "protocol_version", "number", "version"):
            value = getattr(filters, attr)
            if value is not None:
                query = query.where(getattr(Record, attr) == value)
        if filters.q and filters.q.strip():
            from app.routers.records import build_record_keyword_condition

            query = query.where(build_record_keyword_condition(filters.q))
    records = list(
        (
            await db.scalars(
                query.order_by(Record.id, Record.version).limit(MAX_RECORDS + 1)
            )
        ).all()
    )
    if len(records) > MAX_RECORDS:
        raise AnalysisError(f"Narrow the selection to at most {MAX_RECORDS} Records")
    if selection.mode == "selected" and len(records) != len(selection.records):
        # Do not reveal which private or deleted Record existed.
        raise HTTPException(403, "One or more selected revisions are unavailable")
    if not records:
        raise AnalysisError("No readable submitted Records match this selection")
    from app.services.workflow_files import authorize_record_files

    for record in records:
        await authorize_record_files(db, record.data, user)
    names = sorted({record.protocol_version for record in records})
    versions = list(
        (
            await db.scalars(
                select(ProtocolVersion)
                .where(
                    ProtocolVersion.protocol_id == protocol.id,
                    ProtocolVersion.version.in_(names),
                )
                .order_by(ProtocolVersion.version)
            )
        ).all()
    )
    if len(versions) != len(names) or {v.version for v in versions} != set(names):
        raise AnalysisError("Exact Protocol Schema revisions are missing or ambiguous")
    snapshot = {
        "schema_version": 1,
        "protocol_id": str(protocol.id),
        "records": [
            {
                "record_id": str(r.id),
                "record_version": r.version,
                "protocol_version": r.protocol_version,
                "user_id": str(r.user_id),
                "number": r.number,
                "created_at": r.created_at.isoformat(),
                "record_hash": r.hash,
                "data": r.data,
            }
            for r in records
        ],
        "schemas": [
            {
                "id": str(v.id),
                "version": v.version,
                "json_schema": v.json_schema,
                "fields": v.fields,
            }
            for v in versions
        ],
        "fields": [field for v in versions for field in schema_fields(v)],
    }
    try:
        encoded = json.dumps(snapshot, ensure_ascii=False, allow_nan=False).encode()
    except (ValueError, TypeError) as exc:
        raise AnalysisError(
            "Record snapshot contains unsupported or non-finite data"
        ) from exc
    if len(encoded) > MAX_SNAPSHOT_BYTES:
        raise AnalysisError("Analysis snapshot exceeds 16 MiB; narrow the selection")
    return snapshot, protocol, project


async def authorize_snapshot(db: AsyncSession, run: AnalysisRun, user: User) -> None:
    if run.created_by_user_id != user.id:
        raise HTTPException(404, "Analysis not found")
    _, _, own_only = await analysis_scope(db, run.protocol_id, user)
    verify_run_integrity(run)
    await authorize_source_manifest(
        db,
        run.protocol_id,
        user,
        run.source_snapshot.get("records")
        if isinstance(run.source_snapshot, dict)
        else None,
        own_only=own_only,
    )
    if getattr(run, "ai_provenance", None):
        from app.services.analysis_generation import authorize_ai_provenance

        await authorize_ai_provenance(db, run.ai_provenance, user)


async def authorize_source_manifest(
    db: AsyncSession, protocol_id: UUID, user: User, sources: object, *, own_only: bool
) -> None:
    """Reauthorize exact sources shared by computed reports and AI draft assets."""
    try:
        if not isinstance(sources, list) or not 1 <= len(sources) <= MAX_RECORDS:
            raise ValueError("Invalid source manifest")
        references = []
        for source in sources:
            if (
                not isinstance(source, dict)
                or not isinstance(source.get("record_id"), str)
                or type(source.get("record_version")) is not int
                or source["record_version"] < 1
            ):
                raise ValueError("Invalid source reference")
            references.append((UUID(source["record_id"]), source["record_version"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            409, "Analysis integrity check failed; do not use this report"
        ) from exc
    query = select(Record.id, Record.version, Record.user_id).where(
        Record.protocol_id == protocol_id,
        Record.deleted_at.is_(None),
        tuple_(Record.id, Record.version).in_(references),
    )
    rows = (await db.execute(query)).all()
    if len(rows) != len(sources) or (
        own_only and any(row.user_id != user.id for row in rows)
    ):
        raise HTTPException(403, "Analysis sources are no longer readable")
    from app.services.workflow_files import authorize_record_files

    records = list(
        (
            await db.scalars(
                select(Record).where(
                    Record.protocol_id == protocol_id,
                    tuple_(Record.id, Record.version).in_(references),
                )
            )
        ).all()
    )
    for record in records:
        await authorize_record_files(db, record.data, user)


def verify_run_integrity(run: AnalysisRun) -> None:
    try:
        valid = (
            canonical_digest(run.source_snapshot) == run.source_digest
            and canonical_digest(run.recipe) == run.recipe_digest
            and (
                run.result is None or canonical_digest(run.result) == run.result_digest
            )
            and (run.status != "succeeded" or run.result is not None)
        )
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise HTTPException(
            409, "Analysis integrity check failed; do not use this report"
        )


def method_revision_digest(recipe: dict, selection: dict, provenance: dict) -> str:
    """Seal the complete saved method without recursively hashing its seal."""

    if not all(isinstance(value, dict) for value in (recipe, selection, provenance)):
        raise ValueError("Saved method contracts must be JSON objects")
    return canonical_digest(
        {
            "recipe": recipe,
            "source_selection": selection,
            "provenance": {
                key: value
                for key, value in provenance.items()
                if key != "method_digest"
            },
        }
    )


def verify_revision_integrity(revision: AnalysisPipelineRevision) -> None:
    try:
        valid = canonical_digest(
            revision.recipe
        ) == revision.recipe_digest and method_revision_digest(
            revision.recipe, revision.source_selection, revision.provenance
        ) == revision.provenance.get("method_digest")
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise HTTPException(409, "Saved method integrity check failed")


async def owned_run(
    db: AsyncSession, run_id: UUID, user: User, *, lock: bool = False
) -> AnalysisRun:
    statement = (
        select(AnalysisRun)
        .where(AnalysisRun.id == run_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        statement = statement.with_for_update()
    run = await db.scalar(statement)
    if run is None:
        raise HTTPException(404, "Analysis not found")
    await authorize_snapshot(db, run, user)
    return run


async def owned_pipeline(
    db: AsyncSession, pipeline_id: UUID, user: User, *, lock: bool = False
) -> AnalysisPipeline:
    stmt = select(AnalysisPipeline).where(AnalysisPipeline.id == pipeline_id)
    if lock:
        stmt = stmt.with_for_update()
    pipeline = await db.scalar(stmt)
    if pipeline is None or pipeline.created_by_user_id != user.id:
        raise HTTPException(404, "Analysis method not found")
    await analysis_scope(db, pipeline.protocol_id, user)
    return pipeline


async def validate_lineage(
    db: AsyncSession, params: AnalysisPreviewRequest, user: User
) -> None:
    if params.rerun_of_id:
        source = await owned_run(db, params.rerun_of_id, user)
        if source.protocol_id != params.protocol_id:
            raise HTTPException(409, "Rerun must remain in the source Protocol")
    if params.pipeline_revision_id:
        revision = await db.get(AnalysisPipelineRevision, params.pipeline_revision_id)
        if revision is None:
            raise HTTPException(404, "Analysis method revision not found")
        pipeline = await owned_pipeline(db, revision.pipeline_id, user)
        verify_revision_integrity(revision)
        if revision.provenance.get("ai_provenance"):
            from app.services.analysis_generation import authorize_ai_provenance

            await authorize_ai_provenance(
                db, revision.provenance["ai_provenance"], user
            )
        if revision.provenance.get("engine_version") != ENGINE_VERSION:
            raise HTTPException(
                409,
                "Saved method requires another engine version; explicitly revise before using the current engine",
            )
        if (
            pipeline.protocol_id != params.protocol_id
            or revision.recipe_digest
            != canonical_digest(params.recipe.model_dump(mode="json"))
        ):
            raise HTTPException(
                409, "Edited method requires a new revision or an ad hoc analysis"
            )


def preview_identity_digest(preview: AnalysisPreview) -> str:
    """Seal the exact method, displayed impact, AI provenance and confirmation scope."""
    return canonical_digest(
        {
            "source_digest": preview.source_digest,
            "recipe_digest": preview.recipe_digest,
            "selection": preview.source_selection,
            "question": preview.question,
            "user_id": str(preview.created_by_user_id),
            "project_id": str(preview.project_id),
            "protocol_id": str(preview.protocol_id),
            "pipeline_revision_id": str(preview.pipeline_revision_id)
            if preview.pipeline_revision_id
            else None,
            "rerun_of_id": str(preview.rerun_of_id) if preview.rerun_of_id else None,
            "summary": preview.summary,
            "expires_at": preview.expires_at.isoformat(),
            "ai_provenance": preview.ai_provenance,
        }
    )


async def create_preview(
    db: AsyncSession, params: AnalysisPreviewRequest, user: User
) -> AnalysisPreview:
    await validate_lineage(db, params, user)
    snapshot, protocol, project = await capture_sources(
        db, protocol_id=params.protocol_id, user=user, selection=params.selection
    )
    summary = preview_analysis(params.recipe, snapshot["records"], snapshot["fields"])
    recipe = params.recipe.model_dump(mode="json")
    selection = params.selection.model_dump(mode="json", exclude_none=True)
    source_digest = canonical_digest(snapshot)
    recipe_digest = canonical_digest(recipe)
    from app.services.analysis_generation import draft_provenance, inherited_provenance

    ai_provenance = {}
    if params.ai_draft_id:
        ai_provenance = await draft_provenance(
            db,
            params.ai_draft_id,
            user,
            protocol_id=protocol.id,
            source_digest=source_digest,
            recipe=params.recipe,
            question=params.question,
        )
    elif params.pipeline_revision_id:
        revision = await db.get(AnalysisPipelineRevision, params.pipeline_revision_id)
        ai_provenance = inherited_provenance(
            revision.provenance.get("ai_provenance", {}), params.recipe
        )
    elif params.rerun_of_id:
        original = await owned_run(db, params.rerun_of_id, user)
        ai_provenance = inherited_provenance(original.ai_provenance, params.recipe)
    expires_at = utcnow() + timedelta(minutes=PREVIEW_MINUTES)
    preview = AnalysisPreview(
        project_id=project.id,
        protocol_id=protocol.id,
        created_by_user_id=user.id,
        pipeline_revision_id=params.pipeline_revision_id,
        rerun_of_id=params.rerun_of_id,
        question=params.question,
        recipe=recipe,
        source_selection=selection,
        source_digest=source_digest,
        recipe_digest=recipe_digest,
        ai_provenance=ai_provenance,
        summary={
            **summary,
            "field_stats": summary["fields"],
            "protocol_name": protocol.name,
            "project_name": project.name,
            "visibility": "private",
            "fields": snapshot["fields"],
            "sources": [
                {k: v for k, v in row.items() if k != "data"}
                for row in snapshot["records"]
            ],
        },
        expires_at=expires_at,
    )
    preview.preview_digest = preview_identity_digest(preview)
    db.add(preview)
    await db.flush()
    return preview


async def confirm_analysis(
    db: AsyncSession, *, preview_id: UUID, preview_digest: str, key: str, user: User
) -> AnalysisRun:
    # Serialize duplicate confirmations by this user, including different preview IDs.
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    existing = await db.scalar(
        select(AnalysisRun).where(
            AnalysisRun.created_by_user_id == user.id,
            AnalysisRun.client_idempotency_key == key,
        )
    )
    if existing is not None:
        if (
            existing.preview_digest != preview_digest
            or existing.engine_version != ENGINE_VERSION
        ):
            raise HTTPException(409, "Idempotency key belongs to a different analysis")
        await authorize_snapshot(db, existing, user)
        return existing
    preview = await db.get(AnalysisPreview, preview_id, populate_existing=True)
    if preview is None or preview.created_by_user_id != user.id:
        raise HTTPException(404, "Analysis preview not found")
    if preview.preview_digest != preview_digest or preview.expires_at <= utcnow():
        raise HTTPException(409, "Analysis preview changed or expired; preview again")
    try:
        valid = (
            canonical_digest(preview.recipe) == preview.recipe_digest
            and preview_identity_digest(preview) == preview.preview_digest
        )
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise HTTPException(
            409, "Analysis preview integrity check failed; preview again"
        )
    if preview.summary.get("engine_version") != ENGINE_VERSION:
        raise HTTPException(409, "Use the preview's matching analysis engine")
    if preview.ai_provenance:
        from app.services.analysis_generation import authorize_ai_provenance

        await authorize_ai_provenance(db, preview.ai_provenance, user)
    # A preview may be confirmed only once even with a new client key.
    previous = await db.scalar(
        select(AnalysisRun).where(
            AnalysisRun.created_by_user_id == user.id,
            AnalysisRun.preview_digest == preview_digest,
        )
    )
    if previous:
        await authorize_snapshot(db, previous, user)
        return previous
    params = AnalysisPreviewRequest(
        protocol_id=preview.protocol_id,
        selection=preview.source_selection,
        recipe=preview.recipe,
        question=preview.question,
        pipeline_revision_id=preview.pipeline_revision_id,
        rerun_of_id=preview.rerun_of_id,
    )
    await validate_lineage(db, params, user)
    snapshot, protocol, project = await capture_sources(
        db, protocol_id=params.protocol_id, user=user, selection=params.selection
    )
    if (
        canonical_digest(snapshot) != preview.source_digest
        or preview.summary.get("engine_version") != ENGINE_VERSION
    ):
        raise HTTPException(409, "Analysis sources or engine changed; preview again")
    preview_analysis(params.recipe, snapshot["records"], snapshot["fields"])
    run = AnalysisRun(
        project_id=project.id,
        protocol_id=protocol.id,
        created_by_user_id=user.id,
        pipeline_revision_id=preview.pipeline_revision_id,
        rerun_of_id=preview.rerun_of_id,
        question=preview.question,
        recipe=preview.recipe,
        source_selection=preview.source_selection,
        source_snapshot=snapshot,
        source_digest=preview.source_digest,
        recipe_digest=preview.recipe_digest,
        preview_digest=preview_digest,
        ai_provenance=preview.ai_provenance,
        client_idempotency_key=key,
        engine_version=ENGINE_VERSION,
        status="pending",
    )
    db.add(run)
    await db.flush()
    job = await enqueue_job(
        db,
        kind="record_analysis",
        payload={"analysis_id": str(run.id)},
        idempotency_key=f"record-analysis:{run.id}",
        lab_id=project.lab_id,
    )
    run.job_id = job.id
    await db.flush()
    return run


async def process_record_analysis(db: AsyncSession, analysis_id: UUID) -> dict:
    from app.services.workflow_analysis_runtime import (
        before_workflow_analysis_execution,
        sync_workflow_analysis,
        workflow_analysis_context,
    )

    allowed = await before_workflow_analysis_execution(db, analysis_id)
    run = await db.scalar(
        select(AnalysisRun).where(AnalysisRun.id == analysis_id).with_for_update()
    )
    if run is None:
        raise AnalysisError("Analysis was removed")
    if not allowed or run.status in {"succeeded", "cancelled", "failed"}:
        await sync_workflow_analysis(db, run)
        return {"analysis_id": str(run.id), "status": run.status}
    user = await db.get(User, run.created_by_user_id)
    if user is None:
        raise AnalysisError("Analysis owner is unavailable")
    try:
        await authorize_snapshot(db, run, user)
        if (
            run.engine_version != ENGINE_VERSION
            or canonical_digest(run.source_snapshot) != run.source_digest
            or canonical_digest(run.recipe) != run.recipe_digest
        ):
            raise AnalysisError("Pinned analysis inputs or engine no longer match")
        run.status = "running"
        run.started_at = run.started_at or utcnow()
        recipe = AnalysisRecipe.model_validate(run.recipe)
        snapshot = run.source_snapshot
        # Publish running status and release the row lock before bounded CPU work.
        # Cancellation and permission revocation can then win before result sealing.
        await db.commit()
        result = await asyncio.to_thread(
            compute_analysis,
            recipe,
            snapshot["records"],
            snapshot["fields"],
        )
        if not await before_workflow_analysis_execution(
            db, analysis_id, finishing=True
        ):
            await sync_workflow_analysis(db, run)
            return {"analysis_id": str(run.id), "status": run.status}
        await db.refresh(run, with_for_update=True)
        if run.status in {"cancelled", "succeeded", "failed"}:
            return {"analysis_id": str(run.id), "status": run.status}
        await authorize_snapshot(db, run, user)
        run.result = result
        run.result_digest = canonical_digest(result)
        run.status = "succeeded"
        run.error = None
    except (AnalysisError, HTTPException, ValueError) as exc:
        await workflow_analysis_context(db, analysis_id)
        await db.refresh(run, with_for_update=True)
        if run.status in {"cancelled", "succeeded", "failed"}:
            return {"analysis_id": str(run.id), "status": run.status}
        run.status = "failed"
        run.error = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
    run.finished_at = utcnow()
    await db.flush()
    await sync_workflow_analysis(db, run)
    return {
        "analysis_id": str(run.id),
        "status": run.status,
        "result_digest": run.result_digest,
    }


async def mark_analysis_failed(
    db: AsyncSession, analysis_id: UUID, error: str, *, terminal: bool = True
) -> None:
    from app.services.workflow_analysis_runtime import (
        sync_workflow_analysis,
        workflow_analysis_context,
    )

    await workflow_analysis_context(db, analysis_id)
    run = await db.get(AnalysisRun, analysis_id, with_for_update=True)
    if run and run.status not in {"succeeded", "cancelled", "failed"}:
        run.status = "failed" if terminal else "pending"
        run.error = error[:2000]
        run.finished_at = utcnow() if terminal else None
        await db.flush()
        if terminal:
            await sync_workflow_analysis(db, run)


async def cancel_analysis(db: AsyncSession, run: AnalysisRun) -> None:
    if run.status == "cancelled":
        return
    if run.status in {"failed", "succeeded"}:
        raise HTTPException(409, "Analysis already finished")
    run.status = "cancelled"
    run.finished_at = utcnow()
    if run.job_id:
        job = await db.get(PersistentJob, run.job_id, with_for_update=True)
        if job and job.status == JobStatus.PENDING.value:
            job.status = JobStatus.CANCELLED.value
    await db.flush()
