"""Strict local view of a signed Instrument Job envelope."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"Instrument Job {name} must be an object")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Instrument Job {name} is required")
    return value.strip()


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"Instrument Job {name} must be an integer >= {minimum}")
    return value


def _instant(value: Any, name: str) -> datetime:
    raw = _text(value, name)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as error:
        raise ValueError(f"Instrument Job {name} is not an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"Instrument Job {name} must include a timezone")
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class InstrumentJobEnvelope:
    raw: dict[str, Any]
    job_id: str
    action_id: str
    task_id: str
    run_id: str
    lease_expires_at: datetime
    resource_id: str
    resource_revision_id: str
    resource_revision: int
    booking_id: str
    booking_starts_at: datetime
    booking_ends_at: datetime
    command_key: str
    command_version: str
    command_revision: int
    arguments: dict[str, Any]
    risk: str
    device_confirmation_required: bool
    timeout_seconds: int

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> InstrumentJobEnvelope:
        if raw.get("schema") != "airalogy.instrument-job.v1":
            raise ValueError("Unsupported Instrument Job envelope schema")
        resource = _mapping(raw.get("resource"), "resource")
        booking = _mapping(raw.get("booking"), "booking")
        command = _mapping(raw.get("command"), "command")
        arguments = _mapping(command.get("arguments"), "command.arguments")
        risk = _text(command.get("risk"), "command.risk")
        if risk not in {"read_only", "low", "medium", "high"}:
            raise ValueError("Instrument Job command.risk is invalid")
        confirmation_required = command.get("device_confirmation_required")
        if not isinstance(confirmation_required, bool):
            raise TypeError(
                "Instrument Job command.device_confirmation_required must be boolean"
            )
        if risk in {"medium", "high"} and not confirmation_required:
            raise ValueError("Medium- and high-risk jobs require device confirmation")
        issued_at = _instant(raw.get("issued_at"), "issued_at")
        lease_expires_at = _instant(raw.get("lease_expires_at"), "lease_expires_at")
        booking_starts_at = _instant(booking.get("starts_at"), "booking.starts_at")
        booking_ends_at = _instant(booking.get("ends_at"), "booking.ends_at")
        if not issued_at < lease_expires_at:
            raise ValueError("Instrument Job lease window is invalid")
        if not booking_starts_at < booking_ends_at:
            raise ValueError("Instrument Job booking window is invalid")
        return cls(
            raw=dict(raw),
            job_id=_text(raw.get("job_id"), "job_id"),
            action_id=_text(raw.get("action_id"), "action_id"),
            task_id=_text(raw.get("task_id"), "task_id"),
            run_id=_text(raw.get("run_id"), "run_id"),
            lease_expires_at=lease_expires_at,
            resource_id=_text(resource.get("id"), "resource.id"),
            resource_revision_id=_text(
                resource.get("revision_id"), "resource.revision_id"
            ),
            resource_revision=_integer(
                resource.get("revision"), "resource.revision", minimum=1
            ),
            booking_id=_text(booking.get("id"), "booking.id"),
            booking_starts_at=booking_starts_at,
            booking_ends_at=booking_ends_at,
            command_key=_text(command.get("key"), "command.key"),
            command_version=_text(command.get("version"), "command.version"),
            command_revision=_integer(
                command.get("revision"), "command.revision", minimum=1
            ),
            arguments=arguments,
            risk=risk,
            device_confirmation_required=confirmation_required,
            timeout_seconds=_integer(
                command.get("timeout_seconds"),
                "command.timeout_seconds",
                minimum=1,
            ),
        )
