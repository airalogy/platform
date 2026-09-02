"""Governed configuration for on-premises Instrument Gateways."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select

from app.database import DBSession
from app.models.lab import Lab, LabRole, LabUser
from app.models.research_execution import (
    ResearchInstrumentCommand,
    ResearchInstrumentGateway,
    ResearchInstrumentGatewayAudit,
    ResearchInstrumentJob,
    ResearchInstrumentJobStatus,
)
from app.models.resource import (
    Resource,
    ResourceRevision,
    ResourceStatus,
    ResourceTypeRevision,
)
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.access_control import resolve_resource_access
from app.services.research_instruments import (
    COMMAND_KEY_RE,
    command_snapshot,
    gateway_snapshot,
    gateway_token_digest,
    gateway_token_hint,
    generate_gateway_token,
    validate_bounded_schema,
)
from app.services.research_runtime import canonical_digest, utcnow

router = APIRouter(
    prefix="/research-instrument-gateways",
    tags=["research-instrument-gateways"],
)


class GatewayDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lab_id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=4000)
    enabled: bool = True
    reason: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def normalize(self):
        self.name = self.name.strip()
        self.description = self.description.strip()
        self.reason = self.reason.strip()
        return self


class GatewayCreate(GatewayDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class GatewayUpdateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=4000)
    enabled: bool
    reason: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def normalize(self):
        self.name = self.name.strip()
        self.description = self.description.strip()
        self.reason = self.reason.strip()
        return self


class GatewayUpdate(GatewayUpdateDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class GatewayRotateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=4000)


class GatewayRotate(GatewayRotateDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class InstrumentCommandDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gateway_id: UUID
    resource_id: UUID
    command_key: str = Field(min_length=2, max_length=128)
    command_version: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=4000)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk: Literal["read_only", "low", "medium", "high"] = "medium"
    device_confirmation_required: bool = True
    timeout_seconds: int = Field(default=3600, ge=1, le=86400)
    enabled: bool = True
    reason: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def normalize(self):
        self.command_key = self.command_key.strip().lower()
        self.command_version = self.command_version.strip()
        self.name = self.name.strip()
        self.description = self.description.strip()
        self.reason = self.reason.strip()
        if not COMMAND_KEY_RE.fullmatch(self.command_key):
            raise ValueError("Invalid Instrument command key")
        self.input_schema = validate_bounded_schema(self.input_schema, "input")
        self.output_schema = validate_bounded_schema(self.output_schema, "output")
        if self.risk in {"medium", "high"} and not self.device_confirmation_required:
            raise ValueError(
                "Medium- and high-risk commands require device-side confirmation"
            )
        return self


class InstrumentCommandCreate(InstrumentCommandDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class InstrumentCommandUpdateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=4000)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk: Literal["read_only", "low", "medium", "high"]
    device_confirmation_required: bool
    timeout_seconds: int = Field(ge=1, le=86400)
    enabled: bool
    reason: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def normalize(self):
        self.name = self.name.strip()
        self.description = self.description.strip()
        self.reason = self.reason.strip()
        self.input_schema = validate_bounded_schema(self.input_schema, "input")
        self.output_schema = validate_bounded_schema(self.output_schema, "output")
        if self.risk in {"medium", "high"} and not self.device_confirmation_required:
            raise ValueError(
                "Medium- and high-risk commands require device-side confirmation"
            )
        return self


class InstrumentCommandUpdate(InstrumentCommandUpdateDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


async def _membership(
    db_session: DBSession,
    *,
    user: User,
    lab_id: UUID,
) -> tuple[Lab, LabUser]:
    lab = await db_session.get(Lab, lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    membership = await LabUser.find_by(
        db_session, [LabUser.lab_id == lab_id, LabUser.user_id == user.id]
    )
    if membership is None or membership.role > LabRole.MANAGER:
        raise HTTPException(
            status_code=403,
            detail="Only Lab Owners and Managers can manage Instrument Gateways",
        )
    return lab, membership


def _gateway_command(params: GatewayDraft) -> dict[str, Any]:
    return {
        "operation": "create_instrument_gateway",
        "lab_id": str(params.lab_id),
        "name": params.name,
        "description": params.description,
        "enabled": params.enabled,
    }


def _gateway_update_command(
    gateway: ResearchInstrumentGateway,
    params: GatewayUpdateDraft,
) -> dict[str, Any]:
    return {
        "operation": "update_instrument_gateway",
        "gateway_id": str(gateway.id),
        "expected_revision": params.expected_revision,
        "name": params.name,
        "description": params.description,
        "enabled": params.enabled,
    }


def _rotate_command(
    gateway: ResearchInstrumentGateway,
    params: GatewayRotateDraft,
) -> dict[str, Any]:
    return {
        "operation": "rotate_instrument_gateway_credential",
        "gateway_id": str(gateway.id),
        "expected_revision": params.expected_revision,
    }


def _instrument_command(
    params: InstrumentCommandDraft,
    *,
    resource_revision: ResourceRevision,
) -> dict[str, Any]:
    return {
        "operation": "create_instrument_command",
        "gateway_id": str(params.gateway_id),
        "resource_id": str(params.resource_id),
        "resource_revision_id": str(resource_revision.id),
        "resource_revision": resource_revision.revision,
        "command_key": params.command_key,
        "command_version": params.command_version,
        "name": params.name,
        "description": params.description,
        "input_schema": params.input_schema,
        "output_schema": params.output_schema,
        "risk": params.risk,
        "device_confirmation_required": params.device_confirmation_required,
        "timeout_seconds": params.timeout_seconds,
        "enabled": params.enabled,
    }


def _instrument_update_command(
    command: ResearchInstrumentCommand,
    params: InstrumentCommandUpdateDraft,
) -> dict[str, Any]:
    return {
        "operation": "update_instrument_command",
        "command_id": str(command.id),
        "expected_revision": params.expected_revision,
        "name": params.name,
        "description": params.description,
        "input_schema": params.input_schema,
        "output_schema": params.output_schema,
        "risk": params.risk,
        "device_confirmation_required": params.device_confirmation_required,
        "timeout_seconds": params.timeout_seconds,
        "enabled": params.enabled,
    }


async def _gateway_context(
    db_session: DBSession,
    current_user: User,
    gateway_id: UUID,
    *,
    lock: bool,
) -> ResearchInstrumentGateway:
    statement = select(ResearchInstrumentGateway).where(
        ResearchInstrumentGateway.id == gateway_id,
        ResearchInstrumentGateway.revoked_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    gateway = (await db_session.scalars(statement)).first()
    if gateway is None:
        raise HTTPException(status_code=404, detail="Instrument Gateway not found")
    await _membership(db_session, user=current_user, lab_id=gateway.lab_id)
    return gateway


async def _equipment_context(
    db_session: DBSession,
    *,
    current_user: User,
    gateway: ResearchInstrumentGateway,
    resource_id: UUID,
) -> tuple[Resource, ResourceRevision]:
    resource = await db_session.get(Resource, resource_id)
    if (
        resource is None
        or resource.lab_id != gateway.lab_id
        or resource.archived_at is not None
    ):
        raise HTTPException(status_code=422, detail="Equipment Resource is unavailable")
    if (
        resource.status != ResourceStatus.ACTIVE.value
        or resource.current_revision_id is None
    ):
        raise HTTPException(status_code=422, detail="Equipment Resource must be active")
    access = await resolve_resource_access(
        db_session,
        current_user.id,
        gateway.lab_id,
        resource_type_id=resource.resource_type_id,
        resource_id=resource.id,
    )
    if not access.allows("equipment.service"):
        raise HTTPException(
            status_code=403, detail="Equipment management access denied"
        )
    revision = await db_session.get(ResourceRevision, resource.current_revision_id)
    type_revision = (
        await db_session.get(ResourceTypeRevision, revision.resource_type_revision_id)
        if revision
        else None
    )
    if revision is None or type_revision is None:
        raise HTTPException(status_code=422, detail="Equipment revision is unavailable")
    if not (type_revision.capabilities or {}).get("booking"):
        raise HTTPException(
            status_code=422, detail="Resource is not governed equipment"
        )
    return resource, revision


def _audit(
    *,
    gateway: ResearchInstrumentGateway,
    actor_user_id: UUID,
    action: str,
    revision: int,
    snapshot: dict[str, Any],
    reason: str,
    command_id: UUID | None = None,
) -> ResearchInstrumentGatewayAudit:
    return ResearchInstrumentGatewayAudit(
        gateway_id=gateway.id,
        command_id=command_id,
        lab_id=gateway.lab_id,
        revision=revision,
        action=action,
        snapshot=snapshot,
        reason=reason,
        actor_user_id=actor_user_id,
    )


@router.get("")
async def list_instrument_gateways(
    lab_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _membership(db_session, user=current_user, lab_id=lab_id)
    gateways = list(
        (
            await db_session.scalars(
                select(ResearchInstrumentGateway)
                .where(
                    ResearchInstrumentGateway.lab_id == lab_id,
                    ResearchInstrumentGateway.revoked_at.is_(None),
                )
                .order_by(ResearchInstrumentGateway.name, ResearchInstrumentGateway.id)
            )
        ).all()
    )
    return {"items": [gateway_snapshot(item) for item in gateways]}


@router.post("/preview")
async def preview_instrument_gateway(
    params: GatewayDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    lab, _membership_row = await _membership(
        db_session, user=current_user, lab_id=params.lab_id
    )
    command = _gateway_command(params)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": {"lab_id": str(lab.id), "lab_uid": lab.uid, "name": lab.name},
        "effects": [
            "Create a Lab-scoped Instrument Gateway",
            "Issue one credential that is shown only once",
            "Allow no equipment command until an administrator adds an allowlisted schema",
        ],
    }


@router.post("")
async def create_instrument_gateway(
    params: GatewayCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _membership(db_session, user=current_user, lab_id=params.lab_id)
    command = _gateway_command(params)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(
            status_code=409, detail="Instrument Gateway preview changed"
        )
    if await ResearchInstrumentGateway.exists(
        db_session,
        [
            ResearchInstrumentGateway.lab_id == params.lab_id,
            ResearchInstrumentGateway.name == params.name,
            ResearchInstrumentGateway.revoked_at.is_(None),
        ],
    ):
        raise HTTPException(status_code=409, detail="Instrument Gateway already exists")
    credential = generate_gateway_token()
    gateway = ResearchInstrumentGateway(
        lab_id=params.lab_id,
        name=params.name,
        description=params.description,
        token_digest=gateway_token_digest(credential),
        token_hint=gateway_token_hint(credential),
        enabled=params.enabled,
        created_by_user_id=current_user.id,
        updated_by_user_id=current_user.id,
    )
    db_session.add(gateway)
    await db_session.flush()
    db_session.add(
        _audit(
            gateway=gateway,
            actor_user_id=current_user.id,
            action="gateway.created",
            revision=gateway.revision,
            snapshot=gateway_snapshot(gateway),
            reason=params.reason,
        )
    )
    await db_session.commit()
    return {"gateway": gateway_snapshot(gateway), "credential": credential}


@router.post("/{gateway_id}/preview")
async def preview_instrument_gateway_update(
    gateway_id: UUID,
    params: GatewayUpdateDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    gateway = await _gateway_context(db_session, current_user, gateway_id, lock=False)
    if gateway.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Instrument Gateway changed")
    command = _gateway_update_command(gateway, params)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "gateway": gateway_snapshot(gateway),
        "effects": [
            "Create an immutable configuration audit event",
            "Stop future job leasing immediately when disabled",
            "Leave issued credentials unchanged",
        ],
    }


@router.put("/{gateway_id}")
async def update_instrument_gateway(
    gateway_id: UUID,
    params: GatewayUpdate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    gateway = await _gateway_context(db_session, current_user, gateway_id, lock=True)
    if gateway.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Instrument Gateway changed")
    command = _gateway_update_command(gateway, params)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(
            status_code=409, detail="Instrument Gateway preview changed"
        )
    duplicate = await ResearchInstrumentGateway.find_by(
        db_session,
        [
            ResearchInstrumentGateway.lab_id == gateway.lab_id,
            ResearchInstrumentGateway.name == params.name,
            ResearchInstrumentGateway.id != gateway.id,
            ResearchInstrumentGateway.revoked_at.is_(None),
        ],
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="Instrument Gateway name is in use")
    gateway.name = params.name
    gateway.description = params.description
    gateway.enabled = params.enabled
    gateway.revision += 1
    gateway.updated_by_user_id = current_user.id
    gateway.updated_at = utcnow()
    db_session.add(
        _audit(
            gateway=gateway,
            actor_user_id=current_user.id,
            action="gateway.updated",
            revision=gateway.revision,
            snapshot=gateway_snapshot(gateway),
            reason=params.reason,
        )
    )
    await db_session.commit()
    return gateway_snapshot(gateway)


@router.post("/{gateway_id}/rotate/preview")
async def preview_gateway_credential_rotation(
    gateway_id: UUID,
    params: GatewayRotateDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    gateway = await _gateway_context(db_session, current_user, gateway_id, lock=False)
    if gateway.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Instrument Gateway changed")
    command = _rotate_command(gateway, params)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "effects": [
            "Invalidate the old Gateway credential immediately",
            "Issue a replacement credential that is shown only once",
            "Preserve Gateway identity, command allowlist, and audit history",
        ],
    }


@router.post("/{gateway_id}/rotate")
async def rotate_gateway_credential(
    gateway_id: UUID,
    params: GatewayRotate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    gateway = await _gateway_context(db_session, current_user, gateway_id, lock=True)
    if gateway.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Instrument Gateway changed")
    command = _rotate_command(gateway, params)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(
            status_code=409, detail="Credential rotation preview changed"
        )
    active_job_count = await db_session.scalar(
        select(func.count())
        .select_from(ResearchInstrumentJob)
        .where(
            ResearchInstrumentJob.gateway_id == gateway.id,
            ResearchInstrumentJob.status.in_(
                [
                    ResearchInstrumentJobStatus.LEASED.value,
                    ResearchInstrumentJobStatus.RUNNING.value,
                    ResearchInstrumentJobStatus.STOP_REQUESTED.value,
                ]
            ),
        )
    )
    if active_job_count:
        raise HTTPException(
            status_code=409,
            detail=(
                "Stop or finish active Instrument Jobs before rotating the "
                "Gateway credential"
            ),
        )
    credential = generate_gateway_token()
    gateway.token_digest = gateway_token_digest(credential)
    gateway.token_hint = gateway_token_hint(credential)
    gateway.revision += 1
    gateway.updated_by_user_id = current_user.id
    gateway.updated_at = utcnow()
    db_session.add(
        _audit(
            gateway=gateway,
            actor_user_id=current_user.id,
            action="gateway.credential_rotated",
            revision=gateway.revision,
            snapshot=gateway_snapshot(gateway),
            reason=params.reason.strip(),
        )
    )
    await db_session.commit()
    return {"gateway": gateway_snapshot(gateway), "credential": credential}


@router.get("/{gateway_id}/commands")
async def list_instrument_commands(
    gateway_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    gateway = await _gateway_context(db_session, current_user, gateway_id, lock=False)
    commands = list(
        (
            await db_session.scalars(
                select(ResearchInstrumentCommand)
                .where(
                    ResearchInstrumentCommand.gateway_id == gateway.id,
                    ResearchInstrumentCommand.archived_at.is_(None),
                )
                .order_by(
                    ResearchInstrumentCommand.resource_id,
                    ResearchInstrumentCommand.command_key,
                    ResearchInstrumentCommand.command_version,
                )
            )
        ).all()
    )
    return {"items": [command_snapshot(item) for item in commands]}


@router.post("/commands/preview")
async def preview_instrument_command(
    params: InstrumentCommandDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    gateway = await _gateway_context(
        db_session, current_user, params.gateway_id, lock=False
    )
    resource, revision = await _equipment_context(
        db_session,
        current_user=current_user,
        gateway=gateway,
        resource_id=params.resource_id,
    )
    command = _instrument_command(params, resource_revision=revision)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "gateway": gateway_snapshot(gateway),
        "equipment": {
            "id": str(resource.id),
            "name": resource.name,
            "code": resource.code,
            "revision": revision.revision,
        },
        "effects": [
            "Allow only this versioned command on this exact equipment revision",
            "Validate every future input and result against the captured schemas",
            "Require device-side confirmation for medium- and high-risk execution",
        ],
    }


@router.post("/commands")
async def create_instrument_command(
    params: InstrumentCommandCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    gateway = await _gateway_context(
        db_session, current_user, params.gateway_id, lock=True
    )
    _resource, revision = await _equipment_context(
        db_session,
        current_user=current_user,
        gateway=gateway,
        resource_id=params.resource_id,
    )
    command_data = _instrument_command(params, resource_revision=revision)
    if canonical_digest(command_data) != params.preview_digest:
        raise HTTPException(
            status_code=409, detail="Instrument command preview changed"
        )
    if await ResearchInstrumentCommand.exists(
        db_session,
        [
            ResearchInstrumentCommand.gateway_id == params.gateway_id,
            ResearchInstrumentCommand.resource_id == params.resource_id,
            ResearchInstrumentCommand.command_key == params.command_key,
            ResearchInstrumentCommand.command_version == params.command_version,
            ResearchInstrumentCommand.archived_at.is_(None),
        ],
    ):
        raise HTTPException(status_code=409, detail="Instrument command already exists")
    instrument_command = ResearchInstrumentCommand(
        gateway_id=gateway.id,
        lab_id=gateway.lab_id,
        resource_id=params.resource_id,
        resource_revision_id=revision.id,
        resource_revision=revision.revision,
        command_key=params.command_key,
        command_version=params.command_version,
        name=params.name,
        description=params.description,
        input_schema=params.input_schema,
        output_schema=params.output_schema,
        risk=params.risk,
        device_confirmation_required=params.device_confirmation_required,
        timeout_seconds=params.timeout_seconds,
        enabled=params.enabled,
        created_by_user_id=current_user.id,
        updated_by_user_id=current_user.id,
    )
    db_session.add(instrument_command)
    await db_session.flush()
    db_session.add(
        _audit(
            gateway=gateway,
            command_id=instrument_command.id,
            actor_user_id=current_user.id,
            action="command.created",
            revision=instrument_command.revision,
            snapshot=command_snapshot(instrument_command),
            reason=params.reason,
        )
    )
    await db_session.commit()
    return command_snapshot(instrument_command)


async def _command_context(
    db_session: DBSession,
    current_user: User,
    command_id: UUID,
    *,
    lock: bool,
) -> tuple[ResearchInstrumentCommand, ResearchInstrumentGateway]:
    statement = select(ResearchInstrumentCommand).where(
        ResearchInstrumentCommand.id == command_id,
        ResearchInstrumentCommand.archived_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    command = (await db_session.scalars(statement)).first()
    if command is None:
        raise HTTPException(status_code=404, detail="Instrument command not found")
    gateway = await _gateway_context(
        db_session, current_user, command.gateway_id, lock=lock
    )
    return command, gateway


@router.post("/commands/{command_id}/preview")
async def preview_instrument_command_update(
    command_id: UUID,
    params: InstrumentCommandUpdateDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    command, gateway = await _command_context(
        db_session, current_user, command_id, lock=False
    )
    if command.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Instrument command changed")
    command_data = _instrument_update_command(command, params)
    return {
        "preview_digest": canonical_digest(command_data),
        "command": command_data,
        "gateway": gateway_snapshot(gateway),
        "current": command_snapshot(command),
        "effects": [
            "Create a new allowlist revision for future Instrument Jobs",
            "Keep already-created jobs pinned to their original contract",
            "Stop new jobs immediately when disabled",
        ],
    }


@router.put("/commands/{command_id}")
async def update_instrument_command(
    command_id: UUID,
    params: InstrumentCommandUpdate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    command, gateway = await _command_context(
        db_session, current_user, command_id, lock=True
    )
    if command.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Instrument command changed")
    command_data = _instrument_update_command(command, params)
    if canonical_digest(command_data) != params.preview_digest:
        raise HTTPException(
            status_code=409, detail="Instrument command preview changed"
        )
    command.name = params.name
    command.description = params.description
    command.input_schema = params.input_schema
    command.output_schema = params.output_schema
    command.risk = params.risk
    command.device_confirmation_required = params.device_confirmation_required
    command.timeout_seconds = params.timeout_seconds
    command.enabled = params.enabled
    command.revision += 1
    command.updated_by_user_id = current_user.id
    command.updated_at = utcnow()
    db_session.add(
        _audit(
            gateway=gateway,
            command_id=command.id,
            actor_user_id=current_user.id,
            action="command.updated",
            revision=command.revision,
            snapshot=command_snapshot(command),
            reason=params.reason,
        )
    )
    await db_session.commit()
    return command_snapshot(command)
