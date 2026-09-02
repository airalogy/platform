"""Security and serialization helpers for on-premises Instrument Gateways."""

from __future__ import annotations

import hashlib
import re
import secrets
from typing import Any

from jsonschema import Draft202012Validator, SchemaError

from app.models.research_execution import (
    ResearchInstrumentCommand,
    ResearchInstrumentGateway,
)

COMMAND_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")
TOKEN_PREFIX = "aigw_"


def generate_gateway_token() -> str:
    return f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


def gateway_token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def gateway_token_hint(token: str) -> str:
    return token[-8:]


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
