"""Security and serialization helpers for on-premises Instrument Gateways."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from jsonschema import Draft202012Validator, SchemaError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import (
    ResearchAction,
    ResearchActionStatus,
    ResearchRun,
    ResearchRunStatus,
    ResearchTask,
    ResearchTaskStatus,
)
from app.models.research_execution import (
    ResearchInstrumentCommand,
    ResearchInstrumentGateway,
    ResearchInstrumentJob,
    ResearchInstrumentJobStatus,
)
from app.models.resource import (
    BookingStatus,
    EquipmentBooking,
    Resource,
    ResourceRevision,
    ResourceStatus,
)
from app.services.access_control import resolve_resource_access

COMMAND_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")
TOKEN_PREFIX = "aigw_"
LEASE_TOKEN_PREFIX = "aijl_"
ACTIVE_INSTRUMENT_JOB_STATUSES = {
    ResearchInstrumentJobStatus.QUEUED.value,
    ResearchInstrumentJobStatus.LEASED.value,
    ResearchInstrumentJobStatus.RUNNING.value,
    ResearchInstrumentJobStatus.STOP_REQUESTED.value,
}


def generate_gateway_token() -> str:
    return f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


def gateway_token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def gateway_token_hint(token: str) -> str:
    return token[-8:]


def generate_job_lease_token() -> str:
    return f"{LEASE_TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


def job_lease_token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def sign_job_envelope(envelope: dict[str, Any], gateway_digest: str) -> str:
    """Sign a canonical job envelope with a key the Gateway can derive locally."""

    payload = json.dumps(
        envelope,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(gateway_digest.encode("ascii"), payload, hashlib.sha256).hexdigest()


def gateway_snapshot(gateway: ResearchInstrumentGateway) -> dict[str, Any]:
    return {
        "id": str(gateway.id),
        "lab_id": str(gateway.lab_id),
        "name": gateway.name,
        "description": gateway.description,
        "token_hint": gateway.token_hint,
        "enabled": gateway.enabled,
        "revision": gateway.revision,
        "last_seen_at": (
            gateway.last_seen_at.isoformat() if gateway.last_seen_at else None
        ),
        "revoked_at": gateway.revoked_at.isoformat() if gateway.revoked_at else None,
    }


def command_snapshot(command: ResearchInstrumentCommand) -> dict[str, Any]:
    return {
        "id": str(command.id),
        "gateway_id": str(command.gateway_id),
        "lab_id": str(command.lab_id),
        "resource_id": str(command.resource_id),
        "resource_revision_id": str(command.resource_revision_id),
        "resource_revision": command.resource_revision,
        "command_key": command.command_key,
        "command_version": command.command_version,
        "name": command.name,
        "description": command.description,
        "input_schema": command.input_schema,
        "output_schema": command.output_schema,
        "risk": command.risk,
        "device_confirmation_required": command.device_confirmation_required,
        "timeout_seconds": command.timeout_seconds,
        "enabled": command.enabled,
        "revision": command.revision,
        "archived_at": command.archived_at.isoformat() if command.archived_at else None,
    }


def instrument_job_snapshot(job: ResearchInstrumentJob) -> dict[str, Any]:
    return job.as_dict()


def _has_remote_reference(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "$ref" and isinstance(item, str) and "://" in item:
                return True
            if _has_remote_reference(item):
                return True
    elif isinstance(value, list):
        return any(_has_remote_reference(item) for item in value)
    return False


def validate_bounded_schema(schema: dict[str, Any], label: str) -> dict[str, Any]:
    """Accept local Draft 2020-12 object schemas; never dereference the network."""

    if len(str(schema)) > 50_000:
        raise ValueError(f"{label} Schema is too large")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        raise ValueError(f"Invalid {label} Schema: {error.message}") from error
    if schema.get("type") != "object":
        raise ValueError(f"{label} Schema must describe an object")
    if _has_remote_reference(schema):
        raise ValueError(f"{label} Schema cannot contain remote references")
    return schema


def validate_schema_payload(
    schema: dict[str, Any], payload: dict[str, Any], label: str
) -> dict[str, Any]:
    issues = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda item: list(item.absolute_path),
    )
    if not issues:
        return payload
    issue = issues[0]
    path = ".".join(str(item) for item in issue.absolute_path)
    raise ValueError(f"Invalid {label}{f' at {path}' if path else ''}: {issue.message}")


def resource_type_is_pinned(run: ResearchRun, resource: Resource) -> bool:
    """Keep mutable equipment behind the Task's pinned Resource Type boundary."""

    return any(
        str(item.get("source_id") or "") == str(resource.resource_type_id)
        for item in list((run.environment_snapshot or {}).get("resources") or [])
    )


