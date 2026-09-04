"""Strict local view of a signed Instrument Job envelope."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

INTERLOCK_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


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


def _safety_contract(value: Any) -> dict[str, Any]:
    if value is None:
        value = {}
    contract = _mapping(value, "command.safety_contract")
    allowed = {
        "required_interlocks",
        "operator_presence_required",
        "emergency_stop_required",
    }
    if set(contract) - allowed:
        raise ValueError("Instrument Job safety contract contains unsupported fields")
    raw_interlocks = contract.get("required_interlocks") or []
    if not isinstance(raw_interlocks, list) or len(raw_interlocks) > 32:
        raise ValueError("Instrument Job safety contract interlocks are invalid")
    interlocks: list[str] = []
    for value in raw_interlocks:
        if (
            not isinstance(value, str)
            or not INTERLOCK_KEY_RE.fullmatch(value)
            or value in interlocks
        ):
            raise ValueError("Instrument Job safety contract interlock is invalid")
        interlocks.append(value)
    for key in ("operator_presence_required", "emergency_stop_required"):
        if key in contract and not isinstance(contract[key], bool):
            raise TypeError(f"Instrument Job safety contract {key} must be boolean")
    return {
        "required_interlocks": interlocks,
        "operator_presence_required": bool(contract.get("operator_presence_required")),
        "emergency_stop_required": bool(contract.get("emergency_stop_required")),
    }


def validate_safety_attestation(contract: dict[str, Any], value: Any) -> dict[str, Any]:
    attestation = _mapping(value or {}, "safety attestation")
    allowed = {
        "interlocks",
        "operator_present",
        "emergency_stop_available",
        "reference",
    }
    if set(attestation) - allowed:
        raise ValueError("Instrument safety attestation contains unsupported fields")
    interlocks = _mapping(attestation.get("interlocks") or {}, "safety interlocks")
    if len(interlocks) > 64:
        raise ValueError("Instrument safety attestation contains too many interlocks")
    normalized_interlocks: dict[str, bool] = {}
    for key, passed in interlocks.items():
        if not isinstance(key, str) or not INTERLOCK_KEY_RE.fullmatch(key):
            raise ValueError("Instrument safety attestation key is invalid")
        if not isinstance(passed, bool):
            raise TypeError("Instrument safety attestation value must be boolean")
        normalized_interlocks[key] = passed
    missing = [
        key
        for key in contract["required_interlocks"]
        if normalized_interlocks.get(key) is not True
    ]
    if missing:
        raise ValueError(
            f"Required safety interlocks did not pass: {', '.join(missing)}"
        )
    operator_present = attestation.get("operator_present", False)
    emergency_stop_available = attestation.get("emergency_stop_available", False)
    if not isinstance(operator_present, bool) or not isinstance(
        emergency_stop_available, bool
    ):
        raise TypeError("Instrument safety attestation flags must be boolean")
    if contract["operator_presence_required"] and not operator_present:
        raise ValueError("Instrument safety contract requires operator presence")
    if contract["emergency_stop_required"] and not emergency_stop_available:
        raise ValueError("Instrument safety contract requires an emergency stop")
    reference = attestation.get("reference") or ""
    if not isinstance(reference, str) or len(reference.strip()) > 255:
        raise ValueError("Instrument safety attestation reference is invalid")
    if (
        contract["required_interlocks"]
        or contract["operator_presence_required"]
        or contract["emergency_stop_required"]
    ) and not reference.strip():
        raise ValueError("Instrument safety attestation reference is required")
    return {
        "interlocks": normalized_interlocks,
        "operator_present": operator_present,
        "emergency_stop_available": emergency_stop_available,
        "reference": reference.strip(),
    }


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
    safety_contract: dict[str, Any]
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
            safety_contract=_safety_contract(command.get("safety_contract")),
            timeout_seconds=_integer(
                command.get("timeout_seconds"),
                "command.timeout_seconds",
                minimum=1,
            ),
        )
