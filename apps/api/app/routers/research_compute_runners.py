"""Governed identities and exact environment bindings for Compute Runners."""

from __future__ import annotations

import hmac
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.database import DBSession
from app.models.lab import Lab
from app.models.research_execution import (
    ResearchComputeEnvironment,
    ResearchComputeEnvironmentRevision,
    ResearchComputeRunner,
    ResearchComputeRunnerAudit,
    ResearchComputeRunnerEnvironment,
)
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.access_control import resolve_resource_access
from app.services.research_compute import compute_environment_snapshot
from app.services.research_compute_runners import (
    TOKEN_PREFIX,
    compute_runner_binding_snapshot,
    compute_runner_snapshot,
    compute_runner_token_digest,
    compute_runner_token_hint,
    generate_compute_runner_token,
    runner_report_is_execution_ready,
)
from app.services.research_runtime import canonical_digest, utcnow

router = APIRouter(
    prefix="/research-compute-runners",
    tags=["research-compute-runners"],
)
runtime_router = APIRouter(
    prefix="/compute-runner/v1",
    tags=["compute-runner-runtime"],
)

RunnerToken = Annotated[str, Header(alias="X-Airalogy-Compute-Runner-Token")]


class ComputeRunnerDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lab_id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=4000)
    runner_protocol_version: Literal["airalogy.compute-runner.v1"] = (
        "airalogy.compute-runner.v1"
    )
    max_concurrent_jobs: int = Field(default=1, ge=1, le=64)
    enabled: bool = True
    reason: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def normalize(self):
        self.name = self.name.strip()
        self.description = self.description.strip()
        self.reason = self.reason.strip()
        return self


class ComputeRunnerCreate(ComputeRunnerDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class ComputeRunnerUpdateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=4000)
    runner_protocol_version: Literal["airalogy.compute-runner.v1"]
    max_concurrent_jobs: int = Field(ge=1, le=64)
    enabled: bool
    reason: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def normalize(self):
        self.name = self.name.strip()
        self.description = self.description.strip()
        self.reason = self.reason.strip()
        return self


