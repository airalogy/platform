"""Scoped model suggestions for a separately confirmed local interface policy."""

import asyncio
import hmac
import re
from datetime import timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query
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
from app.services.instrument_exploration import (
    generation_prompt,
    validate_observation,
    validate_proposal,
    validate_report,
    validate_request,
)
from app.services.instrument_package_contract import canonical, sha256
from app.services.model_usage import create_usage_context
from app.services.research_runtime import utcnow

router = APIRouter(prefix="/instrument-exploration", tags=["Instrument development"])
InterfaceToken = Annotated[
    str, Header(alias="X-Airalogy-Interface-Token", max_length=80)
]


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request: dict
    reason: str = Field(min_length=1, max_length=2000)
    model_processing_consent: bool = False
    local_actions_reviewed: bool = False

    @model_validator(mode="after")
    def valid_request(self):
        validate_request(self.request)
        if not self.reason.strip():
            raise ValueError("A reason is required")
        return self


class Confirm(Draft):
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


def preview(params, pin):
    if not params.model_processing_consent or not params.local_actions_reviewed:
        raise HTTPException(
            422,
            "Review selected readbacks/model processing and the complete local action policy first",
        )
    return {
        "preview_digest": sha256(
            canonical(
                {
                    "purpose": "interface",
                    "request": params.request,
                    "reason": params.reason,
                    "pin": pin,
                }
            )
        ),
        "request_fingerprint": params.request["fingerprint"],
        "scope_pin": pin,
        "hardware_authorized": False,
        "effects": [
            "Aira may receive these selected control labels/readbacks and choose only an approved action index",
            "At most the approved model calls; 60 seconds and 16 KiB per response; no guaranteed monetary ceiling",
            "Local simulation actions require separate local confirmation. Live URLs are observation-only",
            "No raw screenshots, HTML, arbitrary code, extra targets, source approval, installation or hardware authority",
        ],
    }


@router.post("/preview")
async def preview_session(
    params: Draft, current_user: CurrentUser, db_session: DBSession
):
    if not config.effective_ai_enabled:
        raise HTTPException(
            409, "Aira is disabled; manual interface tools remain available"
        )
    _, pin = await _scope(db_session, current_user, params.request)
    return preview(params, pin)


@router.post("")
async def create_session(
    params: Confirm, current_user: CurrentUser, db_session: DBSession
):
    gateway, _ = await _scope(db_session, current_user, params.request)
    await _gateway_context(db_session, current_user, gateway.id, lock=True)
    gateway, pin = await _scope(db_session, current_user, params.request)
    row = await db_session.get(Session, UUID(params.request["id"]))
    if row:
        if (
            row.purpose != "interface"
            or row.created_by_user_id != current_user.id
            or row.request != params.request
            or row.confirmation_digest != params.preview_digest
        ):
            raise HTTPException(409, "Development request identity is already in use")
        return await _snapshot(db_session, row)
    if not config.effective_ai_enabled:
        raise HTTPException(409, "Aira is disabled")
    result = preview(params, pin)
    if not hmac.compare_digest(result["preview_digest"], params.preview_digest):
        raise HTTPException(409, "Interface exploration preview changed")
    row = Session(
        id=UUID(params.request["id"]),
        purpose="interface",
        gateway_id=gateway.id,
        resource_id=UUID(params.request["resource_id"]),
        created_by_user_id=current_user.id,
        request=params.request,
        scope_pin=pin,
        confirmation_digest=params.preview_digest,
        state="open",
        expires_at=utcnow() + timedelta(seconds=params.request["duration_seconds"]),
    )
    db_session.add(row)
    db_session.add(
        _audit(
            gateway=gateway,
            actor_user_id=current_user.id,
            action="exploration.authorized",
            revision=gateway.revision,
            snapshot={
                "session_id": str(row.id),
                "fingerprint": params.request["fingerprint"],
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
                Session.purpose == "interface",
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
                "expires_at": row.expires_at,
                "created_at": row.created_at,
            }
            for row in rows[:20]
        ],
        "has_more": len(rows) > 20,
        "next_offset": offset + 20,
    }


