"""Explicit selected analysis publication into the existing Evidence lifecycle."""

from uuid import UUID

from fastapi import APIRouter, Query, Response

from app.database import DBSession
from app.routers.depends import CurrentUser
from app.services.analysis_publications import (
    AnalysisPublicationConfirm,
    AnalysisPublicationDraft,
    confirm_analysis_publication,
    preview_analysis_publication,
    publication_context,
    publication_payload,
    require_analysis_publication_readable,
)

router = APIRouter(tags=["analysis"])


@router.get("/analyses/{analysis_id}/evidence-publication-context")
async def get_analysis_publication_context(
    analysis_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
    task_limit: int = Query(50, ge=1, le=100),
    task_offset: int = Query(0, ge=0),
):
    response.headers["Cache-Control"] = "private, no-store"
    return await publication_context(
        db_session,
        analysis_id,
        current_user,
        task_limit=task_limit,
        task_offset=task_offset,
    )


@router.post("/analyses/{analysis_id}/evidence-publications/preview")
async def preview_selected_analysis_publication(
    analysis_id: UUID,
    params: AnalysisPublicationDraft,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    return await preview_analysis_publication(
        db_session, analysis_id, current_user, params
    )


@router.post("/analyses/{analysis_id}/evidence-publications")
async def publish_selected_analysis_evidence(
    analysis_id: UUID,
    params: AnalysisPublicationConfirm,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    result = await confirm_analysis_publication(
        db_session, analysis_id, current_user, params
    )
    await db_session.commit()
    return result


@router.get("/research-assets/analysis-publications/{publication_id}")
async def get_published_analysis_evidence(
    publication_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    row = await require_analysis_publication_readable(
        db_session, publication_id, current_user
    )
    return publication_payload(row)
