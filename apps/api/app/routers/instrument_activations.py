"""Previewed active-version selection; local startup remains an explicit operation."""

from datetime import datetime
from uuid import UUID, uuid5

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    model_validator,
)
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.database import DBSession
from app.models.instrument_activation import InstrumentActivation
from app.models.instrument_qualification import InstrumentQualification
from app.models.research_execution import (
    ResearchInstrumentCommand,
    ResearchInstrumentGateway,
    ResearchInstrumentJob,
)
from app.models.resource import Resource
from app.routers.depends import CurrentUser
from app.routers.instrument_installations import RevokeConfirm, RevokeDraft
from app.routers.instrument_qualifications import _access, _files, _source
from app.routers.research_instrument_jobs import GatewayToken, _authenticate_gateway
from app.services.access_control import resolve_resource_access
from app.services.account_security import get_auth_version
from app.services.instrument_activations import (
    activation_invalid_reason,
    activation_pin,
    command_pin,
    current_activation,
    file_delivery_block_reason,
)
from app.services.instrument_qualifications import qualification_state
from app.services.research_instruments import sign_job_envelope
from app.services.research_runtime import canonical_digest, utcnow

router = APIRouter(tags=["Instrument activation"])
BASE = "/instrument-installations/{binding_id}/activations"


class ActivationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: UUID
    qualification_id: UUID
    expected_active_id: UUID | None = None
    commands: list[str] = Field(min_length=1, max_length=10)
    expires_at: AwareDatetime
    reason: str = Field(min_length=1, max_length=2000)
    activation_confirmed: StrictBool = False

    @model_validator(mode="after")
    def valid(self):
        if not self.activation_confirmed or len(set(self.commands)) != len(
            self.commands
        ):
            raise ValueError(
                "Explicit activation confirmation and unique commands required"
            )
        if any(len(value) > 200 for value in self.commands):
            raise ValueError("Command identity is too long")
        return self


class ActivationConfirm(ActivationDraft):
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


async def _manage(db, user, binding_id, *, lock=False):
    binding = await _access(db, user, binding_id, lock=lock)
    resource = await db.get(Resource, binding.resource_id)
    access = await resolve_resource_access(
        db,
        user.id,
        binding.lab_id,
        resource_type_id=resource.resource_type_id,
        resource_id=resource.id,
    )
    if not access.allows("equipment.activate"):
        raise HTTPException(403, "Equipment activation access denied")
    return binding


async def _idle(db, binding):
    # Gateway lock is held by _manage for writes. Lock the actual Resource as well:
    # another Gateway cannot start work between preview confirmation and activation.
    resource = await db.scalar(
        select(Resource)
        .where(Resource.id == binding.resource_id)
        .with_for_update(skip_locked=True)
    )
    if resource is None:
        raise HTTPException(409, "Equipment is busy; retry after reconciliation")
    active = await db.scalar(
        select(ResearchInstrumentJob.id)
        .where(
            or_(
                ResearchInstrumentJob.gateway_id == binding.gateway_id,
                ResearchInstrumentJob.resource_id == binding.resource_id,
            ),
            ResearchInstrumentJob.status.in_(["leased", "running", "stop_requested"]),
        )
        .limit(1)
    )
    if active:
        raise HTTPException(
            409, "Finish or safely reconcile active work before switching versions"
        )


