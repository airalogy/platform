"""Independent installation grants; never enable a Gateway or execute a driver."""

import asyncio
import hashlib
import hmac
from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.database import DBSession
from app.libs.file_storage import get_file_with_stream
from app.models.instrument_installation import (
    InstrumentDeviceBinding,
    InstrumentDeviceBindingAudit,
)
from app.models.instrument_package import InstrumentAdapterRelease
from app.models.instrument_pairing import InstrumentPairing
from app.models.knowledge import ResearchFile, ResearchFileAccessAudit, ResearchFileBlob
from app.models.research_execution import (
    ResearchInstrumentGateway,
    ResearchInstrumentJob,
)
from app.models.resource import Resource
from app.models.user import User
from app.routers.depends import CurrentUser
from app.routers.instrument_packages import _authorize
from app.routers.research_instrument_gateways import (
    _equipment_context,
    _gateway_context,
)
from app.services.access_control import resolve_resource_access
from app.services.account_security import get_auth_version
from app.services.instrument_installation_contract import (
    validate_receipt,
    validate_request,
)
from app.services.instrument_package_contract import MAX_ARCHIVE_BYTES
from app.services.knowledge import authorize_research_file
from app.services.research_runtime import canonical_digest, utcnow

router = APIRouter(prefix="/instrument-installations", tags=["Instrument installation"])
InstallerToken = Annotated[str, Header(alias="X-Airalogy-Installation-Token")]


class InstallationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request: dict
    resource_id: UUID
    release_id: UUID
    reason: str = Field(min_length=1, max_length=2000)
    fingerprint_confirmed: StrictBool = False

    @field_validator("request")
    @classmethod
    def validate_public_request(cls, value):
        return validate_request(value)


class InstallationConfirm(InstallationDraft):
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt: dict

    @field_validator("receipt")
    @classmethod
    def validate_local_receipt(cls, value):
        return validate_receipt(value)


class RevokeDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)


class RevokeConfirm(RevokeDraft):
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


def _snapshot(row, *, invalid_reason=None):
    state = row.state
    if state == "authorized" and row.expires_at <= utcnow():
        state = "expired"
    return {
        **row.as_dict(),
        "state": state,
        "invalid_reason": invalid_reason,
        "hardware_authorized": False,
        "activation_performed": False,
        "qualification_state": "not_qualified",
    }


def _audit(db, row, action, reason, actor_user_id=None):
    db.add(
        InstrumentDeviceBindingAudit(
            binding_id=row.id,
            revision=row.revision,
            action=action,
            actor_user_id=actor_user_id,
            reason=reason,
            snapshot=jsonable_encoder(_snapshot(row)),
        )
    )


async def _idle(db, gateway, resource_id):
    if gateway.enabled:
        raise HTTPException(409, "Disable the Gateway before authorizing installation")
    active = await db.scalar(
        select(ResearchInstrumentJob.id)
        .where(
            or_(
                ResearchInstrumentJob.gateway_id == gateway.id,
                ResearchInstrumentJob.resource_id == resource_id,
            ),
            ResearchInstrumentJob.status.in_(["leased", "running", "stop_requested"]),
        )
        .limit(1)
    )
    if active:
        raise HTTPException(
            409, "Reconcile active or uncertain instrument work before installation"
        )


