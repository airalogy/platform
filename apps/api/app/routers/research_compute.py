"""Lab-governed, immutable compute-environment contracts."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.database import DBSession
from app.models.lab import Lab
from app.models.research_execution import (
    ResearchComputeEnvironment,
    ResearchComputeEnvironmentRevision,
)
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.access_control import resolve_resource_access
from app.services.research_budget import normalize_currency
from app.services.research_compute import (
    COMPUTE_KEY_RE,
    EGRESS_HOST_RE,
    OCI_DIGEST_RE,
    all_compute_environment_revision_rows,
    compute_environment_snapshot,
    latest_compute_environment_revision,
    latest_compute_environment_rows,
)
from app.services.research_instruments import validate_bounded_schema
from app.services.research_runtime import canonical_digest

router = APIRouter(
    prefix="/research-compute-environments",
    tags=["research-compute-environments"],
)


class ComputeResourceLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cpu_millis: int = Field(default=1000, ge=100, le=64_000)
    memory_mb: int = Field(default=2048, ge=128, le=1_048_576)
    gpu_count: int = Field(default=0, ge=0, le=8)
    timeout_seconds: int = Field(default=3600, ge=1, le=86_400)
    max_output_bytes: int = Field(
        default=100 * 1024 * 1024,
        ge=1024,
        le=10 * 1024 * 1024 * 1024,
    )


class ComputeEnvironmentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lab_id: UUID
    environment_key: str = Field(min_length=2, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=4000)
    runner_protocol_version: Literal["airalogy.compute-runner.v1"] = (
        "airalogy.compute-runner.v1"
    )
    image_ref: str = Field(min_length=72, max_length=2048)
    runtime_version: str = Field(min_length=1, max_length=128)
    allowed_languages: list[Literal["python", "r"]] = Field(min_length=1, max_length=2)
    resource_limits: ComputeResourceLimits = Field(
        default_factory=ComputeResourceLimits
    )
    network_policy: Literal["none", "egress_allowlist"] = "none"
    allowed_egress_hosts: list[str] = Field(default_factory=list, max_length=100)
    input_schema: dict[str, Any]
    result_schema: dict[str, Any]
    software_manifest: dict[str, Any] = Field(default_factory=dict)
    estimated_cost_per_hour: Decimal | None = Field(
        default=None, ge=0, max_digits=38, decimal_places=18
    )
    currency: str | None = Field(default=None, max_length=16)
    risk: Literal["low", "medium", "high"] = "medium"
    enabled: bool = True
    reason: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def normalize(self):
        self.environment_key = self.environment_key.strip().lower()
        self.name = self.name.strip()
        self.description = self.description.strip()
        self.image_ref = self.image_ref.strip()
        self.runtime_version = self.runtime_version.strip()
        self.reason = self.reason.strip()
        if not COMPUTE_KEY_RE.fullmatch(self.environment_key):
            raise ValueError("Invalid compute environment key")
        if not OCI_DIGEST_RE.fullmatch(self.image_ref):
            raise ValueError("Compute image must use an immutable OCI sha256 digest")
        self.allowed_languages = list(dict.fromkeys(self.allowed_languages))
        self.allowed_egress_hosts = sorted(
            {item.strip().lower() for item in self.allowed_egress_hosts if item.strip()}
        )
        for host in self.allowed_egress_hosts:
            if not EGRESS_HOST_RE.fullmatch(host):
                raise ValueError(f"Invalid egress host: {host}")
            if ":" in host and not host.startswith("["):
                port = int(host.rsplit(":", 1)[1])
                if port > 65_535:
                    raise ValueError(f"Invalid egress port: {host}")
        if self.network_policy == "none" and self.allowed_egress_hosts:
            raise ValueError("A network-disabled environment cannot allow egress hosts")
        if self.network_policy == "egress_allowlist" and not self.allowed_egress_hosts:
            raise ValueError(
                "An egress allowlist environment requires at least one host"
            )
        self.input_schema = validate_bounded_schema(self.input_schema, "compute input")
        self.result_schema = validate_bounded_schema(
            self.result_schema, "compute result"
        )
        if len(str(self.software_manifest)) > 100_000:
            raise ValueError("Compute software manifest is too large")
        if (self.estimated_cost_per_hour is None) != (self.currency is None):
            raise ValueError("Estimated cost and currency must be provided together")
        if self.currency is not None:
            self.currency = normalize_currency(self.currency)
        return self


class ComputeEnvironmentCreate(ComputeEnvironmentDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class ComputeEnvironmentRevisionDraft(ComputeEnvironmentDraft):
    expected_revision: int = Field(ge=1)


class ComputeEnvironmentRevisionCreate(ComputeEnvironmentRevisionDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


async def _lab_access(
    db_session: DBSession,
    *,
    user: User,
    lab_id: UUID,
    capability: str,
) -> Lab:
    lab = await db_session.get(Lab, lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    access = await resolve_resource_access(db_session, user.id, lab_id)
    if not access.allows(capability):
        raise HTTPException(status_code=403, detail="Research compute access denied")
    return lab


async def _environment_context(
    db_session: DBSession,
    *,
    user: User,
    environment_id: UUID,
    lock: bool,
) -> tuple[ResearchComputeEnvironment, ResearchComputeEnvironmentRevision]:
    statement = select(ResearchComputeEnvironment).where(
        ResearchComputeEnvironment.id == environment_id,
        ResearchComputeEnvironment.archived_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    environment = (await db_session.scalars(statement)).first()
    if environment is None:
        raise HTTPException(status_code=404, detail="Compute environment not found")
    await _lab_access(
        db_session,
        user=user,
        lab_id=environment.lab_id,
        capability="research.compute.manage",
    )
    revision = await latest_compute_environment_revision(
        db_session, environment.id, lock=lock
    )
    if revision is None:
        raise HTTPException(
            status_code=409, detail="Compute environment has no revision"
        )
    return environment, revision


def _command(
    params: ComputeEnvironmentDraft,
    *,
    operation: str,
    environment_id: UUID | None,
    revision: int,
) -> dict[str, Any]:
    return {
        "operation": operation,
        "lab_id": str(params.lab_id),
        "compute_environment_id": str(environment_id) if environment_id else None,
        "environment_revision": revision,
        "environment_key": params.environment_key,
        "name": params.name,
        "description": params.description,
        "runner_protocol_version": params.runner_protocol_version,
        "image_ref": params.image_ref,
        "runtime_version": params.runtime_version,
        "allowed_languages": params.allowed_languages,
        "resource_limits": params.resource_limits.model_dump(mode="json"),
        "network_policy": params.network_policy,
        "allowed_egress_hosts": params.allowed_egress_hosts,
        "input_schema": params.input_schema,
        "result_schema": params.result_schema,
        "software_manifest": params.software_manifest,
        "estimated_cost_per_hour": (
            str(params.estimated_cost_per_hour)
            if params.estimated_cost_per_hour is not None
            else None
        ),
        "currency": params.currency,
        "risk": params.risk,
        "enabled": params.enabled,
    }


def _revision(
    environment: ResearchComputeEnvironment,
    params: ComputeEnvironmentDraft,
    *,
    revision: int,
    user_id: UUID,
) -> ResearchComputeEnvironmentRevision:
    return ResearchComputeEnvironmentRevision(
        compute_environment_id=environment.id,
        revision=revision,
        name=params.name,
        description=params.description,
        runner_protocol_version=params.runner_protocol_version,
        image_ref=params.image_ref,
        runtime_version=params.runtime_version,
        allowed_languages=params.allowed_languages,
        resource_limits=params.resource_limits.model_dump(mode="json"),
        network_policy=params.network_policy,
        allowed_egress_hosts=params.allowed_egress_hosts,
        input_schema=params.input_schema,
        result_schema=params.result_schema,
        software_manifest=params.software_manifest,
        estimated_cost_per_hour=params.estimated_cost_per_hour,
        currency=params.currency,
        risk=params.risk,
        enabled=params.enabled,
        reason=params.reason,
        created_by_user_id=user_id,
    )


@router.get("")
async def list_compute_environments(
    lab_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _lab_access(
        db_session,
        user=current_user,
        lab_id=lab_id,
        capability="research.compute.manage",
    )
    rows = await latest_compute_environment_rows(
        db_session, lab_id=lab_id, enabled_only=False
    )
    return {
        "items": [
            compute_environment_snapshot(environment, revision)
            for environment, revision in rows
        ]
    }


@router.get("/revisions")
async def list_compute_environment_revisions(
    lab_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _lab_access(
        db_session,
        user=current_user,
        lab_id=lab_id,
        capability="research.compute.manage",
    )
    rows = await all_compute_environment_revision_rows(
        db_session, lab_id=lab_id, enabled_only=False
    )
    return {
        "items": [
            compute_environment_snapshot(environment, revision)
            for environment, revision in rows
        ]
    }


@router.post("/preview")
async def preview_compute_environment(
    params: ComputeEnvironmentDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    lab = await _lab_access(
        db_session,
        user=current_user,
        lab_id=params.lab_id,
        capability="research.compute.manage",
    )
    command = _command(
        params,
        operation="create_research_compute_environment",
        environment_id=None,
        revision=1,
    )
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": {"lab_id": str(lab.id), "lab_uid": lab.uid, "name": lab.name},
        "effects": [
            "Create a Lab-scoped versioned Compute Environment",
            "Pin an immutable OCI image and explicit resource/network limits",
            "Execute no code and allocate no compute resources",
        ],
    }


@router.post("")
async def create_compute_environment(
    params: ComputeEnvironmentCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _lab_access(
        db_session,
        user=current_user,
        lab_id=params.lab_id,
        capability="research.compute.manage",
    )
    command = _command(
        params,
        operation="create_research_compute_environment",
        environment_id=None,
        revision=1,
    )
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(
            status_code=409, detail="Compute environment preview changed"
        )
    if await ResearchComputeEnvironment.exists(
        db_session,
        [
            ResearchComputeEnvironment.lab_id == params.lab_id,
            ResearchComputeEnvironment.environment_key == params.environment_key,
        ],
    ):
        raise HTTPException(status_code=409, detail="Compute environment key is in use")
    environment = ResearchComputeEnvironment(
        lab_id=params.lab_id,
        environment_key=params.environment_key,
        created_by_user_id=current_user.id,
    )
    db_session.add(environment)
    await db_session.flush()
    revision = _revision(environment, params, revision=1, user_id=current_user.id)
    db_session.add(revision)
    await db_session.flush()
    await db_session.commit()
    return compute_environment_snapshot(environment, revision)


@router.post("/{environment_id}/revisions/preview")
async def preview_compute_environment_revision(
    environment_id: UUID,
    params: ComputeEnvironmentRevisionDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    environment, current = await _environment_context(
        db_session,
        user=current_user,
        environment_id=environment_id,
        lock=False,
    )
    if current.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Compute environment changed")
    if environment.lab_id != params.lab_id:
        raise HTTPException(status_code=422, detail="Compute environment Lab changed")
    if environment.environment_key != params.environment_key:
        raise HTTPException(
            status_code=422, detail="Compute environment key is immutable"
        )
    command = _command(
        params,
        operation="revise_research_compute_environment",
        environment_id=environment.id,
        revision=current.revision + 1,
    )
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "current": compute_environment_snapshot(environment, current),
        "effects": [
            "Create a new immutable Compute Environment revision",
            "Keep existing Research Tasks pinned to their captured revision",
            "Block future selection when the new revision is disabled",
        ],
    }


@router.post("/{environment_id}/revisions")
async def create_compute_environment_revision(
    environment_id: UUID,
    params: ComputeEnvironmentRevisionCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    environment, current = await _environment_context(
        db_session,
        user=current_user,
        environment_id=environment_id,
        lock=True,
    )
    if current.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Compute environment changed")
    if environment.lab_id != params.lab_id:
        raise HTTPException(status_code=422, detail="Compute environment Lab changed")
    if environment.environment_key != params.environment_key:
        raise HTTPException(
            status_code=422, detail="Compute environment key is immutable"
        )
    next_revision = current.revision + 1
    command = _command(
        params,
        operation="revise_research_compute_environment",
        environment_id=environment.id,
        revision=next_revision,
    )
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(
            status_code=409, detail="Compute environment preview changed"
        )
    revision = _revision(
        environment,
        params,
        revision=next_revision,
        user_id=current_user.id,
    )
    db_session.add(revision)
    await db_session.flush()
    await db_session.commit()
    return compute_environment_snapshot(environment, revision)
