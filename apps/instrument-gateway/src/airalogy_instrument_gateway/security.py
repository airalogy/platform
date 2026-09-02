"""Canonical envelope verification shared with the Platform contract."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


def canonical_payload(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def expected_job_signature(envelope: dict[str, Any], gateway_token: str) -> str:
    gateway_digest = hashlib.sha256(gateway_token.encode("utf-8")).hexdigest()
    return hmac.new(
        gateway_digest.encode("ascii"),
        canonical_payload(envelope),
        hashlib.sha256,
    ).hexdigest()


def verify_job_signature(
    envelope: dict[str, Any], signature: str, gateway_token: str
) -> None:
    expected = expected_job_signature(envelope, gateway_token)
    if not signature or not hmac.compare_digest(expected, signature):
        raise ValueError("Instrument Job signature is invalid")