async def available_instrument_command_options(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
    user_id: UUID,
    exclude_job_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Resolve only commands the requester can execute with an approved booking."""

    rows = list(
        (
            await db_session.execute(
                select(ResearchInstrumentCommand, ResearchInstrumentGateway)
                .join(
                    ResearchInstrumentGateway,
                    ResearchInstrumentGateway.id
                    == ResearchInstrumentCommand.gateway_id,
                )
                .where(
                    ResearchInstrumentCommand.lab_id == task.lab_id,
                    ResearchInstrumentCommand.enabled.is_(True),
                    ResearchInstrumentCommand.archived_at.is_(None),
                    ResearchInstrumentGateway.enabled.is_(True),
                    ResearchInstrumentGateway.revoked_at.is_(None),
                )
                .order_by(
                    ResearchInstrumentCommand.name,
                    ResearchInstrumentCommand.command_key,
                    ResearchInstrumentCommand.id,
                )
            )
        ).all()
    )
    now = datetime.now(UTC)
    items: list[dict[str, Any]] = []
    for command, gateway in rows:
        resource = await db_session.get(Resource, command.resource_id)
        revision = await db_session.get(ResourceRevision, command.resource_revision_id)
        if (
            resource is None
            or revision is None
            or resource.lab_id != task.lab_id
            or resource.archived_at is not None
            or resource.status != ResourceStatus.ACTIVE.value
            or resource.current_revision_id != revision.id
            or revision.revision != command.resource_revision
            or not resource_type_is_pinned(run, resource)
        ):
            continue
        access = await resolve_resource_access(
            db_session,
            user_id,
            task.lab_id,
            resource_type_id=resource.resource_type_id,
            resource_id=resource.id,
        )
        if not access.allows("equipment.book"):
            continue
        bookings = list(
            (
                await db_session.scalars(
                    select(EquipmentBooking)
                    .where(
                        EquipmentBooking.lab_id == task.lab_id,
                        EquipmentBooking.resource_id == resource.id,
                        EquipmentBooking.user_id == user_id,
                        EquipmentBooking.status == BookingStatus.APPROVED.value,
                        EquipmentBooking.ends_at > now,
                    )
                    .order_by(EquipmentBooking.starts_at, EquipmentBooking.id)
                )
            ).all()
        )
        if bookings:
            active_statement = select(ResearchInstrumentJob.equipment_booking_id).where(
                ResearchInstrumentJob.equipment_booking_id.in_(
                    [booking.id for booking in bookings]
                ),
                ResearchInstrumentJob.status.in_(ACTIVE_INSTRUMENT_JOB_STATUSES),
            )
            if exclude_job_id is not None:
                active_statement = active_statement.where(
                    ResearchInstrumentJob.id != exclude_job_id
                )
            active_booking_ids = set((await db_session.scalars(active_statement)).all())
            bookings = [
                booking for booking in bookings if booking.id not in active_booking_ids
            ]
        if not bookings:
            continue
        items.append(
            {
                **command_snapshot(command),
                "available": True,
                "gateway": {"id": str(gateway.id), "name": gateway.name},
                "resource": {
                    "id": str(resource.id),
                    "name": resource.name,
                    "code": resource.code,
                },
                "bookings": [booking.as_dict() for booking in bookings],
            }
        )
    return items


async def activate_aira_instrument_action(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
    action: ResearchAction,
) -> dict[str, Any]:
    """Re-resolve an approved Aira proposal before it can reach a Gateway."""

    job = await ResearchInstrumentJob.find_by(
        db_session, [ResearchInstrumentJob.action_id == action.id]
    )
    if job is None:
        raise ValueError("Instrument Job not found")
    if (
        action.status != ResearchActionStatus.PROPOSED.value
        or job.status != ResearchInstrumentJobStatus.QUEUED.value
    ):
        raise ValueError("Instrument Action is no longer awaiting approval")
    locked_context = []
    for model, item_id in (
        (ResearchInstrumentCommand, job.command_id),
        (ResearchInstrumentGateway, job.gateway_id),
        (Resource, job.resource_id),
        (EquipmentBooking, job.equipment_booking_id),
    ):
        item = (
            await db_session.scalars(
                select(model).where(model.id == item_id).with_for_update()
            )
        ).first()
        locked_context.append(item)
    if any(item is None for item in locked_context):
        raise ValueError("Instrument command, device, or booking no longer exists")
    options = await available_instrument_command_options(
        db_session,
        task=task,
        run=run,
        user_id=run.requested_by_user_id,
        exclude_job_id=job.id,
    )
    option = next(
        (item for item in options if str(item.get("id")) == str(job.command_id)),
        None,
    )
    if option is None:
        raise ValueError(
            "Instrument command or requester access is no longer available"
        )
    booking = next(
        (
            item
            for item in list(option.get("bookings") or [])
            if str(item.get("id")) == str(job.equipment_booking_id)
        ),
        None,
    )
    if booking is None:
        raise ValueError("The approved equipment booking is no longer available")
    pinned_fields = {
        "gateway_id": job.gateway_id,
        "resource_id": job.resource_id,
        "resource_revision_id": job.resource_revision_id,
        "resource_revision": job.resource_revision,
        "command_key": job.command_key,
        "command_version": job.command_version,
        "command_revision": job.command_revision,
        "input_schema": job.input_schema,
        "output_schema": job.output_schema,
        "risk": job.risk,
        "device_confirmation_required": job.device_confirmation_required,
        "timeout_seconds": job.timeout_seconds,
    }
    current_fields = {
        "gateway_id": option["gateway_id"],
        "resource_id": option["resource_id"],
        "resource_revision_id": option["resource_revision_id"],
        "resource_revision": option["resource_revision"],
        "command_key": option["command_key"],
        "command_version": option["command_version"],
        "command_revision": option["revision"],
        "input_schema": option["input_schema"],
        "output_schema": option["output_schema"],
        "risk": option["risk"],
        "device_confirmation_required": option["device_confirmation_required"],
        "timeout_seconds": option["timeout_seconds"],
    }
    if json.dumps(pinned_fields, sort_keys=True, default=str) != json.dumps(
        current_fields, sort_keys=True, default=str
    ):
        raise ValueError("Instrument command changed after the approval preview")
    validate_schema_payload(job.input_schema, job.arguments, "Instrument arguments")
    booking_in_use = await db_session.scalar(
        select(func.count())
        .select_from(ResearchInstrumentJob)
        .where(
            ResearchInstrumentJob.equipment_booking_id == job.equipment_booking_id,
            ResearchInstrumentJob.id != job.id,
            ResearchInstrumentJob.status.in_(ACTIVE_INSTRUMENT_JOB_STATUSES),
        )
    )
    if booking_in_use:
        raise ValueError("This equipment booking already has an active Instrument Job")
    action.status = ResearchActionStatus.QUEUED.value
    action.error = None
    action.revision += 1
    run.status = ResearchRunStatus.WAITING_FOR_INSTRUMENT.value
    run.last_error = None
    run.advance_generation += 1
    await db_session.flush()
    return {
        "instrument_job_id": str(job.id),
        "gateway_id": str(job.gateway_id),
        "command_key": job.command_key,
        "command_version": job.command_version,
        "equipment_booking_id": str(job.equipment_booking_id),
    }


async def reconcile_expired_instrument_leases(
    db_session: AsyncSession,
) -> dict[str, int]:
    """Recover undelivered jobs and fail closed on lost running-device leases."""

    from app.services.research_runtime import emit_research_event

    now = datetime.now(UTC)
    jobs = list(
        (
            await db_session.scalars(
                select(ResearchInstrumentJob)
                .where(
                    ResearchInstrumentJob.status.in_(
                        [
                            ResearchInstrumentJobStatus.LEASED.value,
                            ResearchInstrumentJobStatus.RUNNING.value,
                        ]
                    ),
                    ResearchInstrumentJob.lease_expires_at.is_not(None),
                    ResearchInstrumentJob.lease_expires_at <= now,
                )
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    recovered = 0
    stopped = 0
    for job in jobs:
        action = await db_session.get(ResearchAction, job.action_id)
        run = await db_session.get(ResearchRun, action.run_id) if action else None
        task = await db_session.get(ResearchTask, run.task_id) if run else None
        if action is None or run is None or task is None:
            continue
        if job.status == ResearchInstrumentJobStatus.LEASED.value:
            job.status = ResearchInstrumentJobStatus.QUEUED.value
            job.lease_token_digest = None
            job.lease_expires_at = None
            job.revision += 1
            recovered += 1
            await emit_research_event(
                db_session,
                task_id=task.id,
                run_id=run.id,
                action_id=action.id,
                kind="instrument_job.lease_expired",
                actor_user_id=None,
                payload={
                    "instrument_job_id": str(job.id),
                    "attempt": job.attempt_count,
                },
                idempotency_key=(
                    f"instrument-job:{job.id}:lease-expired:{job.attempt_count}"
                ),
            )
            continue
        reason = "Instrument Gateway heartbeat lease expired"
        job.status = ResearchInstrumentJobStatus.STOP_REQUESTED.value
        job.stop_reason = reason
        job.stop_requested_at = now
        job.revision += 1
        action.status = ResearchActionStatus.WAITING.value
        action.error = reason
        action.revision += 1
        if task.status != ResearchTaskStatus.CANCELLED.value:
            run.status = ResearchRunStatus.PAUSED.value
            run.last_error = f"{reason}; inspect the equipment before resuming."
            task.status = ResearchTaskStatus.PAUSED.value
            task.revision += 1
        stopped += 1
        await emit_research_event(
            db_session,
            task_id=task.id,
            run_id=run.id,
            action_id=action.id,
            kind="instrument_job.stop_requested",
            actor_user_id=None,
            payload={"instrument_job_id": str(job.id), "reason": reason},
            idempotency_key=f"instrument-job:{job.id}:lease-lost:{job.attempt_count}",
        )
    return {"recovered": recovered, "stop_requested": stopped}
