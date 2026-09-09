"""Shared, bounded identity for a managed Instrument Job; contains no code."""

import hashlib
import json
import re
from uuid import UUID

SCHEMA = "airalogy.instrument-activation.v1"


def activation_digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def validate_activation_pin(value):
    fields = {
        "schema", "id", "binding_id", "qualification_id", "authorization_digest",
        "installation_id", "target_digest",
    }
    if not isinstance(value, dict) or set(value) != fields or value["schema"] != SCHEMA:
        raise ValueError("Invalid managed activation identity")
    for key in ("id", "binding_id", "qualification_id"):
        if not isinstance(value[key], str) or str(UUID(value[key])) != value[key]:
            raise ValueError("Activation IDs must be canonical UUIDs")
    for key in ("authorization_digest", "installation_id", "target_digest"):
        if not isinstance(value[key], str) or not re.fullmatch(r"[a-f0-9]{64}", value[key]):
            raise ValueError("Invalid activation digest")
    return dict(value)