async def _context(
    db, user, *, lab_id, gateway_id, resource_id, release_id, lock=False
):
    await _authorize(db, user, lab_id, lock=lock)
    gateway = await _gateway_context(db, user, gateway_id, lock=lock)
    if gateway.lab_id != lab_id:
        raise HTTPException(404, "Installation target not found")
    if lock:
        equipment = await db.scalar(
            select(Resource)
            .where(Resource.id == resource_id)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        if equipment is None:
            raise HTTPException(409, "Equipment is being changed; retry the preview")
    equipment, revision = await _equipment_context(
        db, current_user=user, gateway=gateway, resource_id=resource_id
    )
    statement = select(InstrumentAdapterRelease).where(
        InstrumentAdapterRelease.id == release_id,
        InstrumentAdapterRelease.lab_id == lab_id,
    )
    if lock:
        statement = statement.with_for_update().execution_options(
            populate_existing=True
        )
    release = await db.scalar(statement)
    if release is None:
        raise HTTPException(404, "Adapter release not found")
    archive = await db.get(ResearchFile, release.research_file_id)
    if archive is None or archive.archived_at or archive.lab_id != lab_id:
        raise HTTPException(409, "Approved adapter archive is unavailable")
    await authorize_research_file(db, user, archive)
    return gateway, equipment, revision, release


def _validate_release(release, descriptor):
    manifest = release.inspection["manifest"]
    if release.state != "approved":
        raise HTTPException(409, "Adapter source is not currently approved")
    if (
        release.archive_digest != descriptor["archive_digest"]
        or release.manifest_digest != descriptor["manifest_digest"]
        or manifest["entry_point"] != descriptor["entry_point"]
        or ".".join(descriptor["python_version"].split(".")[:2])
        not in manifest["compatibility"]["python_versions"]
    ):
        raise HTTPException(
            409, "Installation request does not match the approved package"
        )


async def _preview(db, user, params, *, lock=False):
    request = params.request
    gateway, equipment, revision, release = await _context(
        db,
        user,
        lab_id=UUID(request["lab_id"]),
        gateway_id=UUID(request["gateway_id"]),
        resource_id=params.resource_id,
        release_id=params.release_id,
        lock=lock,
    )
    await _idle(db, gateway, equipment.id)
    paired = await db.scalar(
        select(InstrumentPairing.id)
        .where(
            InstrumentPairing.gateway_id == gateway.id,
            InstrumentPairing.state == "confirmed",
            InstrumentPairing.credential_digest == gateway.token_digest,
        )
        .limit(1)
    )
    if paired is None:
        raise HTTPException(
            409, "Complete two-sided Gateway pairing before installation"
        )
    _validate_release(release, request["descriptor"])
    if not params.fingerprint_confirmed:
        raise HTTPException(
            422, "Compare and confirm the full local installer fingerprint"
        )
    pending = (
        await db.scalars(
            select(InstrumentDeviceBinding).where(
                InstrumentDeviceBinding.gateway_id == gateway.id,
                InstrumentDeviceBinding.state.in_(["authorized", "installing"]),
            )
        )
    ).all()
    for row in pending:
        if row.state == "authorized" and row.expires_at <= utcnow():
            if lock:
                row.state = "expired"
                row.revision += 1
                _audit(db, row, "expired", "Installation was not claimed before expiry")
                await db.flush()
        else:
            raise HTTPException(
                409, "Finish or revoke the pending Gateway installation first"
            )
    command = {
        "operation": "authorize_instrument_installation",
        "actor_user_id": str(user.id),
        "request": request,
        "resource_id": str(equipment.id),
        "resource_revision_id": str(revision.id),
        "resource_revision": revision.revision,
        "release_id": str(release.id),
        "release_revision": release.revision,
        "gateway_identity_pin": canonical_digest(
            {"gateway_id": str(gateway.id), "credential": gateway.token_digest}
        ),
        "creator_auth_version": await get_auth_version(db, user.id),
        "reason": params.reason,
    }
    return {
        **command,
        "preview_digest": canonical_digest(command),
        "hardware_authorized": False,
        "activation_performed": False,
    }, gateway


@router.post("/preview")
async def preview_installation(
    params: InstallationDraft, current_user: CurrentUser, db_session: DBSession
):
    preview, _ = await _preview(db_session, current_user, params)
    return preview


@router.post("")
async def authorize_installation(
    params: InstallationConfirm, current_user: CurrentUser, db_session: DBSession
):
    await _authorize(
        db_session, current_user, UUID(params.request["lab_id"]), lock=True
    )
    # Replay creates no new authorization and cannot revive an expired/revoked grant.
    existing = await db_session.get(InstrumentDeviceBinding, UUID(params.request["id"]))
    if existing is not None:
        await _managed(db_session, current_user, existing.id)
        if (
            existing.authorization_digest != params.preview_digest
            or existing.created_by_user_id != current_user.id
        ):
            raise HTTPException(409, "Installation request identity is already in use")
        return _snapshot(existing)
    preview, gateway = await _preview(db_session, current_user, params, lock=True)
    if preview["preview_digest"] != params.preview_digest:
        raise HTTPException(409, "Installation preview changed")
    row = InstrumentDeviceBinding(
        id=UUID(params.request["id"]),
        lab_id=gateway.lab_id,
        gateway_id=gateway.id,
        resource_id=params.resource_id,
        resource_revision_id=UUID(preview["resource_revision_id"]),
        resource_revision=preview["resource_revision"],
        release_id=params.release_id,
        release_revision=preview["release_revision"],
        gateway_credential_pin=gateway.token_digest,
        installer_token_digest=params.request["credential_digest"],
        installer_fingerprint=params.request["fingerprint"],
        descriptor=params.request["descriptor"],
        authorization_digest=params.preview_digest,
        state="authorized",
        revision=1,
        reason=params.reason,
        created_by_user_id=current_user.id,
        creator_auth_version=preview["creator_auth_version"],
        expires_at=utcnow() + timedelta(minutes=10),
    )
    db_session.add(row)
    try:
        await db_session.flush()
    except IntegrityError as error:
        await db_session.rollback()
        raise HTTPException(
            409,
            "Installation identity or pending grant changed; prepare a fresh request",
        ) from error
    _audit(db_session, row, "authorized", params.reason, current_user.id)
    await db_session.commit()
    return _snapshot(row)


async def _managed(db, user, binding_id, *, lock=False):
    row = await db.get(InstrumentDeviceBinding, binding_id)
    if row is None:
        raise HTTPException(404, "Installation not found")
    # Revocation/history must remain available after equipment or a source is
    # archived. Authorization still uses the original Lab and object scope.
    await _authorize(db, user, row.lab_id, lock=lock)
    gateway_query = select(ResearchInstrumentGateway).where(
        ResearchInstrumentGateway.id == row.gateway_id
    )
    if lock:
        gateway_query = gateway_query.with_for_update()
    await db.scalar(gateway_query)
    equipment = await db.get(Resource, row.resource_id)
    if equipment is None:
        raise HTTPException(404, "Equipment not found")
    access = await resolve_resource_access(
        db,
        user.id,
        row.lab_id,
        resource_type_id=equipment.resource_type_id,
        resource_id=equipment.id,
    )
    if not access.allows("equipment.service"):
        raise HTTPException(403, "Equipment management access denied")
    if lock:
        await db.refresh(row, with_for_update=True)
    return row


@router.get("")
async def list_installations(
    current_user: CurrentUser,
    db_session: DBSession,
    gateway_id: UUID,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    await _gateway_context(db_session, current_user, gateway_id, lock=False)
    rows = (
        await db_session.scalars(
            select(InstrumentDeviceBinding)
            .where(InstrumentDeviceBinding.gateway_id == gateway_id)
            .order_by(
                InstrumentDeviceBinding.created_at.desc(),
                InstrumentDeviceBinding.id.desc(),
            )
            .offset(offset)
            .limit(limit + 1)
        )
    ).all()
    items = []
    for row in rows[:limit]:
        try:
            await _managed(db_session, current_user, row.id)
        except HTTPException as error:
            if error.status_code in {403, 404, 422}:
                continue
            raise
        items.append(_snapshot(row))
    return {
        "items": items,
        "has_more": len(rows) > limit,
        "next_offset": offset + min(len(rows), limit),
    }


@router.get("/{binding_id}/history")
async def installation_history(
    binding_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    await _managed(db_session, current_user, binding_id)
    rows = (
        await db_session.scalars(
            select(InstrumentDeviceBindingAudit)
            .where(InstrumentDeviceBindingAudit.binding_id == binding_id)
            .order_by(InstrumentDeviceBindingAudit.revision)
        )
    ).all()
    return {"items": [row.as_dict() for row in rows]}


def _revoke_preview(row, user, params):
    if row.revision != params.expected_revision or row.state == "revoked":
        raise HTTPException(409, "Installation changed or was already revoked")
    command = {
        "operation": "revoke_instrument_installation",
        "id": str(row.id),
        "revision": row.revision,
        "actor_user_id": str(user.id),
        "reason": params.reason,
    }
    return {**command, "preview_digest": canonical_digest(command)}


@router.post("/{binding_id}/revoke/preview")
async def preview_revoke(
    binding_id: UUID,
    params: RevokeDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    row = await _managed(db_session, current_user, binding_id)
    return _revoke_preview(row, current_user, params)


@router.post("/{binding_id}/revoke")
async def revoke_installation(
    binding_id: UUID,
    params: RevokeConfirm,
    current_user: CurrentUser,
    db_session: DBSession,
):
    row = await _managed(db_session, current_user, binding_id, lock=True)
    if (
        _revoke_preview(row, current_user, params)["preview_digest"]
        != params.preview_digest
    ):
        raise HTTPException(409, "Installation revocation preview changed")
    row.state = "revoked"
    row.revision += 1
    _audit(db_session, row, "revoked", params.reason, current_user.id)
    await db_session.commit()
    return _snapshot(row)


async def _local(db, binding_id, token, *, require_current=True):
    if not token.startswith("aiinstall_") or len(token) != 53:
        raise HTTPException(401, "Invalid installation credential")
    row = await db.get(InstrumentDeviceBinding, binding_id)
    if row is None or not hmac.compare_digest(
        row.installer_token_digest, hashlib.sha256(token.encode()).hexdigest()
    ):
        raise HTTPException(401, "Invalid installation credential")
    user = await db.get(User, row.created_by_user_id)
    if user is None or await get_auth_version(db, user.id) != row.creator_auth_version:
        raise HTTPException(403, "Installation authorization owner changed")
    gateway, equipment, revision, release = await _context(
        db,
        user,
        lab_id=row.lab_id,
        gateway_id=row.gateway_id,
        resource_id=row.resource_id,
        release_id=row.release_id,
        lock=True,
    )
    await db.refresh(row, with_for_update=True)
    if require_current:
        if row.state in {"revoked", "expired"} or (
            row.state == "authorized" and row.expires_at <= utcnow()
        ):
            raise HTTPException(
                409, "Installation authorization expired or was revoked"
            )
        if (
            gateway.token_digest != row.gateway_credential_pin
            or revision.id != row.resource_revision_id
            or release.revision != row.release_revision
        ):
            raise HTTPException(409, "Installation target or source version changed")
        _validate_release(release, row.descriptor)
        await _idle(db, gateway, equipment.id)
    return row, release


@router.post("/{binding_id}/status")
async def installation_status(
    binding_id: UUID, installer_token: InstallerToken, db_session: DBSession
):
    row, _ = await _local(
        db_session, binding_id, installer_token, require_current=False
    )
    # Status recovery does not confer download, install or activation authority.
    return _snapshot(row)


@router.post("/{binding_id}/claim")
async def claim_installation(
    binding_id: UUID, installer_token: InstallerToken, db_session: DBSession
):
    row, _ = await _local(db_session, binding_id, installer_token)
    if row.state == "authorized":
        row.state = "installing"
        row.started_at = utcnow()
        row.expires_at = utcnow() + timedelta(minutes=15)
        row.revision += 1
        _audit(
            db_session,
            row,
            "claimed",
            "Independent local installer claimed the exact authorization",
        )
        await db_session.commit()
    elif row.state == "installing" and row.expires_at <= utcnow():
        raise HTTPException(
            409, "Installation download window expired; reconcile its receipt or revoke"
        )
    return _snapshot(row)


@router.post("/{binding_id}/package")
async def download_installation_package(
    binding_id: UUID, installer_token: InstallerToken, db_session: DBSession
):
    row, release = await _local(db_session, binding_id, installer_token)
    if row.state != "installing" or row.expires_at <= utcnow():
        raise HTTPException(409, "Claim a current installation before downloading")
    file = await db_session.get(ResearchFile, release.research_file_id)
    blob = await db_session.get(ResearchFileBlob, file.blob_id) if file else None
    if (
        file is None
        or file.archived_at
        or file.lab_id != row.lab_id
        or blob is None
        or not 0 < blob.size_bytes <= MAX_ARCHIVE_BYTES
    ):
        raise HTTPException(409, "Approved adapter archive is unavailable")
    blob_key, backend, size, checksum = (
        blob.storage_object_key,
        blob.storage_backend,
        blob.size_bytes,
        release.archive_digest,
    )
    file_id, lab_id, user_id = file.id, row.lab_id, row.created_by_user_id
    await db_session.commit()  # No transaction/row lock across object storage I/O.
    raw = bytearray()
    try:
        async with asyncio.timeout(60):
            async for chunk in get_file_with_stream(blob_key, backend=backend):
                if len(raw) + len(chunk) > size:
                    raise HTTPException(
                        409, "Adapter archive exceeds its recorded size"
                    )
                raw.extend(chunk)
    except TimeoutError as error:
        raise HTTPException(504, "Adapter archive download timed out") from error
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != checksum:
        raise HTTPException(409, "Stored adapter archive integrity changed")
    db_session.expire_all()
    row, _ = await _local(db_session, binding_id, installer_token)
    if row.state != "installing" or row.expires_at <= utcnow():
        raise HTTPException(409, "Installation authorization changed during download")
    row.revision += 1
    _audit(
        db_session,
        row,
        "package_downloaded",
        "Exact approved archive delivered to installation credential",
    )
    db_session.add(
        ResearchFileAccessAudit(
            research_file_id=file_id,
            lab_id=lab_id,
            actor_user_id=user_id,
            action="install_download",
            request_id=str(binding_id),
            user_agent="Delegated installation manager",
            outcome="allowed",
        )
    )
    await db_session.commit()
    return Response(
        bytes(raw),
        media_type="application/zip",
        headers={"Cache-Control": "no-store", "X-Content-SHA256": checksum},
    )


@router.post("/{binding_id}/receipt")
async def complete_installation(
    binding_id: UUID,
    params: Receipt,
    installer_token: InstallerToken,
    db_session: DBSession,
):
    row, _ = await _local(db_session, binding_id, installer_token)
    if row.descriptor != params.receipt["descriptor"]:
        raise HTTPException(409, "Receipt does not match the authorized configuration")
    if row.state == "installed":
        if row.receipt != params.receipt:
            raise HTTPException(409, "An immutable installation receipt already exists")
        return _snapshot(row)
    if row.state != "installing":
        raise HTTPException(409, "Installation has not been claimed")
    row.receipt = params.receipt
    row.state = "installed"
    row.installed_at = utcnow()
    row.revision += 1
    _audit(
        db_session,
        row,
        "installed",
        "Local installer reported inactive installation; not equipment qualification",
    )
    await db_session.commit()
    return _snapshot(row)
