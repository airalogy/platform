"""Pull-only pairing, with separate local possession and administrator approval."""

import hmac
import secrets
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.database import DBSession
from app.models.instrument_pairing import InstrumentPairing
from app.models.lab import Lab
from app.models.research_execution import (
    ResearchInstrumentGateway,
    ResearchInstrumentJob,
)
from app.routers.depends import CurrentUser
from app.routers.research_instrument_gateways import _audit, _gateway_context
from app.services.research_instruments import gateway_snapshot, gateway_token_digest
from app.services.research_runtime import canonical_digest, utcnow

router = APIRouter(prefix="/instrument-pairings", tags=["Instrument pairing"])


class PairingDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    gateway_id: UUID
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)


class PairingCreate(PairingDraft):
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class PairingClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    code: str = Field(pattern=r"^aipair_[A-Za-z0-9_-]{43}$")
    gateway_id: UUID
    lab_id: UUID
    client_name: str = Field(
        min_length=1, max_length=128, pattern=r"^[^\x00-\x1f\x7f]+$"
    )
    credential_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    credential_hint: str = Field(pattern=r"^[A-Za-z0-9_-]{8}$")


class PairingConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


async def _idle(gateway, db):
    if gateway.enabled:
        raise HTTPException(
            409, "Disable the Gateway before pairing; pairing will not enable it"
        )
    count = await db.scalar(
        select(func.count())
        .select_from(ResearchInstrumentJob)
        .where(
            ResearchInstrumentJob.gateway_id == gateway.id,
            ResearchInstrumentJob.status.in_(["leased", "running", "stop_requested"]),
        )
    )
    if count:
        raise HTTPException(409, "Finish or safely stop active jobs before pairing")


def _fingerprint(row):
    if not row.credential_digest:
        return None
    return canonical_digest(
        {
            "pairing_id": str(row.id),
            "gateway_id": str(row.gateway_id),
            "client_name": row.client_name,
            "credential_digest": row.credential_digest,
        }
    )


def _snapshot(row, gateway):
    state = row.state
    if state in {"pending", "claimed"}:
        if row.expires_at <= utcnow():
            state = "expired"
        elif (
            gateway.revoked_at
            or gateway.revision != row.gateway_revision
            or gateway.enabled
        ):
            state = "stale"
    elif state == "confirmed" and (
        gateway.revoked_at or gateway.token_digest != row.credential_digest
    ):
        state = "superseded"
    return {
        "id": str(row.id),
        "gateway_id": str(gateway.id),
        "lab_id": str(gateway.lab_id),
        "gateway_name": gateway.name,
        "state": state,
        "client_name": row.client_name,
        "fingerprint": _fingerprint(row),
        "expires_at": row.expires_at.isoformat(),
        "hardware_authorized": False,
    }


def _assert_pending(row, gateway):
    if _snapshot(row, gateway)["state"] not in {"pending", "claimed"}:
        raise HTTPException(
            409, "Pairing expired, cancelled or changed; create a new pairing"
        )


async def _admin_context(pairing_id, user, db):
    row = await db.get(InstrumentPairing, pairing_id)
    if not row:
        raise HTTPException(404, "Pairing not found")
    gateway = await _gateway_context(db, user, row.gateway_id, lock=True)
    await db.refresh(row, with_for_update=True)
    return row, gateway


def _create_digest(params, user):
    return canonical_digest(
        {
            "operation": "pair_gateway",
            **params.model_dump(mode="json", exclude={"preview_digest"}),
            "actor": str(user.id),
        }
    )


@router.post("/preview")
async def preview_pairing(
    params: PairingDraft, current_user: CurrentUser, db_session: DBSession
):
    gateway = await _gateway_context(
        db_session, current_user, params.gateway_id, lock=False
    )
    await _idle(gateway, db_session)
    if gateway.revision != params.expected_revision:
        raise HTTPException(409, "Gateway changed")
    return {
        "preview_digest": _create_digest(params, current_user),
        "gateway": gateway_snapshot(gateway),
    }


@router.post("")
async def create_pairing(
    params: PairingCreate, current_user: CurrentUser, db_session: DBSession
):
    gateway = await _gateway_context(
        db_session, current_user, params.gateway_id, lock=True
    )
    await _idle(gateway, db_session)
    if (
        gateway.revision != params.expected_revision
        or params.preview_digest != _create_digest(params, current_user)
    ):
        raise HTTPException(409, "Pairing preview changed")
    await db_session.execute(
        update(InstrumentPairing)
        .where(
            InstrumentPairing.gateway_id == gateway.id,
            InstrumentPairing.state.in_(["pending", "claimed"]),
        )
        .values(state="cancelled")
    )
    code = "aipair_" + secrets.token_urlsafe(32)
    row = InstrumentPairing(
        gateway_id=gateway.id,
        gateway_revision=gateway.revision,
        code_digest=gateway_token_digest(code),
        expires_at=utcnow() + timedelta(minutes=10),
        reason=params.reason,
        created_by_user_id=current_user.id,
    )
    db_session.add(row)
    await db_session.flush()
    snapshot = _snapshot(row, gateway)
    db_session.add(
        _audit(
            gateway=gateway,
            actor_user_id=current_user.id,
            action="pairing.created",
            revision=gateway.revision,
            snapshot=snapshot,
            reason=params.reason,
        )
    )
    await db_session.commit()
    return {"pairing": snapshot, "code": code}


