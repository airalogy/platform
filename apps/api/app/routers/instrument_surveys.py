"""User-approved, one-shot survey interpretation. No local/hardware credentials."""

import asyncio
import hmac
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.config import config
from app.database import DBSession
from app.libs.masterbrain import aira_structured_proposal
from app.models.instrument_authoring import InstrumentAuthoringSession as Session
from app.models.instrument_authoring import InstrumentAuthoringTurn as Turn
from app.models.user import User
from app.routers.depends import CurrentUser
from app.routers.instrument_authoring import (
    Cancel,
    _scope,
    _snapshot,
    _turn_data,
    _turns,
)
from app.routers.research_instrument_gateways import _audit, _gateway_context
from app.services.instrument_application_selection import is_candidates
from app.services.instrument_package_contract import canonical, sha256
from app.services.instrument_survey import (
    generation_prompt,
    validate_analysis,
    validate_report,
)
from app.services.model_usage import create_usage_context
from app.services.research_runtime import utcnow

router = APIRouter(prefix="/instrument-surveys", tags=["Instrument development"])


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    gateway_id: UUID
    resource_id: UUID
    goal: str = Field(min_length=1, max_length=4000)
    report: dict
    reason: str = Field(min_length=1, max_length=2000)
    model_processing_consent: bool = False
    capture_reviewed: bool = False

    @model_validator(mode="after")
    def validate_content(self):
        validate_report(self.report)
        if not self.goal.strip() or not self.reason.strip():
            raise ValueError("A goal and authorization reason are required")
        return self

    def request(self):
        value = {
            "id": str(self.id),
            "schema": "airalogy.application-selection.v1"
            if is_candidates(self.report)
            else "airalogy.survey-analysis.v1",
            "gateway_id": str(self.gateway_id),
            "resource_id": str(self.resource_id),
            "spec": {"goal": self.goal, "report": self.report},
            "max_iterations": 1,
        }
        return {**value, "fingerprint": sha256(canonical(value))}


class Confirm(Draft):
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


def preview(params, pin):
    if not params.model_processing_consent or not params.capture_reviewed:
        raise HTTPException(
            422,
            "Review the exact report and consent to configured-model processing first",
        )
    return {
        "preview_digest": sha256(
            canonical(
                {"request": params.request(), "reason": params.reason, "pin": pin}
            )
        ),
        "request_fingerprint": params.request()["fingerprint"],
        "capture_digest": sha256(canonical(params.report)),
        "scope_pin": pin,
        "hardware_authorized": False,
        "effects": [
            "Store this private client-supplied report and send its selected text and goal to the configured Aira model, which may be external",
            "One model attempt, at most 60 seconds and 32 KiB of response; not a guaranteed monetary ceiling",
            "Store and export advisory software candidates or read-only mapping suggestions for human review; metadata does not prove software capabilities",
            "No browser/software launch, screenshots, tools, action approval, source approval, installation or hardware authority",
        ],
    }


@router.post("/preview")
async def preview_session(
    params: Draft, current_user: CurrentUser, db_session: DBSession
):
    if not config.effective_ai_enabled:
        raise HTTPException(
            409, "Aira is disabled; local survey and manual assembly remain available"
        )
    _, pin = await _scope(db_session, current_user, params.request())
    return preview(params, pin)


@router.post("")
async def create_session(
    params: Confirm, current_user: CurrentUser, db_session: DBSession
):
    request = params.request()
    gateway, _ = await _scope(db_session, current_user, request)
    await _gateway_context(db_session, current_user, gateway.id, lock=True)
    gateway, pin = await _scope(db_session, current_user, request)
    row = await db_session.get(Session, params.id)
    if row:
        if (
            row.purpose != "survey"
            or row.created_by_user_id != current_user.id
            or row.request != request
            or row.confirmation_digest != params.preview_digest
        ):
            raise HTTPException(409, "Development request identity is already in use")
        return await _snapshot(db_session, row)
    if not config.effective_ai_enabled:
        raise HTTPException(409, "Aira is disabled")
    result = preview(params, pin)
    if not hmac.compare_digest(result["preview_digest"], params.preview_digest):
        raise HTTPException(409, "Survey analysis preview changed")
    row = Session(
        id=params.id,
        purpose="survey",
        gateway_id=gateway.id,
        resource_id=params.resource_id,
        created_by_user_id=current_user.id,
        request=request,
        scope_pin=pin,
        confirmation_digest=params.preview_digest,
        state="open",
        expires_at=utcnow() + timedelta(minutes=5),
    )
    db_session.add(row)
    db_session.add(
        _audit(
            gateway=gateway,
            actor_user_id=current_user.id,
            action="survey.authorized",
            revision=gateway.revision,
            snapshot={
                "session_id": str(row.id),
                "fingerprint": request["fingerprint"],
                "scope_pin": pin,
            },
            reason=params.reason,
        )
    )
    await db_session.commit()
    return await _snapshot(db_session, row)


@router.get("")
async def list_sessions(
    gateway_id: UUID,
    resource_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    offset: int = Query(default=0, ge=0, le=10000),
):
    await _scope(
        db_session,
        current_user,
        {"gateway_id": str(gateway_id), "resource_id": str(resource_id)},
    )
    rows = list(
        await db_session.scalars(
            select(Session)
            .where(
                Session.purpose == "survey",
                Session.gateway_id == gateway_id,
                Session.resource_id == resource_id,
            )
            .order_by(Session.created_at.desc(), Session.id)
            .offset(offset)
            .limit(21)
        )
    )
    return {
        "items": [
            {
                "id": str(row.id),
                "goal": row.request["spec"]["goal"],
                "state": "expired"
                if row.state == "open" and row.expires_at <= utcnow()
                else row.state,
                "created_at": row.created_at,
                "expires_at": row.expires_at,
            }
            for row in rows[:20]
        ],
        "has_more": len(rows) > 20,
        "next_offset": offset + 20,
    }