async def _preview(db, user, binding, params, *, lock=False):
    release = await _source(db, user, binding, lock=lock)
    qualification = await db.get(InstrumentQualification, params.qualification_id)
    if qualification is None or qualification.binding_id != binding.id:
        raise HTTPException(404, "Qualification not found")
    if await qualification_state(db, qualification, binding) != "qualified":
        raise HTTPException(
            409,
            "A current real-equipment qualification is required; simulation cannot activate equipment",
        )
    if not utcnow() < params.expires_at <= qualification.expires_at:
        raise HTTPException(
            422, "Activation must expire no later than its qualification"
        )
    await _files(
        db,
        user,
        binding,
        [UUID(pin["id"]) for pin in qualification.evidence_files],
        lock=lock,
    )
    current = await current_activation(db, binding.gateway_id)
    if (current.id if current else None) != params.expected_active_id:
        raise HTTPException(
            409, "The current active version changed; refresh and preview again"
        )
    elsewhere = await db.scalar(
        select(InstrumentActivation.id).where(
            InstrumentActivation.resource_id == binding.resource_id,
            InstrumentActivation.gateway_id != binding.gateway_id,
            InstrumentActivation.revoked_at.is_(None),
        )
    )
    if elsewhere:
        raise HTTPException(
            409, "Revoke this equipment's active version on its other Gateway first"
        )
    allowed = {
        f"{item['key']}@{item['version']}": item
        for item in qualification.pins["commands"]
    }
    if not set(params.commands) <= set(allowed):
        raise HTTPException(
            422, "Select only exact commands covered by this qualification"
        )
    # Source/qualification hashes are immutable; the source manifest is rechecked
    # to avoid manufacturing a command absent from the reviewed package.
    declared = {
        f"{item['key']}@{item['version']}": item
        for item in release.inspection["manifest"]["commands"]
    }
    changes = []
    for key in sorted(params.commands):
        contract = allowed[key]
        if declared.get(key) != contract:
            raise HTTPException(
                409, "Qualified command differs from the reviewed source"
            )
        if reason := file_delivery_block_reason(contract):
            raise HTTPException(409, reason)
        existing = await db.scalar(
            select(ResearchInstrumentCommand).where(
                ResearchInstrumentCommand.gateway_id == binding.gateway_id,
                ResearchInstrumentCommand.resource_id == binding.resource_id,
                ResearchInstrumentCommand.command_key == contract["key"],
                ResearchInstrumentCommand.command_version == contract["version"],
            )
        )
        changes.append(
            {
                "id": str(existing.id if existing else uuid5(params.id, key)),
                "previous_revision": existing.revision if existing else None,
                "revision": existing.revision + 1 if existing else 1,
                "contract": contract,
            }
        )
    gateway = await db.get(ResearchInstrumentGateway, binding.gateway_id)
    plan = {
        "operation": "activate_instrument_version",
        "id": str(params.id),
        "binding_id": str(binding.id),
        "binding_revision": binding.revision,
        "gateway_revision": gateway.revision,
        "resource_id": str(binding.resource_id),
        "qualification_id": str(qualification.id),
        "qualification_digest": qualification.confirmation_digest,
        "descriptor": binding.descriptor,
        "receipt": binding.receipt,
        "target": qualification.report["target"],
        "scope": qualification.scope,
        "previous_activation_id": str(current.id) if current else None,
        "commands": changes,
        "expires_at": params.expires_at.isoformat(),
        "reason": params.reason,
        "actor_user_id": str(user.id),
        "actor_auth_version": await get_auth_version(db, user.id),
        "local_start_required": True,
    }
    return {**plan, "preview_digest": canonical_digest(plan)}


async def _snapshot(db, row):
    reason = await activation_invalid_reason(db, row)
    return {
        **row.as_dict(),
        "pin": activation_pin(row),
        "effective_state": "revoked"
        if row.revoked_at
        else "invalid"
        if reason
        else "authorized",
        "invalid_reason": reason,
        "local_start_required": True,
    }


async def _readable(db, user, row):
    binding = await _manage(db, user, row.binding_id)
    await _source(db, user, binding)
    qualification = await db.get(InstrumentQualification, row.qualification_id)
    await _files(
        db, user, binding, [UUID(pin["id"]) for pin in qualification.evidence_files]
    )


