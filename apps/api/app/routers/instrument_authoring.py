"""Aira source proposals only. No source imports, tools, Docker or device access."""

import asyncio
import hmac
import re
from datetime import timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from sqlalchemy import select

from app.config import config
from app.database import DBSession
from app.libs.masterbrain import aira_structured_proposal
from app.models.instrument_authoring import (
    InstrumentAuthoringSession,
    InstrumentAuthoringTurn,
)
from app.models.user import User
from app.routers.depends import CurrentUser
from app.routers.research_instrument_gateways import (
    _audit,
    _equipment_context,
    _gateway_context,
)
from app.services.instrument_authoring_contract import (
    MAX_PROPOSAL_BYTES,
    candidate_digest,
    generation_prompt,
    source_review,
    validate_proposal,
    validate_request,
)
from app.services.instrument_package_contract import canonical, sha256
from app.services.model_usage import create_usage_context
from app.services.research_runtime import utcnow

router = APIRouter(prefix="/instrument-authoring", tags=["Instrument development"])
AuthoringToken = Annotated[
    str, Header(alias="X-Airalogy-Authoring-Token", max_length=80)
]


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request: dict
    reason: str = Field(min_length=1, max_length=2000)
    model_processing_consent: bool = False
    controlled_source_consent: StrictBool = False

    @model_validator(mode="after")
    def validate_content(self):
        validate_request(self.request)
        if (
            source_review(self.request["spec"])["requires_controlled_source_consent"]
            and not self.controlled_source_consent
        ):
            raise ValueError(
                "Explicit approval to draft controlled-command source is required; this is not equipment control permission"
            )
        if not self.reason.strip():
            raise ValueError("An authorization reason is required")
        return self


class Confirm(Draft):
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


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
            select(InstrumentAuthoringSession)
            .where(
                InstrumentAuthoringSession.purpose == "source",
                InstrumentAuthoringSession.gateway_id == gateway_id,
                InstrumentAuthoringSession.resource_id == resource_id,
            )
            .order_by(
                InstrumentAuthoringSession.created_at.desc(),
                InstrumentAuthoringSession.id,
            )
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


async def _scope(db, user, request):
    gateway = await _gateway_context(db, user, UUID(request["gateway_id"]), lock=False)
    _, revision = await _equipment_context(
        db, current_user=user, gateway=gateway, resource_id=UUID(request["resource_id"])
    )
    return gateway, {
        "gateway_revision": gateway.revision,
        "resource_revision_id": str(revision.id),
        "actor_id": str(user.id),
        "model": config.CHAT_MODEL_FAST,
        # A same-named model must not silently switch processing destinations.
        # Store only a digest, never endpoint strings or API credentials.
        "model_transport_digest": sha256(
            canonical(
                {
                    "mode": config.MASTERBRAIN_CALL_MODE,
                    "external": config.CHAT_API_ENDPOINT,
                    "qwen_base": config.DASHSCOPE_BASE_URL,
                    "openai_base": config.OPENAI_BASE_URL,
                }
            )
        ),
    }


def _preview(params, pin):
    if not params.model_processing_consent:
        raise HTTPException(
            422,
            "Explicit permission to process the selected materials and test diagnostics is required",
        )
    review = source_review(params.request["spec"])
    confirmation = {"request": params.request, "reason": params.reason, "pin": pin}
    if review["requires_controlled_source_consent"]:
        confirmation["controlled_source_consent"] = params.controlled_source_consent
    return {
        "preview_digest": sha256(canonical(confirmation)),
        "source_review": review,
        "request_fingerprint": params.request["fingerprint"],
        "scope_pin": pin,
        "hardware_authorized": False,
        "effects": [
            "Process only these selected materials/code/diagnostics with the configured Aira model; it may be external",
            "At most the approved number of model calls, 60 seconds and 64 KiB of response each; no guaranteed monetary ceiling",
            "Store private editable source proposals and client-reported sandbox tests; never execute them in Platform",
            "No device/software launch, driver installation, source approval or instrument activation is authorized",
        ],
    }


@router.post("/preview")
async def preview_session(
    params: Draft, current_user: CurrentUser, db_session: DBSession
):
    if not config.effective_ai_enabled:
        raise HTTPException(
            409, "Aira is disabled; manual Adapter Packages remain available"
        )
    _, pin = await _scope(db_session, current_user, params.request)
    return _preview(params, pin)


