"""Canonical signature and content-digest verification."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any


def canonical_payload(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def expected_job_signature(envelope: dict[str, Any], runner_token: str) -> str:
    runner_digest = hashlib.sha256(runner_token.encode("utf-8")).hexdigest()
    return hmac.new(
        runner_digest.encode("ascii"),
        canonical_payload(envelope),
        hashlib.sha256,
    ).hexdigest()


def verify_job_signature(
    envelope: dict[str, Any], signature: str, runner_token: str
) -> None:
    expected = expected_job_signature(envelope, runner_token)
    if not signature or not hmac.compare_digest(expected, signature):
        raise ValueError("Compute Job signature is invalid")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