async def user_session(db, user, session_id):
    row = await db.get(Session, session_id)
    if row is None or row.purpose != "interface":
        raise HTTPException(404, "Interface development session not found")
    await _scope(db, user, row.request)
    return row


@router.get("/{session_id}")
async def get_session(
    session_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    return await _snapshot(
        db_session, await user_session(db_session, current_user, session_id)
    )


@router.post("/{session_id}/cancel")
async def cancel_session(
    session_id: UUID, params: Cancel, current_user: CurrentUser, db_session: DBSession
):
    await user_session(db_session, current_user, session_id)
    row = await db_session.scalar(
        select(Session).where(Session.id == session_id).with_for_update()
    )
    if params.request_fingerprint != row.request["fingerprint"]:
        raise HTTPException(409, "Interface exploration identity changed")
    if row.state != "cancelled":
        row.state = "cancelled"
        gateway, _ = await _scope(db_session, current_user, row.request)
        db_session.add(
            _audit(
                gateway=gateway,
                actor_user_id=current_user.id,
                action="exploration.cancelled",
                revision=gateway.revision,
                snapshot={"session_id": str(row.id)},
                reason=params.reason,
            )
        )
        await db_session.commit()
    return await _snapshot(db_session, row)


async def token_session(db, session_id, token, *, write=False):
    row = await db.scalar(
        select(Session).where(Session.id == session_id).with_for_update()
    )
    if (
        row is None
        or row.purpose != "interface"
        or not re.fullmatch(r"aiinterface_[A-Za-z0-9_-]{43}", token)
        or not hmac.compare_digest(
            sha256(token.encode()), row.request["credential_digest"]
        )
    ):
        raise HTTPException(401, "Invalid interface-development credential")
    user = await db.get(User, row.created_by_user_id)
    if user is None:
        raise HTTPException(403, "Development user is unavailable")
    _, pin = await _scope(db, user, row.request)
    allowed = (
        row.state == "open"
        and row.expires_at > utcnow()
        and pin == row.scope_pin
        and config.effective_ai_enabled
    )
    if write and not allowed:
        raise HTTPException(
            409, "Interface authorization is cancelled, expired, changed or unavailable"
        )
    return row, user, allowed


@router.post("/{session_id}/status")
async def local_status(
    session_id: UUID, interface_token: InterfaceToken, db_session: DBSession
):
    row, _, allowed = await token_session(db_session, session_id, interface_token)
    return {**await _snapshot(db_session, row), "can_proceed": allowed}


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    previous_id: UUID | None = None
    observation: dict
    evidence_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


@router.post("/{session_id}/turns")
async def generate_turn(
    session_id: UUID,
    params: TurnRequest,
    interface_token: InterfaceToken,
    db_session: DBSession,
):
    row, user, _ = await token_session(db_session, session_id, interface_token)
    selected = {
        "observation": params.observation,
        "evidence_digest": params.evidence_digest,
    }
    try:
        validate_observation(params.observation, row.request["spec"])
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    existing = await db_session.get(Turn, params.id)
    if existing:
        if (
            existing.session_id != row.id
            or existing.previous_id != params.previous_id
            or existing.input != selected
        ):
            raise HTTPException(409, "Turn identity or input changed")
        return _turn_data(existing)
    row, user, _ = await token_session(
        db_session, session_id, interface_token, write=True
    )
    turns = await _turns(db_session, row.id)
    previous = turns[-1] if turns else None
    if (previous.id if previous else None) != params.previous_id or len(
        turns
    ) >= row.request["max_iterations"]:
        raise HTTPException(
            409, "Resume the last saved turn or review the exhausted model budget"
        )
    if previous:
        if (
            previous.state != "generated"
            or previous.proposal["kind"] != "act"
            or not previous.report
            or previous.report["outcome"] != "executed"
            or params.observation != previous.report["after"]
        ):
            raise HTTPException(
                409, "Previous action is unresolved, stopped or complete"
            )
    elif params.observation["sequence"] != 0:
        raise HTTPException(409, "A new local session must start before any action")
    gateway, _ = await _scope(db_session, user, row.request)
    usage = create_usage_context(
        feature="instrument.exploration",
        user_id=user.id,
        lab_id=gateway.lab_id,
        attributes={"session_id": str(row.id), "turn_id": str(params.id)},
    )
    turn = Turn(
        id=params.id,
        session_id=row.id,
        ordinal=len(turns) + 1,
        previous_id=params.previous_id,
        input=selected,
        state="generating",
        operation_id=usage.operation_id,
        deadline=min(utcnow() + timedelta(seconds=65), row.expires_at),
    )
    spec, pin, deadline = row.request["spec"], row.scope_pin, turn.deadline
    history = [{"proposal": item.proposal, "report": item.report} for item in turns]
    db_session.add(turn)
    await db_session.commit()  # Reserve a paid attempt before contacting the provider.
    proposal, error = None, None
    try:
        async with asyncio.timeout(
            min(60, max(0, (deadline - utcnow()).total_seconds()))
        ):
            proposal = validate_proposal(
                await aira_structured_proposal(
                    generation_prompt(spec, params.observation, history),
                    pin["model"],
                    usage_context=usage,
                    max_response_bytes=16384,
                ),
                spec,
                params.observation,
            )
    except TimeoutError:
        error = "model_timeout"
    except (ValueError, TypeError, KeyError):
        error = "invalid_proposal"
    except Exception:  # noqa: BLE001 - never persist provider bodies or credentials
        error = "model_unavailable"
    db_session.expire_all()
    row, _, _ = await token_session(db_session, session_id, interface_token, write=True)
    turn = await db_session.get(Turn, params.id)
    if turn.state != "generating" or utcnow() > deadline:
        error, proposal = "model_deadline", None
    turn.state = "failed" if error else "generated"
    turn.error, turn.proposal = error, proposal
    turn.candidate_digest = sha256(canonical(proposal)) if proposal else None
    await db_session.commit()
    return _turn_data(turn)


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report: dict


@router.post("/{session_id}/turns/{turn_id}/report")
async def report_action(
    session_id: UUID,
    turn_id: UUID,
    params: ReportRequest,
    interface_token: InterfaceToken,
    db_session: DBSession,
):
    row, _, _ = await token_session(db_session, session_id, interface_token)
    turn = await db_session.get(Turn, turn_id)
    if turn is None or turn.session_id != row.id or turn.state != "generated":
        raise HTTPException(409, "No generated action for this report")
    try:
        validate_report(params.report, row.request["spec"], turn)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    if turn.report is not None and turn.report != params.report:
        raise HTTPException(409, "An immutable different report is already saved")
    turn.report = params.report
    await db_session.commit()
    return {
        "turn": _turn_data(turn),
        "hardware_authorized": False,
        "provenance": "local client reported; not hardware qualification",
    }


class EndRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    last_turn_id: UUID | None = None
    reason: Literal["client_finished", "client_stopped"]


@router.post("/{session_id}/end")
async def end_session(
    session_id: UUID,
    params: EndRequest,
    interface_token: InterfaceToken,
    db_session: DBSession,
):
    row, user, _ = await token_session(db_session, session_id, interface_token)
    turns = await _turns(db_session, row.id)
    latest = turns[-1] if turns else None
    if params.last_turn_id != (latest.id if latest else None) or (
        params.reason == "client_finished"
        and (
            latest is None
            or latest.state != "generated"
            or latest.proposal["kind"] != "finish"
        )
    ):
        raise HTTPException(409, "Local completion is not supported by the latest turn")
    if row.state != "cancelled":
        row.state = "cancelled"
        gateway, _ = await _scope(db_session, user, row.request)
        db_session.add(
            _audit(
                gateway=gateway,
                actor_user_id=user.id,
                action="exploration.ended",
                revision=gateway.revision,
                snapshot={
                    "session_id": str(row.id),
                    "last_turn_id": str(params.last_turn_id)
                    if params.last_turn_id
                    else None,
                    "hardware_authorized": False,
                },
                reason=params.reason,
            )
        )
        await db_session.commit()
    return {**await _snapshot(db_session, row), "can_proceed": False}
