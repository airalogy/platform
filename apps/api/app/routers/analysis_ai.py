"""Persisted Aira suggestions, separate from deterministic numeric execution."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import select

from app.database import DBSession
from app.models.analysis_ai import AnalysisAIRequest
from app.routers.depends import CurrentUser
from app.services.analysis_engine import AnalysisError
from app.services.analysis_generation import (
    ComputeDraftRequest,
    DraftRequest,
    InterpretationRequest,
    generate_request,
    owned_ai_request,
    request_payload,
    settle_interrupted_request,
)
from app.services.record_analyses import analysis_scope, owned_run

router = APIRouter(tags=["analysis"])


@router.post("/analyses/aira-drafts")
async def generate_draft(
    params: DraftRequest, db_session: DBSession, current_user: CurrentUser
):
    try:
        row = await generate_request(db_session, params, current_user)
    except AnalysisError as exc:
        raise HTTPException(422, str(exc)) from exc
    return request_payload(row)


@router.post("/analyses/aira-compute-drafts")
async def generate_compute_draft(
    params: ComputeDraftRequest, db_session: DBSession, current_user: CurrentUser
):
    try:
        row = await generate_request(db_session, params, current_user)
    except AnalysisError as exc:
        raise HTTPException(422, str(exc)) from exc
    return request_payload(row)


@router.post("/analyses/{analysis_id}/aira-interpretations")
async def generate_interpretation(
    analysis_id: UUID,
    params: InterpretationRequest,
    db_session: DBSession,
    current_user: CurrentUser,
):
    row = await generate_request(
        db_session, params, current_user, analysis_id=analysis_id
    )
    return request_payload(row)


@router.get("/analysis-ai-requests/{request_id}")
async def get_generation(
    request_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    row = await owned_ai_request(db_session, request_id, current_user)
    await settle_interrupted_request(db_session, row)
    await db_session.commit()
    return request_payload(row)


async def _list_requests(
    db: DBSession, user: CurrentUser, conditions: list, limit: int, offset: int
):
    rows = (
        await db.scalars(
            select(AnalysisAIRequest)
            .where(
                AnalysisAIRequest.created_by_user_id == user.id,
                *conditions,
            )
            .order_by(AnalysisAIRequest.created_at.desc(), AnalysisAIRequest.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    items = []
    for candidate in rows:
        try:
            row = await owned_ai_request(db, candidate.id, user)
        except HTTPException as exc:
            if exc.status_code not in {403, 404}:
                raise
            continue
        await settle_interrupted_request(db, row)
        items.append(request_payload(row))
    await db.commit()
    return {"items": items}


@router.get("/protocols/{protocol_id}/analysis-ai-drafts")
async def list_drafts(
    protocol_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    response.headers["Cache-Control"] = "private, no-store"
    await analysis_scope(db_session, protocol_id, current_user)
    return await _list_requests(
        db_session,
        current_user,
        [
            AnalysisAIRequest.protocol_id == protocol_id,
            AnalysisAIRequest.kind == "draft",
        ],
        limit,
        offset,
    )


@router.get("/analyses/{analysis_id}/aira-interpretations")
async def list_interpretations(
    analysis_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    response.headers["Cache-Control"] = "private, no-store"
    await owned_run(db_session, analysis_id, current_user)
    return await _list_requests(
        db_session,
        current_user,
        [
            AnalysisAIRequest.analysis_run_id == analysis_id,
            AnalysisAIRequest.kind == "interpretation",
        ],
        limit,
        offset,
    )


@router.get("/protocols/{protocol_id}/analysis-ai-compute-drafts")
async def list_compute_drafts(
    protocol_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    response.headers["Cache-Control"] = "private, no-store"
    await analysis_scope(db_session, protocol_id, current_user)
    return await _list_requests(
        db_session,
        current_user,
        [
            AnalysisAIRequest.protocol_id == protocol_id,
            AnalysisAIRequest.kind == "compute_draft",
        ],
        limit,
        offset,
    )