@router.get("")
async def list_pairings(
    gateway_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    gateway = await _gateway_context(db_session, current_user, gateway_id, lock=False)
    rows = (
        await db_session.scalars(
            select(InstrumentPairing)
            .where(InstrumentPairing.gateway_id == gateway.id)
            .order_by(InstrumentPairing.created_at.desc())
            .limit(30)
        )
    ).all()
    return {"items": [_snapshot(row, gateway) for row in rows]}


@router.post("/claim")
async def claim_pairing(params: PairingClaim, db_session: DBSession):
    # The random 256-bit capability is disclosed only by an authorized administrator.
    row = (
        await db_session.scalars(
            select(InstrumentPairing).where(
                InstrumentPairing.code_digest == gateway_token_digest(params.code)
            )
        )
    ).first()
    if not row or row.gateway_id != params.gateway_id:
        raise HTTPException(404, "Pairing unavailable")
    gateway = (
        await db_session.scalars(
            select(ResearchInstrumentGateway)
            .where(ResearchInstrumentGateway.id == row.gateway_id)
            .with_for_update()
        )
    ).first()
    await db_session.refresh(row, with_for_update=True)
    if not gateway or gateway.lab_id != params.lab_id:
        raise HTTPException(404, "Pairing unavailable")
    _assert_pending(row, gateway)
    await _idle(gateway, db_session)
    if row.state == "claimed" and (
        row.credential_digest != params.credential_digest
        or row.client_name != params.client_name
        or row.credential_hint != params.credential_hint
    ):
        raise HTTPException(
            409, "Pairing has already been claimed by another installation"
        )
    row.credential_digest = params.credential_digest
    row.credential_hint = params.credential_hint
    row.client_name = params.client_name
    row.state = "claimed"
    snapshot = _snapshot(row, gateway)
    lab = await db_session.get(Lab, gateway.lab_id)
    await db_session.commit()
    return {**snapshot, "lab_name": lab.name}


@router.post("/{pairing_id}/preview")
async def preview_confirmation(
    pairing_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    row, gateway = await _admin_context(pairing_id, current_user, db_session)
    _assert_pending(row, gateway)
    await _idle(gateway, db_session)
    if row.state != "claimed":
        raise HTTPException(409, "The local installation has not claimed this pairing")
    snapshot = _snapshot(row, gateway)
    return {
        "pairing": snapshot,
        "preview_digest": canonical_digest(
            {**snapshot, "actor": str(current_user.id), "revision": gateway.revision}
        ),
    }


@router.post("/{pairing_id}/confirm")
async def confirm_pairing(
    pairing_id: UUID,
    params: PairingConfirm,
    current_user: CurrentUser,
    db_session: DBSession,
):
    row, gateway = await _admin_context(pairing_id, current_user, db_session)
    preview = await preview_confirmation(pairing_id, current_user, db_session)
    if params.preview_digest != preview["preview_digest"]:
        raise HTTPException(409, "Pairing preview changed")
    # Possession alone never grants authority. Keep the Gateway disabled after approval.
    gateway.token_digest = row.credential_digest
    gateway.token_hint = row.credential_hint
    gateway.revision += 1
    gateway.updated_by_user_id = current_user.id
    gateway.updated_at = utcnow()
    row.state = "confirmed"
    snapshot = _snapshot(row, gateway)
    db_session.add(
        _audit(
            gateway=gateway,
            actor_user_id=current_user.id,
            action="pairing.confirmed",
            revision=gateway.revision,
            snapshot=snapshot,
            reason=row.reason,
        )
    )
    try:
        await db_session.commit()
    except IntegrityError as error:
        await db_session.rollback()
        raise HTTPException(
            409, "Credential identity conflicts; enroll with a new local credential"
        ) from error
    return {"pairing": snapshot, "gateway": gateway_snapshot(gateway)}


@router.post("/{pairing_id}/cancel")
async def cancel_pairing(
    pairing_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    row, gateway = await _admin_context(pairing_id, current_user, db_session)
    if row.state == "confirmed":
        raise HTTPException(
            409, "Use credential rotation to revoke a confirmed installation"
        )
    row.state = "cancelled"
    snapshot = _snapshot(row, gateway)
    db_session.add(
        _audit(
            gateway=gateway,
            actor_user_id=current_user.id,
            action="pairing.cancelled",
            revision=gateway.revision,
            snapshot=snapshot,
            reason=row.reason,
        )
    )
    await db_session.commit()
    return snapshot


@router.post("/{pairing_id}/status")
async def local_status(
    pairing_id: UUID,
    db_session: DBSession,
    x_airalogy_gateway_token: str = Header(default="", max_length=256),
):
    row = await db_session.get(InstrumentPairing, pairing_id)
    if (
        not row
        or not row.credential_digest
        or not hmac.compare_digest(
            gateway_token_digest(x_airalogy_gateway_token), row.credential_digest
        )
    ):
        raise HTTPException(404, "Pairing unavailable")
    gateway = await db_session.get(ResearchInstrumentGateway, row.gateway_id)
    return _snapshot(row, gateway)
