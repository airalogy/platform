"""Versioned, Lab-governed compute-environment catalog helpers."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_execution import (
    ResearchComputeEnvironment,
    ResearchComputeEnvironmentRevision,
)

COMPUTE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")
OCI_DIGEST_RE = re.compile(
    r"^(?![^@]*://)[a-z0-9][a-z0-9._:/-]{0,1975}@sha256:[0-9a-f]{64}$"
)
EGRESS_HOST_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?|\[[0-9a-f:]+\])(?::[1-9][0-9]{0,4})?$"
)


def _money(value: Decimal | None) -> str | None:
    return format(value.normalize(), "f") if value is not None else None


def compute_environment_snapshot(
    environment: ResearchComputeEnvironment,
    revision: ResearchComputeEnvironmentRevision,
) -> dict[str, Any]:
    return {
        "key": f"compute:{environment.id}",
        "version": str(revision.revision),
        "kind": "compute",
        "name": revision.name,
        "description": revision.description,
        "source_type": "research_compute_environment_revision",
        "source_id": str(environment.id),
        "source_revision_id": str(revision.id),
        "executor_types": ["compute_runner"],
        "risk": revision.risk,
        "input_schema": revision.input_schema,
        "output_schema": revision.result_schema,
        "available": bool(revision.enabled and environment.archived_at is None),
        "unavailable_reason": (
            ""
            if revision.enabled and environment.archived_at is None
            else "Compute environment is disabled or archived"
        ),
        "metadata": {
            "lab_id": str(environment.lab_id),
            "environment_key": environment.environment_key,
            "environment_revision": revision.revision,
            "runner_protocol_version": revision.runner_protocol_version,
            "image_ref": revision.image_ref,
            "runtime_version": revision.runtime_version,
            "allowed_languages": revision.allowed_languages,
            "resource_limits": revision.resource_limits,
            "network_policy": revision.network_policy,
            "allowed_egress_hosts": revision.allowed_egress_hosts,
            "software_manifest": revision.software_manifest,
            "estimated_cost_per_hour": _money(revision.estimated_cost_per_hour),
            "currency": revision.currency,
            "change_reason": revision.reason,
        },
    }


async def latest_compute_environment_revision(
    db_session: AsyncSession,
    environment_id: UUID,
    *,
    lock: bool = False,
) -> ResearchComputeEnvironmentRevision | None:
    statement = (
        select(ResearchComputeEnvironmentRevision)
        .where(
            ResearchComputeEnvironmentRevision.compute_environment_id == environment_id
        )
        .order_by(ResearchComputeEnvironmentRevision.revision.desc())
        .limit(1)
    )
    if lock:
        statement = statement.with_for_update()
    return (await db_session.scalars(statement)).first()


async def latest_compute_environment_rows(
    db_session: AsyncSession,
    *,
    lab_id: UUID,
    enabled_only: bool,
) -> list[tuple[ResearchComputeEnvironment, ResearchComputeEnvironmentRevision]]:
    latest = (
        select(
            ResearchComputeEnvironmentRevision.compute_environment_id.label(
                "environment_id"
            ),
            func.max(ResearchComputeEnvironmentRevision.revision).label("revision"),
        )
        .group_by(ResearchComputeEnvironmentRevision.compute_environment_id)
        .subquery()
    )
    statement = (
        select(ResearchComputeEnvironment, ResearchComputeEnvironmentRevision)
        .join(
            latest,
            latest.c.environment_id == ResearchComputeEnvironment.id,
        )
        .join(
            ResearchComputeEnvironmentRevision,
            (
                ResearchComputeEnvironmentRevision.compute_environment_id
                == latest.c.environment_id
            )
            & (ResearchComputeEnvironmentRevision.revision == latest.c.revision),
        )
        .where(
            ResearchComputeEnvironment.lab_id == lab_id,
            ResearchComputeEnvironment.archived_at.is_(None),
        )
        .order_by(
            ResearchComputeEnvironmentRevision.name,
            ResearchComputeEnvironment.id,
        )
    )
    if enabled_only:
        statement = statement.where(
            ResearchComputeEnvironmentRevision.enabled.is_(True)
        )
    return list((await db_session.execute(statement)).all())


async def all_compute_environment_revision_rows(
    db_session: AsyncSession,
    *,
    lab_id: UUID,
    enabled_only: bool,
) -> list[tuple[ResearchComputeEnvironment, ResearchComputeEnvironmentRevision]]:
    """List exact revisions so old Task contracts remain bindable and reproducible."""

    statement = (
        select(ResearchComputeEnvironment, ResearchComputeEnvironmentRevision)
        .join(
            ResearchComputeEnvironmentRevision,
            ResearchComputeEnvironmentRevision.compute_environment_id
            == ResearchComputeEnvironment.id,
        )
        .where(
            ResearchComputeEnvironment.lab_id == lab_id,
            ResearchComputeEnvironment.archived_at.is_(None),
        )
        .order_by(
            ResearchComputeEnvironmentRevision.name,
            ResearchComputeEnvironmentRevision.revision.desc(),
            ResearchComputeEnvironment.id,
        )
    )
    if enabled_only:
        statement = statement.where(
            ResearchComputeEnvironmentRevision.enabled.is_(True)
        )
    return list((await db_session.execute(statement)).all())
