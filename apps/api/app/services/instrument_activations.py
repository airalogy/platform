"""One governed active version per Gateway and Resource, pinned into every job."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from app.models.instrument_activation import (
    InstrumentActivation,
    InstrumentJobActivation,
)
from app.models.instrument_installation import InstrumentDeviceBinding
from app.models.instrument_qualification import InstrumentQualification
from app.models.resource import Resource
from app.models.user import User
from app.services.access_control import resolve_resource_access
from app.services.account_security import get_auth_version
from app.services.instrument_activation_contract import (
    SCHEMA,
    activation_digest,
    validate_activation_pin,
)
from app.services.instrument_qualifications import qualification_state


def activation_pin(row):
    return validate_activation_pin(
        {
            "schema": SCHEMA,
            "id": str(row.id),
            "binding_id": str(row.binding_id),
            "qualification_id": str(row.qualification_id),
            "authorization_digest": row.authorization_digest,
            "installation_id": row.plan["descriptor"]["installation_id"],
            "target_digest": activation_digest(row.plan["target"]),
        }
    )


async def current_activation(db, gateway_id, resource_id=None):
    query = select(InstrumentActivation).where(
        InstrumentActivation.gateway_id == gateway_id,
        InstrumentActivation.revoked_at.is_(None),
    )
    if resource_id is not None:
        query = query.where(InstrumentActivation.resource_id == resource_id)
    return await db.scalar(query)


async def activation_invalid_reason(db, row):
    if row is None or row.revoked_at:
        return "Managed activation is missing or revoked"
    if datetime.fromisoformat(row.plan["expires_at"]) <= datetime.now(UTC):
        return "Managed activation expired"
    binding = await db.get(InstrumentDeviceBinding, row.binding_id)
    qualification = await db.get(InstrumentQualification, row.qualification_id)
    if (
        binding is None
        or qualification is None
        or qualification.binding_id != binding.id
    ):
        return "Managed installation or qualification is missing"
    state = await qualification_state(db, qualification, binding)
    if state != "qualified":
        return f"Managed qualification is not current: {state}"
    if (
        row.gateway_id != binding.gateway_id
        or row.resource_id != binding.resource_id
        or row.lab_id != binding.lab_id
        or row.plan["descriptor"] != binding.descriptor
        or row.plan["receipt"] != binding.receipt
        or row.plan["qualification_digest"] != qualification.confirmation_digest
    ):
        return "Managed activation target changed"
    # Authority remains organizational: revoking the approver's current access
    # invalidates new execution, rather than preserving a stale permission bit.
    creator = await db.get(User, row.created_by_user_id)
    try:
        from app.routers.instrument_qualifications import _access, _files, _source

        if creator is None:
            return "Activation approver is unavailable"
        if await get_auth_version(db, creator.id) != row.plan["actor_auth_version"]:
            return "Activation approver credentials changed"
        await _access(db, creator, binding.id)
        resource = await db.get(Resource, binding.resource_id)
        access = await resolve_resource_access(
            db,
            creator.id,
            binding.lab_id,
            resource_type_id=resource.resource_type_id,
            resource_id=resource.id,
        )
        if not access.allows("equipment.activate"):
            return "Equipment activation access was revoked"
        await _source(db, creator, binding)
        await _files(
            db,
            creator,
            binding,
            [UUID(pin["id"]) for pin in qualification.evidence_files],
        )
    except HTTPException:
        return "Activation approver or source access was revoked"
    return None


def command_pin(command):
    return {
        "id": str(command.id),
        "revision": command.revision,
        "key": command.command_key,
        "version": command.command_version,
        "input_schema": command.input_schema,
        "output_schema": command.output_schema,
        "risk": command.risk,
        "device_confirmation_required": command.device_confirmation_required,
        "safety_contract": command.safety_contract,
        "timeout_seconds": command.timeout_seconds,
        "resource_revision_id": str(command.resource_revision_id),
        "resource_revision": command.resource_revision,
    }


async def executable_activation(db, gateway_id, resource_id, command):
    """Return the current grant or an error; never fall back to manual execution."""
    row = await current_activation(db, gateway_id, resource_id)
    reason = await activation_invalid_reason(db, row)
    if reason:
        return None, reason
    if command is None or not command.enabled or command.archived_at:
        return None, "Managed command is unavailable"
    if command.gateway_id != gateway_id or command.resource_id != resource_id:
        return None, "Managed command belongs to another target"
    if command_pin(command) not in row.commands:
        return None, "Command differs from the approved active version"
    return row, None


async def execution_block_reason(db, gateway_id, resource_id, command, job=None):
    from app.services.instrument_installations import managed_execution_block_reason

    managed = await managed_execution_block_reason(db, gateway_id, resource_id)
    if not managed:
        # A pinned job cannot turn into legacy work if its history is damaged.
        if job is not None and await db.get(InstrumentJobActivation, job.id):
            return "Managed job lost its installation history"
        return None
    row, reason = await executable_activation(db, gateway_id, resource_id, command)
    if reason:
        return reason
    if job is not None:
        pinned = await db.get(InstrumentJobActivation, job.id)
        if (
            pinned is None
            or pinned.activation_id != row.id
            or pinned.pin != activation_pin(row)
        ):
            return "Instrument Job is not pinned to the current active version"
        from app.models.instrument_output import InstrumentOutputBatch
        from app.services.instrument_output_contract import declarations

        declared = next(
            item["contract"]["outputs"]
            for item in row.plan["commands"]
            if item["contract"]["key"] == command.command_key
            and item["contract"]["version"] == command.command_version
        )
        batch = await db.get(InstrumentOutputBatch, job.id)
        if declared and (
            batch is None or batch.plan["outputs"] != declarations(declared)
        ):
            return "Instrument Job has no matching pinned file intake plan"
        expected = next(item for item in row.commands if item["id"] == str(command.id))
        if (
            str(job.resource_revision_id) != expected["resource_revision_id"]
            or job.resource_revision != expected["resource_revision"]
        ):
            return "Instrument Job equipment revision differs from the activation"
        if any(
            getattr(job, field) != expected[key]
            for field, key in (
                ("command_revision", "revision"),
                ("command_key", "key"),
                ("command_version", "version"),
                ("input_schema", "input_schema"),
                ("output_schema", "output_schema"),
                ("risk", "risk"),
                ("device_confirmation_required", "device_confirmation_required"),
                ("safety_contract", "safety_contract"),
                ("timeout_seconds", "timeout_seconds"),
            )
        ):
            return "Instrument Job contract changed from its approved version"
    return None


async def assert_execution_allowed(db, gateway_id, resource_id, command, job=None):
    reason = await execution_block_reason(db, gateway_id, resource_id, command, job)
    if reason:
        raise HTTPException(409, reason)


async def pin_job_activation(db, job, command):
    await assert_execution_allowed(db, job.gateway_id, job.resource_id, command)
    row = await current_activation(db, job.gateway_id, job.resource_id)
    if row is not None:
        db.add(
            InstrumentJobActivation(
                job_id=job.id, activation_id=row.id, pin=activation_pin(row)
            )
        )
        from app.services.instrument_outputs import pin_outputs

        await pin_outputs(db, job, command, row)


async def job_activation_pin(db, job):
    row = await db.get(InstrumentJobActivation, job.id)
    return row.pin if row else None