@router.post("")
async def create_session(
    params: Confirm, current_user: CurrentUser, db_session: DBSession
):
    gateway, pin = await _scope(db_session, current_user, params.request)
    # Serialize duplicate creation within the same existing Gateway governance lock.
    await _gateway_context(db_session, current_user, gateway.id, lock=True)
    gateway, pin = await _scope(db_session, current_user, params.request)
    existing = await db_session.get(
        InstrumentAuthoringSession, UUID(params.request["id"])
    )
    if existing:
        if (
            existing.purpose != "source"
            or existing.created_by_user_id != current_user.id
            or existing.request != params.request
            or existing.confirmation_digest != params.preview_digest
        ):
            raise HTTPException(409, "Authoring request identity is already in use")
        return await _snapshot(db_session, existing)
    if not config.effective_ai_enabled:
        raise HTTPException(409, "Aira is disabled")
    preview = _preview(params, pin)
    if not hmac.compare_digest(preview["preview_digest"], params.preview_digest):
        raise HTTPException(409, "Authoring preview changed")
    row = InstrumentAuthoringSession(
        id=UUID(params.request["id"]),
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
            action="authoring.authorized",
            revision=gateway.revision,
            snapshot={
                "session_id": str(row.id),
                "fingerprint": params.request["fingerprint"],
                "scope_pin": pin,
                "controlled_source_consent": params.controlled_source_consent,
                "source_review": preview["source_review"],
            },
            reason=params.reason,
        )
    )
    await db_session.commit()
    return await _snapshot(db_session, row)


async def _turns(db, session_id):
    return list(
        await db.scalars(
            select(InstrumentAuthoringTurn)
            .where(InstrumentAuthoringTurn.session_id == session_id)
            .order_by(InstrumentAuthoringTurn.ordinal)
        )
    )


def _turn_data(turn):
    data = turn.as_dict()
    data["effective_state"] = (
        "interrupted"
        if turn.state == "generating" and turn.deadline <= utcnow()
        else turn.state
    )
    return data


async def _snapshot(db, row):
    return {
        **row.as_dict(),
        # Interface exploration and observation share this envelope, but do not
        # carry a source manifest or acquire source-development authority.
        **(
            {"source_review": source_review(row.request["spec"])}
            if row.purpose == "source"
            else {}
        ),
        "effective_state": "expired"
        if row.state == "open" and row.expires_at <= utcnow()
        else row.state,
        "turns": [_turn_data(turn) for turn in await _turns(db, row.id)],
        "hardware_authorized": False,
    }


async def _user_session(db, user, session_id):
    row = await db.get(InstrumentAuthoringSession, session_id)
    if row is None or row.purpose != "source":
        raise HTTPException(404, "Authoring session not found")
    await _scope(db, user, row.request)
    return row


