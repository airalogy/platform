"""Security and serialization helpers for on-premises Instrument Gateways."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from datetime import UTC, datetime
from typing import Any

from jsonschema import Draft202012Validator, SchemaError
from sqlalchemy import select
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

COMMAND_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")
TOKEN_PREFIX = "aigw_"
LEASE_TOKEN_PREFIX = "aijl_"


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
    raise ValueError(
        f"Invalid {label}{f' at {path}' if path else ''}: {issue.message}"
    )


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