async def user_session(db, user, session_id, *, lock=False):
    query = select(Session).where(Session.id == session_id)
    row = await db.scalar(query.with_for_update() if lock else query)
    if row is None or row.purpose != "survey":
        raise HTTPException(404, "Survey analysis session not found")
    gateway, pin = await _scope(db, user, row.request)
    return row, gateway, pin


def can_generate(row, user, pin):
    if row.created_by_user_id != user.id:
        raise HTTPException(
            403, "Only the confirming user may start this model attempt"
        )
    if (
        row.state != "open"
        or row.expires_at <= utcnow()
        or row.scope_pin != pin
        or not config.effective_ai_enabled
    ):
        raise HTTPException(
            409, "Survey authorization is cancelled, expired, changed or unavailable"
        )


@router.get("/{session_id}")
async def get_session(
    session_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    row, _, pin = await user_session(db_session, current_user, session_id)
    result = await _snapshot(db_session, row)
    result["can_analyze"] = (
        not result["turns"]
        and row.state == "open"
        and row.expires_at > utcnow()
        and row.scope_pin == pin
        and row.created_by_user_id == current_user.id
        and config.effective_ai_enabled
    )
    return result


@router.post("/{session_id}/cancel")
async def cancel_session(
    session_id: UUID, params: Cancel, current_user: CurrentUser, db_session: DBSession
):
    row, gateway, _ = await user_session(
        db_session, current_user, session_id, lock=True
    )
    if params.request_fingerprint != row.request["fingerprint"]:
        raise HTTPException(409, "Survey request identity changed")
    if row.state != "cancelled":
        row.state = "cancelled"
        db_session.add(
            _audit(
                gateway=gateway,
                actor_user_id=current_user.id,
                action="survey.cancelled",
                revision=gateway.revision,
                snapshot={"session_id": str(row.id)},
                reason=params.reason,
            )
        )
        await db_session.commit()
    return await _snapshot(db_session, row)


class Analyze(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID


@router.post("/{session_id}/analyze")
async def analyze(
    session_id: UUID, params: Analyze, current_user: CurrentUser, db_session: DBSession
):
    row, gateway, pin = await user_session(
        db_session, current_user, session_id, lock=True
    )
    turns = await _turns(db_session, row.id)
    if turns:
        if turns[0].id != params.id:
            raise HTTPException(
                409, "One model attempt only; inspect the saved turn without retrying"
            )
        return _turn_data(turns[0])
    if await db_session.get(Turn, params.id):
        raise HTTPException(409, "Turn identity is already in use")
    can_generate(row, current_user, pin)
    usage = create_usage_context(
        feature="instrument.application_selection"
        if is_candidates(row.request["spec"]["report"])
        else "instrument.survey",
        user_id=current_user.id,
        lab_id=gateway.lab_id,
        attributes={"session_id": str(row.id), "turn_id": str(params.id)},
    )
    spec = row.request["spec"]
    capture_digest = sha256(canonical(spec["report"]))
    deadline = min(utcnow() + timedelta(seconds=65), row.expires_at)
    turn = Turn(
        id=params.id,
        session_id=row.id,
        ordinal=1,
        previous_id=None,
        input={"capture_digest": capture_digest},
        state="generating",
        operation_id=usage.operation_id,
        deadline=deadline,
    )
    db_session.add(turn)
    await (
        db_session.commit()
    )  # Reserve the paid attempt before contacting the provider.
    proposal, error = None, None
    try:
        async with asyncio.timeout(
            min(60, max(0, (deadline - utcnow()).total_seconds()))
        ):
            proposal = validate_analysis(
                await aira_structured_proposal(
                    generation_prompt(spec["goal"], spec["report"]),
                    pin["model"],
                    usage_context=usage,
                    max_response_bytes=32768,
                ),
                spec["report"],
            )
    except TimeoutError:
        error = "model_timeout"
    except (ValueError, TypeError, KeyError):
        error = "invalid_proposal"
    except Exception:  # noqa: BLE001 - never persist provider bodies or credentials
        error = "model_unavailable"
    actor_id = UUID(pin["actor_id"])
    db_session.expire_all()
    actor = await db_session.get(User, actor_id)
    if actor is None:
        raise HTTPException(403, "Survey user is unavailable")
    row, _, current_pin = await user_session(db_session, actor, session_id, lock=True)
    can_generate(row, actor, current_pin)
    turn = await db_session.get(Turn, params.id)
    if turn.state != "generating" or utcnow() > deadline:
        error, proposal = "model_deadline", None
    turn.state, turn.error = ("failed" if error else "generated"), error
    turn.proposal = None if error else proposal
    turn.candidate_digest = (
        sha256(canonical(proposal)) if proposal and not error else None
    )
    await db_session.commit()
    return _turn_data(turn)


@router.get("/{session_id}/export")
async def export_analysis(
    session_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    row, _, _ = await user_session(db_session, current_user, session_id)
    turns = await _turns(db_session, row.id)
    if not turns or turns[0].state != "generated":
        raise HTTPException(409, "There is no completed analysis to export")
    turn = turns[0]
    return {
        "schema": "airalogy.application-selection-export.v1"
        if is_candidates(row.request["spec"]["report"])
        else "airalogy.survey-analysis-export.v1",
        "session_id": str(row.id),
        "turn_id": str(turn.id),
        "capture_digest": sha256(canonical(row.request["spec"]["report"])),
        "analysis": turn.proposal,
    }