@router.get("/{session_id}")
async def get_session(
    session_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    return await _snapshot(
        db_session, await _user_session(db_session, current_user, session_id)
    )


class Cancel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_reason(self):
        if not self.reason.strip():
            raise ValueError("A cancellation reason is required")
        return self


@router.post("/{session_id}/cancel")
async def cancel_session(
    session_id: UUID, params: Cancel, current_user: CurrentUser, db_session: DBSession
):
    await _user_session(db_session, current_user, session_id)
    row = await db_session.scalar(
        select(InstrumentAuthoringSession)
        .where(InstrumentAuthoringSession.id == session_id)
        .with_for_update()
    )
    if params.request_fingerprint != row.request["fingerprint"]:
        raise HTTPException(409, "Authoring session identity changed")
    if row.state != "cancelled":
        row.state = "cancelled"
        gateway, _ = await _scope(db_session, current_user, row.request)
        db_session.add(
            _audit(
                gateway=gateway,
                actor_user_id=current_user.id,
                action="authoring.cancelled",
                revision=gateway.revision,
                snapshot={"session_id": str(row.id)},
                reason=params.reason,
            )
        )
        await db_session.commit()
    return await _snapshot(db_session, row)


async def _token_session(db, session_id, token, *, write=False):
    row = await db.scalar(
        select(InstrumentAuthoringSession)
        .where(InstrumentAuthoringSession.id == session_id)
        .with_for_update()
    )
    if (
        row is None
        or row.purpose != "source"
        or not re.fullmatch(r"aiauthor_[A-Za-z0-9_-]{43}", token)
        or not hmac.compare_digest(
            sha256(token.encode()), row.request["credential_digest"]
        )
    ):
        raise HTTPException(401, "Invalid authoring credential")
    user = await db.get(User, row.created_by_user_id)
    if user is None:
        raise HTTPException(403, "Authoring user is unavailable")
    _, pin = await _scope(db, user, row.request)
    if write and (
        row.state != "open"
        or row.expires_at <= utcnow()
        or pin != row.scope_pin
        or not config.effective_ai_enabled
    ):
        raise HTTPException(
            409, "Authoring authorization is cancelled, expired, changed or unavailable"
        )
    return row, user


@router.post("/{session_id}/status")
async def local_status(
    session_id: UUID, authoring_token: AuthoringToken, db_session: DBSession
):
    row, _ = await _token_session(db_session, session_id, authoring_token)
    return await _snapshot(db_session, row)


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    previous_id: UUID | None = None


@router.post("/{session_id}/turns")
async def generate_turn(
    session_id: UUID,
    params: TurnRequest,
    authoring_token: AuthoringToken,
    db_session: DBSession,
):
    row, user = await _token_session(db_session, session_id, authoring_token)
    existing = await db_session.get(InstrumentAuthoringTurn, params.id)
    if existing:
        if existing.session_id != row.id or existing.previous_id != params.previous_id:
            raise HTTPException(409, "Turn identity is already in use")
        return _turn_data(existing)
    row, user = await _token_session(
        db_session, session_id, authoring_token, write=True
    )
    turns = await _turns(db_session, row.id)
    previous = turns[-1] if turns else None
    if (previous.id if previous else None) != params.previous_id:
        raise HTTPException(409, "Resume the latest saved attempt")
    if len(turns) >= row.request["max_iterations"]:
        raise HTTPException(409, "Authoring model-call budget exhausted")
    if previous:
        if previous.state == "generating" and previous.deadline > utcnow():
            raise HTTPException(409, "Previous model attempt is still in progress")
        if previous.state == "generated" and (
            previous.report is None
            or previous.report["passed"]
            or previous.proposal["missing_information"]
        ):
            raise HTTPException(
                409, "Test or review the previous draft before another model call"
            )
    context = create_usage_context(
        feature="instrument.authoring",
        user_id=user.id,
        lab_id=(
            await _gateway_context(db_session, user, row.gateway_id, lock=False)
        ).lab_id,
        attributes={"authoring_session_id": str(row.id), "turn_id": str(params.id)},
    )
    turn = InstrumentAuthoringTurn(
        id=params.id,
        session_id=row.id,
        ordinal=len(turns) + 1,
        previous_id=params.previous_id,
        state="generating",
        operation_id=context.operation_id,
        deadline=min(utcnow() + timedelta(seconds=65), row.expires_at),
    )
    spec, pin, deadline = row.request["spec"], row.scope_pin, turn.deadline
    previous_data = (
        None
        if previous is None
        else {
            "proposal": previous.proposal,
            "error": previous.error,
            "report": previous.report,
        }
    )
    db_session.add(turn)
    await (
        db_session.commit()
    )  # Reserve the call before network; lost responses never re-spend it.
    proposal, error = None, None
    try:
        async with asyncio.timeout(
            min(60, max(0, (deadline - utcnow()).total_seconds()))
        ):
            proposal = validate_proposal(
                await aira_structured_proposal(
                    generation_prompt(spec, previous_data),
                    pin["model"],
                    usage_context=context,
                    max_response_bytes=MAX_PROPOSAL_BYTES,
                ),
                spec,
            )
    except TimeoutError:
        error = "model_timeout"
    except (ValueError, TypeError, KeyError):
        error = "invalid_proposal"
    except Exception:  # noqa: BLE001 - persist a bounded error, never provider bodies or credentials
        error = "model_unavailable"
    db_session.expire_all()
    row, _ = await _token_session(db_session, session_id, authoring_token, write=True)
    turn = await db_session.get(InstrumentAuthoringTurn, params.id)
    if turn.state != "generating" or utcnow() > deadline:
        error, proposal = "model_deadline", None
    turn.state = "failed" if error else "generated"
    turn.error, turn.proposal = error, proposal
    turn.candidate_digest = candidate_digest(spec, proposal) if proposal else None
    await db_session.commit()
    return _turn_data(turn)


class Report(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    archive_digest: str | None = Field(pattern=r"^[a-f0-9]{64}$")
    phase: Literal["build", "sandbox"]
    sdk_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    image: str = Field(max_length=256)
    passed: bool = Field(strict=True)
    failure_reason: str = Field(max_length=128)
    untrusted_test_output: str = Field(max_length=8000)

    @model_validator(mode="after")
    def validate_outcome(self):
        if (
            self.phase == "build" and (self.passed or self.archive_digest is not None)
        ) or (self.phase == "sandbox" and self.archive_digest is None):
            raise ValueError(
                "Build failures have no archive; a sandbox report must identify its archive"
            )
        if self.passed == bool(self.failure_reason):
            raise ValueError("Only failed tests have a failure reason")
        return self


@router.post("/{session_id}/turns/{turn_id}/report")
async def report_test(
    session_id: UUID,
    turn_id: UUID,
    params: Report,
    authoring_token: AuthoringToken,
    db_session: DBSession,
):
    # Reporting already performed isolated work is allowed after cancellation/expiry,
    # but still requires the original user's current scope and exact credential.
    row, _ = await _token_session(db_session, session_id, authoring_token)
    turn = await db_session.get(InstrumentAuthoringTurn, turn_id)
    if (
        turn is None
        or turn.session_id != row.id
        or turn.state != "generated"
        or turn.proposal["missing_information"]
    ):
        raise HTTPException(409, "No testable source proposal for this attempt")
    sandbox = row.request["sandbox"]
    if (
        params.candidate_digest != turn.candidate_digest
        or params.sdk_digest != sandbox["sdk_digest"]
        or params.image != sandbox["image"]
    ):
        raise HTTPException(
            409, "Test report does not match the fixed candidate or sandbox"
        )
    result = params.model_dump()
    if turn.report is not None and turn.report != result:
        raise HTTPException(409, "A different report is already saved")
    turn.report = result
    await db_session.commit()
    return {
        "turn": _turn_data(turn),
        "provenance": "local client reported; not hardware qualification",
        "hardware_authorized": False,
    }