class ComputeRunnerUpdate(ComputeRunnerUpdateDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class ComputeRunnerRotateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def normalize(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("Credential rotation reason is required")
        return self


class ComputeRunnerRotate(ComputeRunnerRotateDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class ComputeRunnerBindingDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runner_id: UUID
    compute_environment_revision_id: UUID
    expected_runner_revision: int = Field(ge=1)
    reason: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def normalize(self):
        self.reason = self.reason.strip()
        return self


class ComputeRunnerBindingCreate(ComputeRunnerBindingDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class ComputeRunnerBindingArchiveDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_runner_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def normalize(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("Binding removal reason is required")
        return self


class ComputeRunnerBindingArchive(ComputeRunnerBindingArchiveDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class ComputeRunnerSecurityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    non_root: bool
    read_only_root_filesystem: bool
    network_isolation: bool
    no_host_mounts: bool


class ComputeRunnerReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal["airalogy.compute-runner.v1"]
    runner_version: str = Field(min_length=1, max_length=64)
    executor_backend: Literal["docker", "podman", "kubernetes", "slurm"]
    active_jobs: int = Field(ge=0, le=64)
    available_slots: int = Field(ge=0, le=64)
    security: ComputeRunnerSecurityReport

    @model_validator(mode="after")
    def normalize(self):
        self.runner_version = self.runner_version.strip()
        return self


async def _lab_access(
    db_session: DBSession,
    *,
    user: User,
    lab_id: UUID,
) -> Lab:
    lab = await db_session.get(Lab, lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    access = await resolve_resource_access(db_session, user.id, lab_id)
    if not access.allows("research.compute.manage"):
        raise HTTPException(status_code=403, detail="Research compute access denied")
    return lab


async def _runner_context(
    db_session: DBSession,
    *,
    user: User,
    runner_id: UUID,
    lock: bool,
) -> ResearchComputeRunner:
    statement = select(ResearchComputeRunner).where(
        ResearchComputeRunner.id == runner_id,
        ResearchComputeRunner.revoked_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    runner = (await db_session.scalars(statement)).first()
    if runner is None:
        raise HTTPException(status_code=404, detail="Compute Runner not found")
    await _lab_access(db_session, user=user, lab_id=runner.lab_id)
    return runner


async def _environment_revision_context(
    db_session: DBSession,
    *,
    lab_id: UUID,
    revision_id: UUID,
    require_enabled: bool = True,
) -> tuple[ResearchComputeEnvironment, ResearchComputeEnvironmentRevision]:
    row = (
        await db_session.execute(
            select(ResearchComputeEnvironment, ResearchComputeEnvironmentRevision)
            .join(
                ResearchComputeEnvironmentRevision,
                ResearchComputeEnvironmentRevision.compute_environment_id
                == ResearchComputeEnvironment.id,
            )
            .where(
                ResearchComputeEnvironmentRevision.id == revision_id,
                ResearchComputeEnvironment.lab_id == lab_id,
                ResearchComputeEnvironment.archived_at.is_(None),
            )
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=422, detail="Compute Environment revision is unavailable"
        )
    environment, revision = row
    if require_enabled and not revision.enabled:
        raise HTTPException(
            status_code=422, detail="Compute Environment revision is disabled"
        )
    return environment, revision


async def _binding_context(
    db_session: DBSession,
    *,
    user: User,
    binding_id: UUID,
    lock: bool,
) -> tuple[
    ResearchComputeRunnerEnvironment,
    ResearchComputeRunner,
    ResearchComputeEnvironment,
    ResearchComputeEnvironmentRevision,
]:
    statement = select(ResearchComputeRunnerEnvironment).where(
        ResearchComputeRunnerEnvironment.id == binding_id,
        ResearchComputeRunnerEnvironment.archived_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    binding = (await db_session.scalars(statement)).first()
    if binding is None:
        raise HTTPException(status_code=404, detail="Compute Runner binding not found")
    runner = await _runner_context(
        db_session,
        user=user,
        runner_id=binding.runner_id,
        lock=lock,
    )
    environment, revision = await _environment_revision_context(
        db_session,
        lab_id=runner.lab_id,
        revision_id=binding.compute_environment_revision_id,
        require_enabled=False,
    )
    return binding, runner, environment, revision


def _runner_command(
    params: ComputeRunnerDraft,
    *,
    operation: str,
    runner_id: UUID | None,
) -> dict[str, Any]:
    return {
        "operation": operation,
        "runner_id": str(runner_id) if runner_id else None,
        "lab_id": str(params.lab_id),
        "name": params.name,
        "description": params.description,
        "runner_protocol_version": params.runner_protocol_version,
        "max_concurrent_jobs": params.max_concurrent_jobs,
        "enabled": params.enabled,
    }


def _runner_update_command(
    runner: ResearchComputeRunner,
    params: ComputeRunnerUpdateDraft,
) -> dict[str, Any]:
    return {
        "operation": "update_research_compute_runner",
        "runner_id": str(runner.id),
        "expected_revision": params.expected_revision,
        "name": params.name,
        "description": params.description,
        "runner_protocol_version": params.runner_protocol_version,
        "max_concurrent_jobs": params.max_concurrent_jobs,
        "enabled": params.enabled,
    }


def _rotation_command(
    runner: ResearchComputeRunner,
    params: ComputeRunnerRotateDraft,
) -> dict[str, Any]:
    return {
        "operation": "rotate_research_compute_runner_credential",
        "runner_id": str(runner.id),
        "expected_revision": params.expected_revision,
    }


def _binding_command(
    runner: ResearchComputeRunner,
    environment: ResearchComputeEnvironment,
    revision: ResearchComputeEnvironmentRevision,
    *,
    operation: str,
    binding_id: UUID | None,
    expected_runner_revision: int,
) -> dict[str, Any]:
    return {
        "operation": operation,
        "runner_id": str(runner.id),
        "binding_id": str(binding_id) if binding_id else None,
        "expected_runner_revision": expected_runner_revision,
        "compute_environment_id": str(environment.id),
        "compute_environment_revision_id": str(revision.id),
        "compute_environment_revision": revision.revision,
        "image_ref": revision.image_ref,
        "runner_protocol_version": revision.runner_protocol_version,
    }


def _audit(
    *,
    runner: ResearchComputeRunner,
    actor_user_id: UUID,
    action: str,
    snapshot: dict[str, Any],
    reason: str,
    binding_id: UUID | None = None,
) -> ResearchComputeRunnerAudit:
    return ResearchComputeRunnerAudit(
        runner_id=runner.id,
        binding_id=binding_id,
        lab_id=runner.lab_id,
        revision=runner.revision,
        action=action,
        snapshot=snapshot,
        reason=reason,
        actor_user_id=actor_user_id,
    )


async def authenticate_compute_runner(
    db_session: DBSession,
    token: str,
) -> ResearchComputeRunner:
    if not token or not token.startswith(TOKEN_PREFIX):
        raise HTTPException(status_code=401, detail="Invalid Compute Runner credential")
    digest = compute_runner_token_digest(token)
    runner = await ResearchComputeRunner.find_by(
        db_session,
        [
            ResearchComputeRunner.token_digest == digest,
            ResearchComputeRunner.revoked_at.is_(None),
        ],
    )
    if runner is None or not hmac.compare_digest(runner.token_digest, digest):
        raise HTTPException(status_code=401, detail="Invalid Compute Runner credential")
    return runner


async def _binding_rows(
    db_session: DBSession,
    *,
    runner_id: UUID,
) -> list[
    tuple[
        ResearchComputeRunnerEnvironment,
        ResearchComputeEnvironment,
        ResearchComputeEnvironmentRevision,
    ]
]:
    return list(
        (
            await db_session.execute(
                select(
                    ResearchComputeRunnerEnvironment,
                    ResearchComputeEnvironment,
                    ResearchComputeEnvironmentRevision,
                )
                .join(
                    ResearchComputeEnvironmentRevision,
                    ResearchComputeEnvironmentRevision.id
                    == ResearchComputeRunnerEnvironment.compute_environment_revision_id,
                )
                .join(
                    ResearchComputeEnvironment,
                    ResearchComputeEnvironment.id
                    == ResearchComputeRunnerEnvironment.compute_environment_id,
                )
                .where(
                    ResearchComputeRunnerEnvironment.runner_id == runner_id,
                    ResearchComputeRunnerEnvironment.archived_at.is_(None),
                    ResearchComputeEnvironment.archived_at.is_(None),
                )
                .order_by(
                    ResearchComputeEnvironmentRevision.name,
                    ResearchComputeEnvironmentRevision.revision,
                )
            )
        ).all()
    )


@router.get("")
async def list_compute_runners(
    lab_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _lab_access(db_session, user=current_user, lab_id=lab_id)
    runners = list(
        (
            await db_session.scalars(
                select(ResearchComputeRunner)
                .where(
                    ResearchComputeRunner.lab_id == lab_id,
                    ResearchComputeRunner.revoked_at.is_(None),
                )
                .order_by(ResearchComputeRunner.name, ResearchComputeRunner.id)
            )
        ).all()
    )
    return {"items": [compute_runner_snapshot(item) for item in runners]}


@router.post("/preview")
async def preview_compute_runner(
    params: ComputeRunnerDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    lab = await _lab_access(db_session, user=current_user, lab_id=params.lab_id)
    command = _runner_command(
        params, operation="create_research_compute_runner", runner_id=None
    )
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": {"lab_id": str(lab.id), "lab_uid": lab.uid, "name": lab.name},
        "effects": [
            "Create a Lab-scoped Compute Runner identity",
            "Issue one credential that is shown only once",
            "Authorize no Compute Environment until an exact revision is bound",
        ],
    }


@router.post("")
async def create_compute_runner(
    params: ComputeRunnerCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _lab_access(db_session, user=current_user, lab_id=params.lab_id)
    command = _runner_command(
        params, operation="create_research_compute_runner", runner_id=None
    )
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="Compute Runner preview changed")
    if await ResearchComputeRunner.exists(
        db_session,
        [
            ResearchComputeRunner.lab_id == params.lab_id,
            ResearchComputeRunner.name == params.name,
            ResearchComputeRunner.revoked_at.is_(None),
        ],
    ):
        raise HTTPException(status_code=409, detail="Compute Runner name is in use")
    credential = generate_compute_runner_token()
    runner = ResearchComputeRunner(
        lab_id=params.lab_id,
        name=params.name,
        description=params.description,
        runner_protocol_version=params.runner_protocol_version,
        max_concurrent_jobs=params.max_concurrent_jobs,
        token_digest=compute_runner_token_digest(credential),
        token_hint=compute_runner_token_hint(credential),
        enabled=params.enabled,
        created_by_user_id=current_user.id,
        updated_by_user_id=current_user.id,
    )
    db_session.add(runner)
    await db_session.flush()
    db_session.add(
        _audit(
            runner=runner,
            actor_user_id=current_user.id,
            action="runner.created",
            snapshot=compute_runner_snapshot(runner),
            reason=params.reason,
        )
    )
    await db_session.commit()
    return {"runner": compute_runner_snapshot(runner), "credential": credential}


@router.post("/items/{runner_id}/preview")
async def preview_compute_runner_update(
    runner_id: UUID,
    params: ComputeRunnerUpdateDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    runner = await _runner_context(
        db_session, user=current_user, runner_id=runner_id, lock=False
    )
    if runner.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Compute Runner changed")
    command = _runner_update_command(runner, params)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "current": compute_runner_snapshot(runner),
        "effects": [
            "Create an immutable Runner configuration audit event",
            "Stop future job leasing immediately when disabled",
            "Preserve the issued credential and exact environment bindings",
        ],
    }


@router.put("/items/{runner_id}")
async def update_compute_runner(
    runner_id: UUID,
    params: ComputeRunnerUpdate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    runner = await _runner_context(
        db_session, user=current_user, runner_id=runner_id, lock=True
    )
    if runner.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Compute Runner changed")
    command = _runner_update_command(runner, params)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="Compute Runner preview changed")
    duplicate = await ResearchComputeRunner.find_by(
        db_session,
        [
            ResearchComputeRunner.lab_id == runner.lab_id,
            ResearchComputeRunner.name == params.name,
            ResearchComputeRunner.id != runner.id,
            ResearchComputeRunner.revoked_at.is_(None),
        ],
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="Compute Runner name is in use")
    runner.name = params.name
    runner.description = params.description
    runner.runner_protocol_version = params.runner_protocol_version
    runner.max_concurrent_jobs = params.max_concurrent_jobs
    runner.enabled = params.enabled
    runner.revision += 1
    runner.updated_by_user_id = current_user.id
    runner.updated_at = utcnow()
    db_session.add(
        _audit(
            runner=runner,
            actor_user_id=current_user.id,
            action="runner.updated",
            snapshot=compute_runner_snapshot(runner),
            reason=params.reason,
        )
    )
    await db_session.commit()
    return compute_runner_snapshot(runner)


@router.post("/items/{runner_id}/rotate/preview")
async def preview_compute_runner_rotation(
    runner_id: UUID,
    params: ComputeRunnerRotateDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    runner = await _runner_context(
        db_session, user=current_user, runner_id=runner_id, lock=False
    )
    if runner.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Compute Runner changed")
    command = _rotation_command(runner, params)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "effects": [
            "Invalidate the old Runner credential immediately",
            "Issue a replacement credential that is shown only once",
            "Preserve Runner identity, environment bindings, and audit history",
        ],
    }


@router.post("/items/{runner_id}/rotate")
async def rotate_compute_runner_credential(
    runner_id: UUID,
    params: ComputeRunnerRotate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    runner = await _runner_context(
        db_session, user=current_user, runner_id=runner_id, lock=True
    )
    if runner.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Compute Runner changed")
    command = _rotation_command(runner, params)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="Credential rotation preview changed")
    credential = generate_compute_runner_token()
    runner.token_digest = compute_runner_token_digest(credential)
    runner.token_hint = compute_runner_token_hint(credential)
    runner.revision += 1
    runner.updated_by_user_id = current_user.id
    runner.updated_at = utcnow()
    db_session.add(
        _audit(
            runner=runner,
            actor_user_id=current_user.id,
            action="runner.credential_rotated",
            snapshot=compute_runner_snapshot(runner),
            reason=params.reason,
        )
    )
    await db_session.commit()
    return {"runner": compute_runner_snapshot(runner), "credential": credential}


@router.get("/items/{runner_id}/bindings")
async def list_compute_runner_bindings(
    runner_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    runner = await _runner_context(
        db_session, user=current_user, runner_id=runner_id, lock=False
    )
    rows = await _binding_rows(db_session, runner_id=runner.id)
    return {
        "items": [
            compute_runner_binding_snapshot(binding, environment, revision)
            for binding, environment, revision in rows
        ]
    }


@router.post("/bindings/preview")
async def preview_compute_runner_binding(
    params: ComputeRunnerBindingDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    runner = await _runner_context(
        db_session, user=current_user, runner_id=params.runner_id, lock=False
    )
    if runner.revision != params.expected_runner_revision:
        raise HTTPException(status_code=409, detail="Compute Runner changed")
    environment, revision = await _environment_revision_context(
        db_session,
        lab_id=runner.lab_id,
        revision_id=params.compute_environment_revision_id,
    )
    if revision.runner_protocol_version != runner.runner_protocol_version:
        raise HTTPException(
            status_code=422,
            detail="Runner and Compute Environment protocol versions differ",
        )
    command = _binding_command(
        runner,
        environment,
        revision,
        operation="bind_research_compute_environment",
        binding_id=None,
        expected_runner_revision=params.expected_runner_revision,
    )
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "runner": compute_runner_snapshot(runner),
        "environment": compute_environment_snapshot(environment, revision),
        "effects": [
            "Authorize this Runner for one exact Compute Environment revision",
            "Grant no access to future environment revisions",
            "Execute no code and create no Compute Job",
        ],
    }


@router.post("/bindings")
async def create_compute_runner_binding(
    params: ComputeRunnerBindingCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    runner = await _runner_context(
        db_session, user=current_user, runner_id=params.runner_id, lock=True
    )
    if runner.revision != params.expected_runner_revision:
        raise HTTPException(status_code=409, detail="Compute Runner changed")
    environment, revision = await _environment_revision_context(
        db_session,
        lab_id=runner.lab_id,
        revision_id=params.compute_environment_revision_id,
    )
    if revision.runner_protocol_version != runner.runner_protocol_version:
        raise HTTPException(
            status_code=422,
            detail="Runner and Compute Environment protocol versions differ",
        )
    command = _binding_command(
        runner,
        environment,
        revision,
        operation="bind_research_compute_environment",
        binding_id=None,
        expected_runner_revision=params.expected_runner_revision,
    )
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="Runner binding preview changed")
    existing = await ResearchComputeRunnerEnvironment.find_by(
        db_session,
        [
            ResearchComputeRunnerEnvironment.runner_id == runner.id,
            ResearchComputeRunnerEnvironment.compute_environment_revision_id
            == revision.id,
        ],
    )
    if existing is not None and existing.archived_at is None:
        raise HTTPException(status_code=409, detail="Runner binding already exists")
    if existing is None:
        binding = ResearchComputeRunnerEnvironment(
            runner_id=runner.id,
            lab_id=runner.lab_id,
            compute_environment_id=environment.id,
            compute_environment_revision_id=revision.id,
            created_by_user_id=current_user.id,
        )
        db_session.add(binding)
        await db_session.flush()
    else:
        binding = existing
        binding.archived_at = None
        binding.created_by_user_id = current_user.id
        binding.created_at = utcnow()
    runner.revision += 1
    runner.updated_by_user_id = current_user.id
    runner.updated_at = utcnow()
    snapshot = compute_runner_binding_snapshot(binding, environment, revision)
    db_session.add(
        _audit(
            runner=runner,
            binding_id=binding.id,
            actor_user_id=current_user.id,
            action="binding.created",
            snapshot=snapshot,
            reason=params.reason,
        )
    )
    await db_session.commit()
    return snapshot


@router.post("/bindings/{binding_id}/archive/preview")
async def preview_compute_runner_binding_archive(
    binding_id: UUID,
    params: ComputeRunnerBindingArchiveDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    binding, runner, environment, revision = await _binding_context(
        db_session, user=current_user, binding_id=binding_id, lock=False
    )
    if runner.revision != params.expected_runner_revision:
        raise HTTPException(status_code=409, detail="Compute Runner changed")
    command = _binding_command(
        runner,
        environment,
        revision,
        operation="archive_research_compute_environment_binding",
        binding_id=binding.id,
        expected_runner_revision=params.expected_runner_revision,
    )
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "binding": compute_runner_binding_snapshot(binding, environment, revision),
        "effects": [
            "Stop this Runner from leasing new jobs for the exact environment revision",
            "Preserve the binding and audit history",
            "Leave other Runner and environment authorizations unchanged",
        ],
    }


@router.post("/bindings/{binding_id}/archive")
async def archive_compute_runner_binding(
    binding_id: UUID,
    params: ComputeRunnerBindingArchive,
    current_user: CurrentUser,
    db_session: DBSession,
):
    binding, runner, environment, revision = await _binding_context(
        db_session, user=current_user, binding_id=binding_id, lock=True
    )
    if runner.revision != params.expected_runner_revision:
        raise HTTPException(status_code=409, detail="Compute Runner changed")
    command = _binding_command(
        runner,
        environment,
        revision,
        operation="archive_research_compute_environment_binding",
        binding_id=binding.id,
        expected_runner_revision=params.expected_runner_revision,
    )
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="Runner binding preview changed")
    binding.archived_at = utcnow()
    runner.revision += 1
    runner.updated_by_user_id = current_user.id
    runner.updated_at = utcnow()
    snapshot = compute_runner_binding_snapshot(binding, environment, revision)
    db_session.add(
        _audit(
            runner=runner,
            binding_id=binding.id,
            actor_user_id=current_user.id,
            action="binding.archived",
            snapshot=snapshot,
            reason=params.reason,
        )
    )
    await db_session.commit()
    return snapshot


@runtime_router.post("/status")
async def report_compute_runner_status(
    params: ComputeRunnerReport,
    runner_token: RunnerToken,
    db_session: DBSession,
):
    runner = await authenticate_compute_runner(db_session, runner_token)
    if params.active_jobs + params.available_slots > runner.max_concurrent_jobs:
        raise HTTPException(
            status_code=422,
            detail="Reported Compute Runner capacity exceeds its configured limit",
        )
    runner.last_report = params.model_dump(mode="json")
    runner.last_seen_at = utcnow()
    rows = await _binding_rows(db_session, runner_id=runner.id)
    await db_session.commit()
    return {
        "runner_id": str(runner.id),
        "runner_revision": runner.revision,
        "enabled": runner.enabled,
        "execution_ready": bool(
            runner.enabled and runner_report_is_execution_ready(runner)
        ),
        "environment_bindings": [
            compute_runner_binding_snapshot(binding, environment, revision)
            for binding, environment, revision in rows
        ],
    }
