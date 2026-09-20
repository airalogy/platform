"""Project-scoped entry points for the shared private Analysis lifecycle."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import select

from app.database import DBSession
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.routers.analyses import AnalysisConfirmRequest
from app.routers.depends import CurrentUser
from app.services.analysis_engine import MAX_RECORDS, AnalysisError
from app.services.analysis_schema import schema_fields
from app.services.project_analyses import (
    MAX_PROJECT_INPUTS,
    ProjectInterpretationRequest,
    ProjectPreviewRequest,
    compare_project_analyses,
    confirm_project_analysis,
    create_project_interpretation,
    create_project_preview,
    project_analysis_scope,
    project_interpretations,
)
from app.services.project_analysis_engine import project_source_fields
from app.services.record_analyses import (
    AnalysisSelection,
    analysis_scope,
    capture_sources,
)

router = APIRouter(tags=["analysis"])


@router.get("/projects/{project_id}/project-analysis-context")
async def get_project_analysis_context(
    project_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    response.headers["Cache-Control"] = "private, no-store"
    project = await project_analysis_scope(db_session, project_id, current_user)
    candidates = list(
        (
            await db_session.scalars(
                select(Protocol)
                .where(Protocol.project_id == project.id, Protocol.deleted_at.is_(None))
                .order_by(Protocol.id)
                .offset(offset)
                .limit(limit + 1)
            )
        ).all()
    )
    protocols = []
    for candidate in candidates[:limit]:
        try:
            protocol, _, own_only = await analysis_scope(
                db_session, candidate.id, current_user
            )
        except HTTPException as exc:
            if exc.status_code not in {400, 403, 404}:
                raise
            continue
        versions = list(
            (
                await db_session.scalars(
                    select(ProtocolVersion)
                    .where(ProtocolVersion.protocol_id == protocol.id)
                    .order_by(ProtocolVersion.version)
                )
            ).all()
        )
        latest = next(
            (
                version
                for version in versions
                if version.version == protocol.latest_version
            ),
            None,
        )
        try:
            fields = (
                project_source_fields(
                    {
                        "schemas": [
                            {
                                "id": str(latest.id),
                                "version": latest.version,
                                "json_schema": latest.json_schema,
                            }
                        ],
                        "fields": schema_fields(latest),
                    }
                )
                if latest
                else []
            )
            error = None
        except AnalysisError:
            fields, error = [], "The latest Protocol Schema is not analyzable"
        protocols.append(
            {
                "protocol_id": str(protocol.id),
                "protocol_name": protocol.name,
                "fields": fields,
                "protocol_versions": [version.version for version in versions],
                "own_records_only": own_only,
                "unavailable_reason": error,
            }
        )
    return {
        "project_id": str(project.id),
        "project_name": project.name,
        "protocols": protocols,
        "next_offset": offset + limit if len(candidates) > limit else None,
        "limits": {"max_inputs": MAX_PROJECT_INPUTS, "max_records": MAX_RECORDS},
        "ai_available": False,
    }


@router.post("/projects/{project_id}/project-analysis-context/{protocol_id}")
async def get_project_source_context(
    project_id: UUID,
    protocol_id: UUID,
    params: AnalysisSelection,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    project = await project_analysis_scope(db_session, project_id, current_user)
    try:
        snapshot, protocol, source_project = await capture_sources(
            db_session, protocol_id=protocol_id, selection=params, user=current_user
        )
        if source_project.id != project.id:
            raise HTTPException(
                422, "Selected Protocol does not belong to this Project"
            )
        fields = project_source_fields(snapshot)
        _, _, own_only = await analysis_scope(db_session, protocol.id, current_user)
    except AnalysisError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "project_id": str(project.id),
        "protocol_id": str(protocol.id),
        "protocol_name": protocol.name,
        "fields": fields,
        "own_records_only": own_only,
        "protocol_versions": [row["version"] for row in snapshot["schemas"]],
        "sources": [
            {key: value for key, value in row.items() if key != "data"}
            for row in snapshot["records"]
        ],
        "limits": {"max_records": MAX_RECORDS},
        "ai_available": False,
    }


@router.post("/analyses/project/preview")
async def preview_project_record_analysis(
    params: ProjectPreviewRequest,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    try:
        preview = await create_project_preview(db_session, params, current_user)
    except AnalysisError as exc:
        detail = {
            "message": str(exc),
            "code": getattr(exc, "code", "invalid_project_analysis"),
        }
        if getattr(exc, "audit", None) is not None:
            detail["audit"] = exc.audit
        raise HTTPException(422, detail) from exc
    await db_session.commit()
    return preview.as_dict()


@router.post("/analyses/project")
async def create_project_record_analysis(
    # The confirmation envelope is deliberately identical to Protocol analysis.
    params: AnalysisConfirmRequest,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    try:
        run = await confirm_project_analysis(
            db_session,
            preview_id=params.preview_id,
            preview_digest=params.preview_digest,
            key=params.client_idempotency_key,
            user=current_user,
        )
    except AnalysisError as exc:
        raise HTTPException(422, str(exc)) from exc
    await db_session.commit()
    return run.as_dict()


@router.get("/analyses/{analysis_id}/comparison")
async def get_project_analysis_comparison(
    analysis_id: UUID,
    baseline_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    return await compare_project_analyses(
        db_session, analysis_id, baseline_id, current_user
    )


@router.get("/analyses/{analysis_id}/interpretations")
async def get_project_analysis_interpretations(
    analysis_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    return await project_interpretations(db_session, analysis_id, current_user)


@router.post("/analyses/{analysis_id}/interpretations")
async def append_project_analysis_interpretation(
    analysis_id: UUID,
    params: ProjectInterpretationRequest,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    revision = await create_project_interpretation(
        db_session, analysis_id, params, current_user
    )
    await db_session.commit()
    return revision.as_dict()