@router.post(BASE + "/preview")
async def preview_activation(
    binding_id: UUID,
    params: ActivationDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    binding = await _manage(db_session, current_user, binding_id)
    return await _preview(db_session, current_user, binding, params)


@router.post(BASE)
async def activate_version(
    binding_id: UUID,
    params: ActivationConfirm,
    current_user: CurrentUser,
    db_session: DBSession,
):
    binding = await _manage(db_session, current_user, binding_id, lock=True)
    existing = await db_session.get(InstrumentActivation, params.id)
    if existing:
        if (
            existing.binding_id != binding.id
            or existing.created_by_user_id != current_user.id
            or existing.authorization_digest != params.preview_digest
        ):
            raise HTTPException(409, "Activation identity is already used")
        original = existing.plan
        if (
            str(params.qualification_id) != original["qualification_id"]
            or str(params.expected_active_id or "")
            != (original["previous_activation_id"] or "")
            or sorted(params.commands)
            != sorted(
                f"{c['contract']['key']}@{c['contract']['version']}"
                for c in original["commands"]
            )
            or params.expires_at != datetime.fromisoformat(original["expires_at"])
            or params.reason != original["reason"]
        ):
            raise HTTPException(
                409, "Activation retry differs from the original confirmation"
            )
        # Do not revive, re-enable or switch a version on an idempotent retry.
        await _readable(db_session, current_user, existing)
        return await _snapshot(db_session, existing)
    await _idle(db_session, binding)
    preview = await _preview(db_session, current_user, binding, params, lock=True)
    if preview["preview_digest"] != params.preview_digest:
        raise HTTPException(409, "Activation preview changed; review the impact again")
    previous = await current_activation(db_session, binding.gateway_id)
    if previous:
        previous.revoked_at = utcnow()
        previous.revoked_by_user_id = current_user.id
        previous.revoke_reason = f"Superseded by {params.id}: {params.reason}"
        await db_session.flush()
    row = InstrumentActivation(
        id=params.id,
        binding_id=binding.id,
        qualification_id=params.qualification_id,
        lab_id=binding.lab_id,
        gateway_id=binding.gateway_id,
        resource_id=binding.resource_id,
        authorization_digest=params.preview_digest,
        plan={key: value for key, value in preview.items() if key != "preview_digest"},
        commands=[],
        created_by_user_id=current_user.id,
    )
    db_session.add(row)
    pins = []
    for change in preview["commands"]:
        contract = change["contract"]
        command = await db_session.get(ResearchInstrumentCommand, UUID(change["id"]))
        if command is None:
            command = ResearchInstrumentCommand(
                id=UUID(change["id"]),
                gateway_id=binding.gateway_id,
                lab_id=binding.lab_id,
                resource_id=binding.resource_id,
                created_by_user_id=current_user.id,
            )
            db_session.add(command)
        command.command_key, command.command_version = (
            contract["key"],
            contract["version"],
        )
        command.name = contract["name"]
        command.description = "\n".join(contract["effects"])
        for field in (
            "input_schema",
            "output_schema",
            "risk",
            "device_confirmation_required",
            "safety_contract",
            "timeout_seconds",
        ):
            setattr(command, field, contract[field])
        command.resource_revision_id, command.resource_revision = (
            binding.resource_revision_id,
            binding.resource_revision,
        )
        command.revision = change["revision"]
        command.enabled, command.archived_at = True, None
        command.updated_by_user_id = current_user.id
        pins.append(command_pin(command))
    row.commands = pins
    gateway = await db_session.get(ResearchInstrumentGateway, binding.gateway_id)
    gateway.enabled = True
    gateway.revision += 1
    gateway.updated_by_user_id = current_user.id
    try:
        await db_session.flush()
    except IntegrityError as error:
        await db_session.rollback()
        raise HTTPException(
            409, "Concurrent active-version change; refresh and retry"
        ) from error
    result = jsonable_encoder(await _snapshot(db_session, row))
    await db_session.commit()
    return result


@router.get(BASE)
async def list_activations(
    binding_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
):
    binding = await _manage(db_session, current_user, binding_id)
    rows = list(
        (
            await db_session.scalars(
                select(InstrumentActivation)
                .where(InstrumentActivation.gateway_id == binding.gateway_id)
                .order_by(
                    InstrumentActivation.created_at.desc(),
                    InstrumentActivation.id.desc(),
                )
                .offset(offset)
                .limit(limit + 1)
            )
        ).all()
    )
    items = []
    for row in rows[:limit]:
        try:
            await _readable(db_session, current_user, row)
            items.append(await _snapshot(db_session, row))
        except HTTPException as error:
            if error.status_code not in {403, 404}:
                raise
            items.append(
                {
                    "id": str(row.id),
                    "binding_id": str(row.binding_id),
                    "effective_state": "revoked" if row.revoked_at else "redacted",
                    "details_redacted": True,
                }
            )
    current = await current_activation(db_session, binding.gateway_id)
    return {
        "items": items,
        "has_more": len(rows) > limit,
        "next_offset": offset + min(len(rows), limit),
        "current_id": str(current.id) if current else None,
    }


async def _record(db, user, binding_id, activation_id):
    binding = await _manage(db, user, binding_id, lock=True)
    row = await db.get(InstrumentActivation, activation_id)
    if row is None or row.binding_id != binding.id:
        raise HTTPException(404, "Activation not found")
    return binding, row


def _revocation(row, user, params):
    if params.expected_revision != 1:
        raise HTTPException(409, "Activation revision changed")
    value = {
        "operation": "revoke_instrument_activation",
        "id": str(row.id),
        "authorization_digest": row.authorization_digest,
        "actor_user_id": str(user.id),
        "reason": params.reason,
    }
    return {**value, "preview_digest": canonical_digest(value)}


@router.post(BASE + "/{activation_id}/revoke/preview")
async def preview_revoke_activation(
    binding_id: UUID,
    activation_id: UUID,
    params: RevokeDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    _, row = await _record(db_session, current_user, binding_id, activation_id)
    if row.revoked_at:
        raise HTTPException(409, "Activation was already revoked")
    return _revocation(row, current_user, params)


@router.post(BASE + "/{activation_id}/revoke")
async def revoke_activation(
    binding_id: UUID,
    activation_id: UUID,
    params: RevokeConfirm,
    current_user: CurrentUser,
    db_session: DBSession,
):
    binding, row = await _record(db_session, current_user, binding_id, activation_id)
    if (
        _revocation(row, current_user, params)["preview_digest"]
        != params.preview_digest
    ):
        raise HTTPException(409, "Activation revocation preview changed")
    if row.revoked_at:
        if (
            row.revoked_by_user_id != current_user.id
            or row.revoke_reason != params.reason
        ):
            raise HTTPException(409, "Activation was already revoked")
    else:
        row.revoked_at, row.revoked_by_user_id, row.revoke_reason = (
            utcnow(),
            current_user.id,
            params.reason,
        )
        gateway = await db_session.get(ResearchInstrumentGateway, binding.gateway_id)
        gateway.enabled = False
        gateway.revision += 1
        gateway.updated_by_user_id = current_user.id
        await db_session.commit()
    return {
        "id": str(row.id),
        "effective_state": "revoked",
        "safe_stop_confirmed": False,
    }


@router.get("/instrument-gateway/v1/activation")
async def runtime_activation(gateway_token: GatewayToken, db_session: DBSession):
    gateway = await _authenticate_gateway(db_session, gateway_token)
    row = await current_activation(db_session, gateway.id)
    reason = await activation_invalid_reason(db_session, row)
    if reason or not gateway.enabled:
        return {"activation": None, "invalid_reason": reason or "Gateway is disabled"}
    value = {
        "pin": activation_pin(row),
        "lab_id": str(row.lab_id),
        "gateway_id": str(row.gateway_id),
        "resource_id": str(row.resource_id),
        "descriptor": row.plan["descriptor"],
        "receipt": row.plan["receipt"],
        "target": row.plan["target"],
        "commands": row.commands,
        "expires_at": row.plan["expires_at"],
    }
    return {
        "activation": value,
        "signature": sign_job_envelope(value, gateway.token_digest),
    }
