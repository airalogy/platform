"""Security and serialization helpers for isolated research Compute Runners."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.research_execution import (
    ResearchComputeEnvironment,
    ResearchComputeEnvironmentRevision,
    ResearchComputeRunner,
    ResearchComputeRunnerEnvironment,
)
from app.services.research_compute import compute_environment_snapshot

TOKEN_PREFIX = "aicr_"
RUNNER_HEARTBEAT_STALE_SECONDS = 180


def generate_compute_runner_token() -> str:
    return f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


def compute_runner_token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def compute_runner_token_hint(token: str) -> str:
    return token[-8:]


def compute_runner_snapshot(runner: ResearchComputeRunner) -> dict[str, Any]:
    return {
        "id": str(runner.id),
        "lab_id": str(runner.lab_id),
        "name": runner.name,
        "description": runner.description,
        "runner_protocol_version": runner.runner_protocol_version,
        "max_concurrent_jobs": runner.max_concurrent_jobs,
        "token_hint": runner.token_hint,
        "enabled": runner.enabled,
        "revision": runner.revision,
        "last_report": runner.last_report,
        "last_seen_at": runner.last_seen_at.isoformat() if runner.last_seen_at else None,
        "revoked_at": runner.revoked_at.isoformat() if runner.revoked_at else None,
    }


def compute_runner_binding_snapshot(
    binding: ResearchComputeRunnerEnvironment,
    environment: ResearchComputeEnvironment,
    revision: ResearchComputeEnvironmentRevision,
) -> dict[str, Any]:
    return {
        "id": str(binding.id),
        "runner_id": str(binding.runner_id),
        "lab_id": str(binding.lab_id),
        "compute_environment_id": str(binding.compute_environment_id),
        "compute_environment_revision_id": str(
            binding.compute_environment_revision_id
        ),
        "environment": compute_environment_snapshot(environment, revision),
        "created_at": binding.created_at.isoformat() if binding.created_at else None,
        "archived_at": binding.archived_at.isoformat() if binding.archived_at else None,
    }


def runner_report_is_execution_ready(runner: ResearchComputeRunner) -> bool:
    """Only a recently reporting Runner with the required isolation may lease work."""

    report = runner.last_report or {}
    security = report.get("security") or {}
    last_seen_at = runner.last_seen_at
    return bool(
        last_seen_at is not None
        and last_seen_at > datetime.now(UTC) - timedelta(seconds=RUNNER_HEARTBEAT_STALE_SECONDS)
        and report.get("protocol_version") == runner.runner_protocol_version
        and security.get("non_root") is True
        and security.get("read_only_root_filesystem") is True
        and security.get("network_isolation") is True
        and security.get("no_host_mounts") is True
    )
