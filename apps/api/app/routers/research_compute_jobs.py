"""Approval-gated Compute Jobs leased to isolated, Lab-governed Runners."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import tempfile
from datetime import timedelta
from typing import Annotated, Any, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

from app.config import config
from app.database import DBSession
from app.libs.file_storage import (
    default_storage_backend,
    default_storage_namespace,
    get_file_with_stream,
    upload_file,
)
from app.models.knowledge import (
    OwnerScope,
    ResearchFile,
    ResearchFileBlob,
    Visibility,
)
from app.models.lab import Lab
from app.models.project import Project
from app.models.research import (
    ResearchAction,
    ResearchActionKind,
    ResearchActionStatus,
    ResearchApproval,
    ResearchApprovalStatus,
    ResearchRun,
    ResearchRunStatus,
    ResearchTask,
    ResearchTaskComputeEnvironment,
    ResearchTaskStatus,
)
from app.models.research_asset import DataAsset, DataAssetStatus, DataAssetVersion
from app.models.research_execution import (
    ResearchComputeEnvironmentRevision,
    ResearchComputeJob,
    ResearchComputeJobInput,
    ResearchComputeJobOutput,
    ResearchComputeJobStatus,
    ResearchComputeRunner,
    ResearchComputeRunnerEnvironment,
)
from app.models.user import User
from app.routers.depends import CurrentUser
from app.routers.research_compute_runners import (
    RunnerToken,
    authenticate_compute_runner,
)
from app.services.knowledge import assert_research_file_upload_quota
from app.services.research_budget import (
    ResearchBudgetError,
    project_budget_change,
    research_budget_snapshot,
)
from app.services.research_compute_contracts import (
    MAX_OUTPUT_FILES,
    MAX_SOURCE_BYTES,
    ComputeInputDraft,
    ComputeOutputDraft,
    validate_compute_action_payload,
    validate_compute_output_budget,
)
from app.services.research_compute_jobs import (
    ACTIVE_COMPUTE_JOB_STATUSES,
    FINAL_COMPUTE_JOB_STATUSES,
    LEASE_SECONDS,
    compute_action_command,
    compute_estimated_cost,
    compute_job_snapshot,
    compute_lease_token_digest,
    compute_output_snapshot,
    compute_source_digest,
    eligible_runner_count,
    exact_compute_inputs,
    generate_compute_lease_token,
    pinned_compute_environment,
    release_compute_budget,
    runner_active_job_count,
    settle_compute_budget,
    sign_compute_envelope,
    validate_pinned_compute_inputs,
)
from app.services.research_compute_runners import runner_report_is_execution_ready
from app.services.research_instruments import validate_schema_payload
from app.services.research_runtime import (
    append_aira_result,
    canonical_digest,
    create_plan_version,
    emit_research_event,
    enqueue_research_advance,
    request_action_approval,
    require_research_capability,
    research_run_has_executable_ai_path,
    utcnow,
)

router = APIRouter(tags=["research-compute-jobs"])
runtime_router = APIRouter(prefix="/compute-runner/v1", tags=["compute-runner-runtime"])

LeaseToken = Annotated[str, Header(alias="X-Airalogy-Compute-Lease")]
OUTPUT_UPLOAD_MIN_BYTES_PER_SECOND = 256 * 1024


class ComputeActionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compute_environment_revision_id: UUID
    language: Literal["python", "r"]
    source_code: str = Field(min_length=1, max_length=MAX_SOURCE_BYTES)
    input_payload: dict[str, Any] = Field(default_factory=dict)
    input_assets: list[ComputeInputDraft] = Field(default_factory=list, max_length=32)
    output_files: list[ComputeOutputDraft] = Field(
        default_factory=list, max_length=MAX_OUTPUT_FILES
    )
    title: str = Field(default="", max_length=255)
    description: str = Field(default="", max_length=20_000)
    idempotency_key: str = Field(min_length=8, max_length=160)

    @model_validator(mode="after")
    def normalize(self):
        self.title = self.title.strip()
        self.description = self.description.strip()
        self.idempotency_key = self.idempotency_key.strip()
        validate_compute_action_payload(
            source_code=self.source_code,
            source_byte_limit=MAX_SOURCE_BYTES,
            input_payload=self.input_payload,
            input_assets=self.input_assets,
            output_files=self.output_files,
        )
        return self


class ComputeActionCreate(ComputeActionDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class ComputeCancelDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def normalize(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("Cancellation reason is required")
        return self


class ComputeCancel(ComputeCancelDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class ComputeUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wall_seconds: int = Field(ge=0, le=86_400)
    cpu_seconds: float = Field(default=0, ge=0, le=5_529_600, allow_inf_nan=False)
    max_memory_mb: int = Field(default=0, ge=0, le=1_048_576)
    gpu_seconds: float = Field(default=0, ge=0, le=691_200, allow_inf_nan=False)
    output_bytes: int = Field(default=0, ge=0, le=10 * 1024 * 1024 * 1024)


class RunnerCompletedOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_id: UUID
    checksum_sha256: str = Field(min_length=64, max_length=64)
    byte_size: int = Field(ge=0, le=10 * 1024 * 1024 * 1024)

    @model_validator(mode="after")
    def normalize(self):
        self.checksum_sha256 = self.checksum_sha256.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", self.checksum_sha256):
            raise ValueError("Compute output checksum is invalid")
        return self


class RunnerComplete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: dict[str, Any] = Field(default_factory=dict)
    usage: ComputeUsage
    outputs: list[RunnerCompletedOutput] = Field(
        default_factory=list, max_length=MAX_OUTPUT_FILES
    )

    @model_validator(mode="after")
    def validate_outputs(self):
        output_ids = [item.output_id for item in self.outputs]
        if len(output_ids) != len(set(output_ids)):
            raise ValueError("Completed Compute outputs must be unique")
        return self


class RunnerFail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: str = Field(min_length=1, max_length=20_000)
    usage: ComputeUsage | None = None

    @model_validator(mode="after")
    def normalize(self):
        self.error = self.error.strip()
        if not self.error:
            raise ValueError("Failure reason is required")
        return self


class RunnerCancelled(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="", max_length=2_000)
    usage: ComputeUsage | None = None


async def _project(db_session: DBSession, project_id: UUID) -> Project:
    project = await Project.find_by(
        db_session, [Project.id == project_id, Project.deleted_at.is_(None)]
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _task_context(
    db_session: DBSession,
    current_user: User,
    task_id: UUID,
    *,
    capability: str,
) -> tuple[ResearchTask, Project, Lab, ResearchRun]:
    task = await db_session.get(ResearchTask, task_id)
    if task is None or task.archived_at is not None:
        raise HTTPException(status_code=404, detail="Research Task not found")
    project = await _project(db_session, task.project_id)
    await require_research_capability(
        db_session, user=current_user, project=project, capability=capability
    )
    lab = await db_session.get(Lab, task.lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    run = (
        await db_session.scalars(
            select(ResearchRun)
            .where(ResearchRun.task_id == task.id)
            .order_by(ResearchRun.run_number.desc())
            .limit(1)
        )
    ).first()
    if run is None:
        raise HTTPException(status_code=409, detail="Research Run not found")
    return task, project, lab, run


def _destination(
    *, task: ResearchTask, project: Project, lab: Lab, run: ResearchRun
) -> dict[str, Any]:
    return {
        "lab": {"id": str(lab.id), "uid": lab.uid, "name": lab.name},
        "project": {"id": str(project.id), "uid": project.uid, "name": project.name},
        "task": {"id": str(task.id), "title": task.title},
        "run": {"id": str(run.id), "number": run.run_number},
    }


async def _validated_action_command(
    db_session: DBSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
    params: ComputeActionDraft,
    requesting_user_id: UUID,
):
    if task.status != ResearchTaskStatus.ACTIVE.value:
        raise HTTPException(status_code=409, detail="Research Task must be active")
    if run.status != ResearchRunStatus.RUNNING.value:
        raise HTTPException(
            status_code=409,
            detail="Research Run must be ready before requesting computation",
        )
    try:
        _task_environment, environment, revision = await pinned_compute_environment(
            db_session,
            task=task,
            revision_id=params.compute_environment_revision_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if params.language not in revision.allowed_languages:
        raise HTTPException(
            status_code=422,
            detail="Language is not allowed by this Compute Environment",
        )
    try:
        validate_schema_payload(
            revision.input_schema, params.input_payload, "compute input"
        )
        inputs = await exact_compute_inputs(
            db_session,
            task=task,
            items=[
                (item.data_asset_version_id, item.mount_name)
                for item in params.input_assets
            ],
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        declared_output_bytes = validate_compute_output_budget(
            params.output_files, revision.resource_limits
        )
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error
    if params.output_files:
        await assert_research_file_upload_quota(
            db_session,
            requesting_user_id,
            declared_output_bytes,
            incoming_count=len(params.output_files),
        )
    authorized_runners = await eligible_runner_count(
        db_session,
        environment_revision_id=revision.id,
        ready_only=False,
    )
    if not authorized_runners:
        raise HTTPException(
            status_code=409,
            detail="No Compute Runner is authorized for this environment revision",
        )
    estimated_cost = compute_estimated_cost(revision)
    if task.budget_limit is not None:
        if estimated_cost is None or not revision.currency:
            raise HTTPException(
                status_code=409,
                detail="A budgeted Task requires a priced Compute Environment",
            )
        try:
            snapshot = await research_budget_snapshot(db_session, task=task)
            project_budget_change(
                task=task,
                snapshot=snapshot,
                kind="reserve",
                amount=estimated_cost,
                currency=revision.currency,
            )
        except ResearchBudgetError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
    title = params.title or f"Run {revision.name} computation"
    command = compute_action_command(
        task=task,
        run=run,
        environment=environment,
        revision=revision,
        language=params.language,
        source_code=params.source_code,
        input_payload=params.input_payload,
        input_versions=inputs,
        output_files=[item.model_dump(mode="json") for item in params.output_files],
        title=title,
        description=params.description,
        idempotency_key=params.idempotency_key,
    )
    ready_runners = await eligible_runner_count(
        db_session,
        environment_revision_id=revision.id,
        ready_only=True,
    )
    return command, environment, revision, inputs, authorized_runners, ready_runners


@router.get("/research-tasks/{task_id}/compute-options")
async def list_compute_options(
    task_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, _project_context, _lab, _run = await _task_context(
        db_session, current_user, task_id, capability="research.read"
    )
    rows = list(
        (
            await db_session.execute(
                select(ResearchComputeEnvironmentRevision)
                .join(
                    ResearchTaskComputeEnvironment,
                    ResearchTaskComputeEnvironment.compute_environment_revision_id
                    == ResearchComputeEnvironmentRevision.id,
                )
                .where(ResearchTaskComputeEnvironment.task_id == task.id)
                .order_by(ResearchTaskComputeEnvironment.position)
            )
        ).scalars()
    )
    items = []
    for revision in rows:
        items.append(
            {
                "compute_environment_revision_id": str(revision.id),
                "name": revision.name,
                "revision": revision.revision,
                "allowed_languages": revision.allowed_languages,
                "input_schema": revision.input_schema,
                "result_schema": revision.result_schema,
                "resource_limits": revision.resource_limits,
                "network_policy": revision.network_policy,
                "estimated_cost": (
                    str(compute_estimated_cost(revision))
                    if compute_estimated_cost(revision) is not None
                    else None
                ),
                "currency": revision.currency,
                "authorized_runner_count": await eligible_runner_count(
                    db_session,
                    environment_revision_id=revision.id,
                    ready_only=False,
                ),
                "ready_runner_count": await eligible_runner_count(
                    db_session,
                    environment_revision_id=revision.id,
                    ready_only=True,
                ),
            }
        )
    return {"items": items}


@router.post("/research-tasks/{task_id}/compute-actions/preview")
async def preview_compute_action(
    task_id: UUID,
    params: ComputeActionDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, project, lab, run = await _task_context(
        db_session, current_user, task_id, capability="research.compute.use"
    )
    (
        command,
        _environment,
        revision,
        inputs,
        authorized,
        ready,
    ) = await _validated_action_command(
        db_session,
        task=task,
        run=run,
        params=params,
        requesting_user_id=current_user.id,
    )
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": _destination(task=task, project=project, lab=lab, run=run),
        "environment": {
            "name": revision.name,
            "revision": revision.revision,
            "image_ref": revision.image_ref,
            "risk": revision.risk,
        },
        "source": {
            "language": params.language,
            "sha256": compute_source_digest(params.source_code),
            "bytes": len(params.source_code.encode("utf-8")),
        },
        "input_asset_count": len(inputs),
        "output_file_count": len(params.output_files),
        "authorized_runner_count": authorized,
        "ready_runner_count": ready,
        "effects": [
            "Create a version-pinned Compute Action and approval request",
            "Reserve the maximum estimated cost after approval when the Task has a budget",
            "Queue execution only for an isolated Runner authorized for this exact revision",
            "Keep source, inputs, result Schema, usage, cost, and events in the Task audit trail",
            "Register only declared and checksum-verified output files as draft DataAssets",
        ],
    }


@router.post("/research-tasks/{task_id}/compute-actions")
async def create_compute_action(
    task_id: UUID,
    params: ComputeActionCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, _project_context, _lab, run = await _task_context(
        db_session, current_user, task_id, capability="research.compute.use"
    )
    (
        command,
        environment,
        revision,
        inputs,
        _authorized,
        _ready,
    ) = await _validated_action_command(
        db_session,
        task=task,
        run=run,
        params=params,
        requesting_user_id=current_user.id,
    )
    digest = canonical_digest(command)
    if digest != params.preview_digest:
        raise HTTPException(status_code=409, detail="Compute Action preview changed")
    existing = await ResearchAction.find_by(
        db_session,
        [
            ResearchAction.run_id == run.id,
            ResearchAction.idempotency_key == params.idempotency_key,
        ],
    )
    if existing is not None:
        if (
            existing.kind != ResearchActionKind.COMPUTE_JOB.value
            or existing.preview_digest != digest
        ):
            raise HTTPException(
                status_code=409, detail="Action idempotency key is already in use"
            )
        existing_job = await ResearchComputeJob.find_by(
            db_session, [ResearchComputeJob.action_id == existing.id]
        )
        if existing_job is None:
            raise HTTPException(status_code=409, detail="Compute Action is incomplete")
        return {**existing.as_dict(), "compute_job": compute_job_snapshot(existing_job)}

    await create_plan_version(
        db_session,
        task=task,
        run=run,
        kind="manual",
        plan={"action": command, "previous_plan_version": run.plan_version},
        summary=command["title"],
    )
    sequence = (
        await db_session.scalar(
            select(func.max(ResearchAction.sequence)).where(
                ResearchAction.run_id == run.id
            )
        )
        or 0
    ) + 1
    action = ResearchAction(
        run_id=run.id,
        sequence=sequence,
        plan_version=run.plan_version,
        kind=ResearchActionKind.COMPUTE_JOB.value,
        status=ResearchActionStatus.PROPOSED.value,
        title=command["title"],
        description=command["description"],
        executor_type="compute_runner",
        input_data={
            "compute_environment_revision_id": str(revision.id),
            "language": params.language,
            "source_sha256": command["source_sha256"],
            "input_payload": params.input_payload,
            "input_assets": command["input_assets"],
            "output_files": command["output_files"],
            "source": "manual",
            "resume_run": True,
        },
        requirements={
            "image_ref": revision.image_ref,
            "resource_limits": revision.resource_limits,
            "network_policy": revision.network_policy,
            "allowed_egress_hosts": revision.allowed_egress_hosts,
            "input_schema": revision.input_schema,
            "result_schema": revision.result_schema,
            "estimated_cost": command["estimated_cost"],
            "currency": revision.currency,
        },
        policy_decision="ask",
        preview_digest=digest,
        idempotency_key=params.idempotency_key,
    )
    db_session.add(action)
    await db_session.flush()
    job = ResearchComputeJob(
        action_id=action.id,
        compute_environment_id=environment.id,
        compute_environment_revision_id=revision.id,
        compute_environment_revision=revision.revision,
        language=params.language,
        source_code=params.source_code,
        source_sha256=command["source_sha256"],
        input_payload=params.input_payload,
        input_schema=revision.input_schema,
        result_schema=revision.result_schema,
        environment_snapshot=(
            await pinned_compute_environment(
                db_session, task=task, revision_id=revision.id
            )
        )[0].snapshot,
        resource_limits=revision.resource_limits,
        timeout_seconds=int(revision.resource_limits["timeout_seconds"]),
        estimated_cost=compute_estimated_cost(revision),
        currency=revision.currency,
        created_by_user_id=current_user.id,
        output_manifest=[],
    )
    db_session.add(job)
    await db_session.flush()
    for position, (asset, version, mount_name) in enumerate(inputs, start=1):
        db_session.add(
            ResearchComputeJobInput(
                compute_job_id=job.id,
                data_asset_id=asset.id,
                data_asset_version_id=version.id,
                position=position,
                mount_name=mount_name,
            )
        )
    output_rows = []
    for position, output in enumerate(params.output_files, start=1):
        row = ResearchComputeJobOutput(
            compute_job_id=job.id,
            position=position,
            mount_name=output.mount_name,
            asset_name=output.asset_name,
            description=output.description,
            kind=output.kind,
            media_type=output.media_type,
            max_bytes=output.max_bytes,
            required=output.required,
            data_schema=output.data_schema,
            version_metadata=output.metadata,
        )
        db_session.add(row)
        output_rows.append(row)
    await db_session.flush()
    job.output_manifest = [compute_output_snapshot(row) for row in output_rows]
    approval = await request_action_approval(
        db_session,
        task=task,
        run=run,
        action=action,
        reason=(
            "Approve isolated compute execution, exact inputs, resource limits, "
            "network policy, and maximum estimated cost."
        ),
    )
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="compute_job.requested",
        actor_user_id=current_user.id,
        payload={
            "compute_job_id": str(job.id),
            "approval_id": str(approval.id),
            "environment_revision_id": str(revision.id),
            "source_sha256": job.source_sha256,
        },
        idempotency_key=f"compute-job:{job.id}:requested",
    )
    await db_session.commit()
    return {
        **action.as_dict(),
        "compute_job": compute_job_snapshot(job),
        "approval_id": str(approval.id),
    }


async def _user_job_context(
    db_session: DBSession,
    current_user: User,
    job_id: UUID,
    *,
    lock: bool,
) -> tuple[ResearchComputeJob, ResearchAction, ResearchRun, ResearchTask, Project, Lab]:
    statement = select(ResearchComputeJob).where(ResearchComputeJob.id == job_id)
    if lock:
        statement = statement.with_for_update()
    job = (await db_session.scalars(statement)).first()
    action = await db_session.get(ResearchAction, job.action_id) if job else None
    run = await db_session.get(ResearchRun, action.run_id) if action else None
    task = await db_session.get(ResearchTask, run.task_id) if run else None
    if job is None or action is None or run is None or task is None:
        raise HTTPException(status_code=404, detail="Compute Job not found")
    project = await _project(db_session, task.project_id)
    await require_research_capability(
        db_session,
        user=current_user,
        project=project,
        capability="research.compute.use",
    )
    lab = await db_session.get(Lab, task.lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    return job, action, run, task, project, lab


@router.get("/research-compute-jobs")
async def list_compute_jobs(
    task_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    _task, _project_context, _lab, run = await _task_context(
        db_session, current_user, task_id, capability="research.read"
    )
    rows = list(
        (
            await db_session.execute(
                select(ResearchComputeJob, ResearchAction)
                .join(ResearchAction, ResearchAction.id == ResearchComputeJob.action_id)
                .where(ResearchAction.run_id == run.id)
                .order_by(ResearchComputeJob.created_at.desc())
            )
        ).all()
    )
    return {
        "items": [
            {**action.as_dict(), "compute_job": compute_job_snapshot(job)}
            for job, action in rows
        ]
    }


def _cancel_command(
    job: ResearchComputeJob, params: ComputeCancelDraft
) -> dict[str, Any]:
    return {
        "operation": "cancel_research_compute_job",
        "compute_job_id": str(job.id),
        "expected_revision": params.expected_revision,
        "reason": params.reason,
    }


@router.post("/research-compute-jobs/{job_id}/cancel/preview")
async def preview_cancel_compute_job(
    job_id: UUID,
    params: ComputeCancelDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    job, action, run, task, project, lab = await _user_job_context(
        db_session, current_user, job_id, lock=False
    )
    if job.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Compute Job changed")
    if job.status in FINAL_COMPUTE_JOB_STATUSES:
        raise HTTPException(status_code=409, detail="Compute Job is already final")
    command = _cancel_command(job, params)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": _destination(task=task, project=project, lab=lab, run=run),
        "action": {"id": str(action.id), "title": action.title},
        "effects": [
            "Pause the Research Task for inspection",
            (
                "Cancel the job before delivery and release its reserved budget"
                if job.status
                in {
                    ResearchComputeJobStatus.AWAITING_APPROVAL.value,
                    ResearchComputeJobStatus.QUEUED.value,
                }
                else "Request cancellation from the active Runner"
            ),
            "Keep the source, inputs, usage, and cancellation event for audit",
        ],
    }


@router.post("/research-compute-jobs/{job_id}/cancel")
async def cancel_compute_job(
    job_id: UUID,
    params: ComputeCancel,
    current_user: CurrentUser,
    db_session: DBSession,
):
    job, action, run, task, _project_context, _lab = await _user_job_context(
        db_session, current_user, job_id, lock=True
    )
    if job.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Compute Job changed")
    if job.status in FINAL_COMPUTE_JOB_STATUSES:
        raise HTTPException(status_code=409, detail="Compute Job is already final")
    command = _cancel_command(job, params)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(
            status_code=409, detail="Compute cancellation preview changed"
        )
    now = utcnow()
    previous_status = job.status
    job.cancel_reason = params.reason
    job.cancel_requested_at = now
    job.revision += 1
    cancelled_before_delivery = previous_status in {
        ResearchComputeJobStatus.AWAITING_APPROVAL.value,
        ResearchComputeJobStatus.QUEUED.value,
    }
    if cancelled_before_delivery:
        if previous_status == ResearchComputeJobStatus.QUEUED.value:
            try:
                await release_compute_budget(
                    db_session,
                    task=task,
                    run=run,
                    action=action,
                    job=job,
                    suffix="cancel-release",
                    actor_user_id=current_user.id,
                )
            except ResearchBudgetError as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
        job.status = ResearchComputeJobStatus.CANCELLED.value
        job.completed_at = now
        action.status = ResearchActionStatus.CANCELLED.value
        action.completed_at = now
        pending_approval = await ResearchApproval.find_by(
            db_session,
            [
                ResearchApproval.action_id == action.id,
                ResearchApproval.status == ResearchApprovalStatus.PENDING.value,
            ],
        )
        if pending_approval is not None:
            pending_approval.status = ResearchApprovalStatus.REVOKED.value
            pending_approval.decision_reason = params.reason
            pending_approval.decided_by_user_id = current_user.id
            pending_approval.decided_at = now
            pending_approval.revision += 1
    else:
        job.status = ResearchComputeJobStatus.CANCEL_REQUESTED.value
        action.status = ResearchActionStatus.WAITING.value
    action.error = (
        f"Cancelled: {params.reason}"
        if cancelled_before_delivery
        else f"Cancellation requested: {params.reason}"
    )
    action.revision += 1
    run.status = ResearchRunStatus.PAUSED.value
    run.last_error = "Compute cancellation requested; inspect outputs before resuming."
    task.status = ResearchTaskStatus.PAUSED.value
    task.revision += 1
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind=(
            "compute_job.cancelled"
            if cancelled_before_delivery
            else "compute_job.cancel_requested"
        ),
        actor_user_id=current_user.id,
        payload={
            "compute_job_id": str(job.id),
            "previous_status": previous_status,
            "reason": params.reason,
        },
        idempotency_key=(
            f"compute-job:{job.id}:"
            f"{'cancelled' if cancelled_before_delivery else 'cancel-requested'}:"
            f"{job.revision}"
        ),
    )
    await db_session.commit()
    return {**action.as_dict(), "compute_job": compute_job_snapshot(job)}


async def _runner_job_context(
    db_session: DBSession,
    *,
    runner: ResearchComputeRunner,
    job_id: UUID,
    lease_token: str,
) -> tuple[ResearchComputeJob, ResearchAction, ResearchRun, ResearchTask]:
    job = (
        await db_session.scalars(
            select(ResearchComputeJob)
            .where(
                ResearchComputeJob.id == job_id,
                ResearchComputeJob.runner_id == runner.id,
            )
            .with_for_update()
        )
    ).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Compute Job not found")
    digest = compute_lease_token_digest(lease_token)
    if job.lease_token_digest is None or not hmac.compare_digest(
        job.lease_token_digest, digest
    ):
        raise HTTPException(status_code=401, detail="Invalid Compute Job lease")
    action = await db_session.get(ResearchAction, job.action_id)
    run = await db_session.get(ResearchRun, action.run_id) if action else None
    task = await db_session.get(ResearchTask, run.task_id) if run else None
    if action is None or run is None or task is None:
        raise HTTPException(status_code=409, detail="Compute Job context is missing")
    return job, action, run, task


def _ensure_live_lease(job: ResearchComputeJob) -> None:
    if job.lease_expires_at is None or job.lease_expires_at <= utcnow():
        raise HTTPException(status_code=409, detail="Compute Job lease expired")


def _validate_usage(job: ResearchComputeJob, usage: ComputeUsage) -> None:
    limits = job.resource_limits or {}
    if usage.wall_seconds > job.timeout_seconds:
        raise HTTPException(
            status_code=422, detail="Compute wall time exceeds its limit"
        )
    if usage.max_memory_mb > int(limits.get("memory_mb") or 0):
        raise HTTPException(
            status_code=422, detail="Compute memory usage exceeds its limit"
        )
    if usage.output_bytes > int(limits.get("max_output_bytes") or 0):
        raise HTTPException(status_code=422, detail="Compute output exceeds its limit")


async def _pause_compute_failure(
    *,
    job: ResearchComputeJob,
    action: ResearchAction,
    run: ResearchRun,
    task: ResearchTask,
    error: str,
) -> None:
    now = utcnow()
    job.status = ResearchComputeJobStatus.FAILED.value
    job.error = error
    job.completed_at = now
    job.lease_expires_at = None
    job.revision += 1
    if task.status != ResearchTaskStatus.CANCELLED.value:
        action.status = ResearchActionStatus.FAILED.value
        action.error = error
        action.completed_at = now
        action.revision += 1
        run.status = ResearchRunStatus.PAUSED.value
        run.last_error = error
        task.status = ResearchTaskStatus.PAUSED.value
        task.revision += 1


async def _input_rows(db_session: DBSession, job_id: UUID):
    return list(
        (
            await db_session.execute(
                select(
                    ResearchComputeJobInput,
                    DataAsset,
                    DataAssetVersion,
                    ResearchFile,
                    ResearchFileBlob,
                )
                .join(
                    DataAsset,
                    DataAsset.id == ResearchComputeJobInput.data_asset_id,
                )
                .join(
                    DataAssetVersion,
                    DataAssetVersion.id
                    == ResearchComputeJobInput.data_asset_version_id,
                )
                .join(
                    ResearchFile,
                    ResearchFile.id == DataAssetVersion.research_file_id,
                )
                .join(ResearchFileBlob, ResearchFileBlob.id == ResearchFile.blob_id)
                .where(ResearchComputeJobInput.compute_job_id == job_id)
                .order_by(ResearchComputeJobInput.position)
            )
        ).all()
    )


async def _output_rows(db_session: DBSession, job_id: UUID):
    return list(
        (
            await db_session.execute(
                select(ResearchComputeJobOutput, ResearchFileBlob)
                .outerjoin(
                    ResearchFileBlob,
                    ResearchFileBlob.id == ResearchComputeJobOutput.blob_id,
                )
                .where(ResearchComputeJobOutput.compute_job_id == job_id)
                .order_by(ResearchComputeJobOutput.position)
            )
        ).all()
    )


async def _refresh_output_manifest(
    db_session: DBSession, job: ResearchComputeJob
) -> list[dict[str, Any]]:
    manifest = [
        compute_output_snapshot(output, blob)
        for output, blob in await _output_rows(db_session, job.id)
    ]
    job.output_manifest = manifest
    return manifest


@runtime_router.post("/jobs/lease")
async def lease_compute_job(
    runner_token: RunnerToken,
    db_session: DBSession,
):
    runner = await authenticate_compute_runner(db_session, runner_token)
    if not runner.enabled or not runner_report_is_execution_ready(runner):
        raise HTTPException(
            status_code=403, detail="Compute Runner is not execution-ready"
        )
    report = runner.last_report or {}
    if int(report.get("available_slots") or 0) <= 0:
        await db_session.commit()
        return {"job": None, "retry_after_seconds": 10}
    now = utcnow()
    active_jobs = list(
        (
            await db_session.scalars(
                select(ResearchComputeJob)
                .where(
                    ResearchComputeJob.runner_id == runner.id,
                    ResearchComputeJob.status.in_(ACTIVE_COMPUTE_JOB_STATUSES),
                )
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    for active in active_jobs:
        if (
            active.status == ResearchComputeJobStatus.LEASED.value
            and active.started_at is None
            and active.lease_expires_at is not None
            and active.lease_expires_at <= now
        ):
            active.status = ResearchComputeJobStatus.QUEUED.value
            active.runner_id = None
            active.lease_token_digest = None
            active.lease_expires_at = None
            active.revision += 1
        elif (
            active.status == ResearchComputeJobStatus.RUNNING.value
            and active.lease_expires_at is not None
            and active.lease_expires_at <= now
        ):
            action = await db_session.get(ResearchAction, active.action_id)
            run = await db_session.get(ResearchRun, action.run_id) if action else None
            task = await db_session.get(ResearchTask, run.task_id) if run else None
            if action is not None and run is not None and task is not None:
                await _pause_compute_failure(
                    job=active,
                    action=action,
                    run=run,
                    task=task,
                    error="Compute Runner heartbeat lease expired during execution",
                )
                await emit_research_event(
                    db_session,
                    task_id=task.id,
                    run_id=run.id,
                    action_id=action.id,
                    kind="compute_job.failed",
                    actor_user_id=None,
                    payload={
                        "compute_job_id": str(active.id),
                        "error": active.error,
                    },
                    idempotency_key=f"compute-job:{active.id}:lease-expired",
                )
        elif (
            active.status == ResearchComputeJobStatus.CANCEL_REQUESTED.value
            and active.lease_expires_at is not None
            and active.lease_expires_at <= now
        ):
            action = await db_session.get(ResearchAction, active.action_id)
            run = await db_session.get(ResearchRun, action.run_id) if action else None
            task = await db_session.get(ResearchTask, run.task_id) if run else None
            if action is not None and run is not None and task is not None:
                await _pause_compute_failure(
                    job=active,
                    action=action,
                    run=run,
                    task=task,
                    error=(
                        "Compute Runner did not acknowledge cancellation before "
                        "its lease expired; execution outcome is uncertain"
                    ),
                )
                await emit_research_event(
                    db_session,
                    task_id=task.id,
                    run_id=run.id,
                    action_id=action.id,
                    kind="compute_job.failed",
                    actor_user_id=None,
                    payload={
                        "compute_job_id": str(active.id),
                        "error": active.error,
                    },
                    idempotency_key=f"compute-job:{active.id}:cancel-timeout",
                )
    effective_capacity = min(
        runner.max_concurrent_jobs,
        int(report.get("active_jobs") or 0) + int(report.get("available_slots") or 0),
    )
    if await runner_active_job_count(db_session, runner.id) >= effective_capacity:
        await db_session.commit()
        return {"job": None, "retry_after_seconds": 10}

    bound_revisions = select(
        ResearchComputeRunnerEnvironment.compute_environment_revision_id
    ).where(
        ResearchComputeRunnerEnvironment.runner_id == runner.id,
        ResearchComputeRunnerEnvironment.archived_at.is_(None),
    )
    job = (
        await db_session.scalars(
            select(ResearchComputeJob)
            .join(ResearchAction, ResearchAction.id == ResearchComputeJob.action_id)
            .where(
                ResearchComputeJob.status == ResearchComputeJobStatus.QUEUED.value,
                ResearchComputeJob.compute_environment_revision_id.in_(bound_revisions),
                ResearchAction.status == ResearchActionStatus.QUEUED.value,
            )
            .order_by(ResearchComputeJob.created_at, ResearchComputeJob.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
    ).first()
    if job is None:
        runner.last_seen_at = now
        await db_session.commit()
        return {"job": None, "retry_after_seconds": 15}
    action = await db_session.get(ResearchAction, job.action_id)
    run = await db_session.get(ResearchRun, action.run_id) if action else None
    task = await db_session.get(ResearchTask, run.task_id) if run else None
    revision = await db_session.get(
        ResearchComputeEnvironmentRevision, job.compute_environment_revision_id
    )
    invalid_reason = None
    if action is None or run is None or task is None:
        invalid_reason = "Compute Job context is missing"
    elif (
        task.status != ResearchTaskStatus.ACTIVE.value
        or run.status != ResearchRunStatus.WAITING_FOR_COMPUTE.value
    ):
        await db_session.commit()
        return {"job": None, "retry_after_seconds": 15}
    elif runner.lab_id != task.lab_id:
        invalid_reason = "Compute Runner and Task belong to different Labs"
    elif (
        revision is None
        or not revision.enabled
        or revision.runner_protocol_version != runner.runner_protocol_version
        or revision.revision != job.compute_environment_revision
    ):
        invalid_reason = "Pinned Compute Environment is unavailable"
    elif compute_source_digest(job.source_code) != job.source_sha256:
        invalid_reason = "Compute source digest no longer matches"
    else:
        try:
            await validate_pinned_compute_inputs(db_session, task=task, job_id=job.id)
        except ValueError as error:
            invalid_reason = str(error)
    if invalid_reason is not None:
        if action is not None and run is not None and task is not None:
            try:
                await release_compute_budget(
                    db_session,
                    task=task,
                    run=run,
                    action=action,
                    job=job,
                    suffix="delivery-failure-release",
                    actor_user_id=None,
                )
            except ResearchBudgetError:
                pass
            await _pause_compute_failure(
                job=job,
                action=action,
                run=run,
                task=task,
                error=invalid_reason,
            )
            await emit_research_event(
                db_session,
                task_id=task.id,
                run_id=run.id,
                action_id=action.id,
                kind="compute_job.failed",
                actor_user_id=None,
                payload={"compute_job_id": str(job.id), "error": invalid_reason},
                idempotency_key=f"compute-job:{job.id}:failed:{job.revision}",
            )
        await db_session.commit()
        return {"job": None, "retry_after_seconds": 15}

    input_rows = await _input_rows(db_session, job.id)
    output_rows = await _output_rows(db_session, job.id)
    expected_inputs = await db_session.scalar(
        select(func.count())
        .select_from(ResearchComputeJobInput)
        .where(ResearchComputeJobInput.compute_job_id == job.id)
    )
    if len(input_rows) != int(expected_inputs or 0):
        try:
            await release_compute_budget(
                db_session,
                task=task,
                run=run,
                action=action,
                job=job,
                suffix="missing-input-release",
                actor_user_id=None,
            )
        except ResearchBudgetError:
            pass
        await _pause_compute_failure(
            job=job,
            action=action,
            run=run,
            task=task,
            error="A Compute input blob is no longer available",
        )
        await emit_research_event(
            db_session,
            task_id=task.id,
            run_id=run.id,
            action_id=action.id,
            kind="compute_job.failed",
            actor_user_id=None,
            payload={"compute_job_id": str(job.id), "error": job.error},
            idempotency_key=f"compute-job:{job.id}:missing-input-blob",
        )
        await db_session.commit()
        return {"job": None, "retry_after_seconds": 15}
    lease_token = generate_compute_lease_token()
    expires_at = now + timedelta(seconds=LEASE_SECONDS)
    job.status = ResearchComputeJobStatus.LEASED.value
    job.runner_id = runner.id
    job.lease_token_digest = compute_lease_token_digest(lease_token)
    job.lease_expires_at = expires_at
    job.leased_at = now
    job.heartbeat_at = now
    job.attempt_count += 1
    job.revision += 1
    runner.last_seen_at = now
    envelope = {
        "schema": "airalogy.compute-job.v1",
        "job_id": str(job.id),
        "action_id": str(action.id),
        "task_id": str(task.id),
        "run_id": str(run.id),
        "issued_at": now.isoformat(),
        "lease_expires_at": expires_at.isoformat(),
        "environment": {
            "id": str(job.compute_environment_id),
            "revision_id": str(job.compute_environment_revision_id),
            "revision": job.compute_environment_revision,
            "image_ref": revision.image_ref,
            "runtime_version": revision.runtime_version,
            "language": job.language,
            "resource_limits": job.resource_limits,
            "network_policy": revision.network_policy,
            "allowed_egress_hosts": revision.allowed_egress_hosts,
        },
        "source": {
            "code": job.source_code,
            "sha256": job.source_sha256,
        },
        "input_payload": job.input_payload,
        "inputs": [
            {
                "id": str(input_row.id),
                "mount_name": input_row.mount_name,
                "data_asset_id": str(asset.id),
                "data_asset_version_id": str(version.id),
                "data_asset_version": version.version,
                "filename": research_file.filename,
                "media_type": blob.content_type,
                "byte_size": blob.size_bytes,
                "checksum_sha256": blob.checksum_sha256,
                "download_path": (
                    f"/compute-runner/v1/jobs/{job.id}/inputs/{input_row.id}"
                ),
            }
            for input_row, asset, version, research_file, blob in input_rows
        ],
        "outputs": [
            {
                "id": str(output.id),
                "mount_name": output.mount_name,
                "asset_name": output.asset_name,
                "description": output.description,
                "kind": output.kind,
                "media_type": output.media_type,
                "max_bytes": output.max_bytes,
                "required": output.required,
                "data_schema": output.data_schema,
                "metadata": output.version_metadata,
                "upload_path": (
                    f"/compute-runner/v1/jobs/{job.id}/outputs/{output.id}"
                ),
            }
            for output, _blob in output_rows
        ],
        "result_schema": job.result_schema,
    }
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="compute_job.leased",
        actor_user_id=None,
        payload={
            "compute_job_id": str(job.id),
            "runner_id": str(runner.id),
            "lease_expires_at": expires_at.isoformat(),
            "attempt": job.attempt_count,
        },
        idempotency_key=f"compute-job:{job.id}:leased:{job.attempt_count}",
    )
    await db_session.commit()
    return {
        "job": envelope,
        "signature": sign_compute_envelope(envelope, runner.token_digest),
        "lease_token": lease_token,
    }


@runtime_router.get("/jobs/{job_id}/inputs/{input_id}")
async def download_compute_input(
    job_id: UUID,
    input_id: UUID,
    runner_token: RunnerToken,
    lease_token: LeaseToken,
    db_session: DBSession,
):
    runner = await authenticate_compute_runner(db_session, runner_token)
    job, action, run, task = await _runner_job_context(
        db_session,
        runner=runner,
        job_id=job_id,
        lease_token=lease_token,
    )
    if job.status not in {
        ResearchComputeJobStatus.LEASED.value,
        ResearchComputeJobStatus.RUNNING.value,
    }:
        raise HTTPException(status_code=409, detail="Compute Job is not active")
    _ensure_live_lease(job)
    row = (
        await db_session.execute(
            select(ResearchComputeJobInput, ResearchFile, ResearchFileBlob)
            .join(
                DataAssetVersion,
                DataAssetVersion.id == ResearchComputeJobInput.data_asset_version_id,
            )
            .join(ResearchFile, ResearchFile.id == DataAssetVersion.research_file_id)
            .join(ResearchFileBlob, ResearchFileBlob.id == ResearchFile.blob_id)
            .where(
                ResearchComputeJobInput.id == input_id,
                ResearchComputeJobInput.compute_job_id == job.id,
            )
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Compute input not found")
    input_row, _research_file, blob = row
    now = utcnow()
    runner.last_seen_at = now
    job.heartbeat_at = now
    job.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="compute_job.input_downloaded",
        actor_user_id=None,
        payload={
            "compute_job_id": str(job.id),
            "input_id": str(input_row.id),
            "data_asset_id": str(input_row.data_asset_id),
            "data_asset_version_id": str(input_row.data_asset_version_id),
            "runner_id": str(runner.id),
        },
        idempotency_key=(
            f"compute-job:{job.id}:input:{input_row.id}:attempt:{job.attempt_count}"
        ),
    )
    safe_name = input_row.mount_name.replace('"', "_")
    await db_session.commit()
    return StreamingResponse(
        get_file_with_stream(blob.storage_object_key, backend=blob.storage_backend),
        media_type=blob.content_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{safe_name}"; '
                f"filename*=UTF-8''{quote(input_row.mount_name)}"
            ),
            "X-Content-SHA256": blob.checksum_sha256,
        },
    )


@runtime_router.post("/jobs/{job_id}/start")
async def start_compute_job(
    job_id: UUID,
    runner_token: RunnerToken,
    lease_token: LeaseToken,
    db_session: DBSession,
):
    runner = await authenticate_compute_runner(db_session, runner_token)
    job, action, run, task = await _runner_job_context(
        db_session, runner=runner, job_id=job_id, lease_token=lease_token
    )
    if job.status != ResearchComputeJobStatus.LEASED.value:
        raise HTTPException(status_code=409, detail="Compute Job cannot be started")
    if (
        task.status != ResearchTaskStatus.ACTIVE.value
        or run.status != ResearchRunStatus.WAITING_FOR_COMPUTE.value
        or action.status != ResearchActionStatus.QUEUED.value
    ):
        raise HTTPException(status_code=409, detail="Research Run is not ready")
    _ensure_live_lease(job)
    now = utcnow()
    job.status = ResearchComputeJobStatus.RUNNING.value
    job.started_at = now
    job.heartbeat_at = now
    job.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    job.revision += 1
    action.status = ResearchActionStatus.RUNNING.value
    action.started_at = now
    action.revision += 1
    runner.last_seen_at = now
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="compute_job.started",
        actor_user_id=None,
        payload={"compute_job_id": str(job.id), "runner_id": str(runner.id)},
        idempotency_key=f"compute-job:{job.id}:started",
    )
    await db_session.commit()
    return {"status": job.status, "lease_expires_at": job.lease_expires_at}


@runtime_router.post("/jobs/{job_id}/heartbeat")
async def heartbeat_compute_job(
    job_id: UUID,
    runner_token: RunnerToken,
    lease_token: LeaseToken,
    db_session: DBSession,
):
    runner = await authenticate_compute_runner(db_session, runner_token)
    job, action, run, task = await _runner_job_context(
        db_session, runner=runner, job_id=job_id, lease_token=lease_token
    )
    if job.status == ResearchComputeJobStatus.CANCEL_REQUESTED.value:
        runner.last_seen_at = utcnow()
        await db_session.commit()
        return {
            "status": job.status,
            "cancel_requested": True,
            "reason": job.cancel_reason,
        }
    if job.status not in {
        ResearchComputeJobStatus.LEASED.value,
        ResearchComputeJobStatus.RUNNING.value,
    }:
        raise HTTPException(status_code=409, detail="Compute Job is not active")
    _ensure_live_lease(job)
    now = utcnow()
    timed_out = bool(
        job.started_at
        and now >= job.started_at + timedelta(seconds=job.timeout_seconds)
    )
    if timed_out:
        job.status = ResearchComputeJobStatus.CANCEL_REQUESTED.value
        job.cancel_reason = "Compute Job timeout reached"
        job.cancel_requested_at = now
        job.revision += 1
        action.status = ResearchActionStatus.WAITING.value
        action.error = job.cancel_reason
        action.revision += 1
        run.status = ResearchRunStatus.PAUSED.value
        run.last_error = job.cancel_reason
        task.status = ResearchTaskStatus.PAUSED.value
        task.revision += 1
        await emit_research_event(
            db_session,
            task_id=task.id,
            run_id=run.id,
            action_id=action.id,
            kind="compute_job.cancel_requested",
            actor_user_id=None,
            payload={"compute_job_id": str(job.id), "reason": job.cancel_reason},
            idempotency_key=f"compute-job:{job.id}:timeout",
        )
        await db_session.commit()
        return {
            "status": job.status,
            "cancel_requested": True,
            "reason": job.cancel_reason,
        }
    job.heartbeat_at = now
    job.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    runner.last_seen_at = now
    await db_session.commit()
    return {
        "status": job.status,
        "cancel_requested": False,
        "lease_expires_at": job.lease_expires_at,
    }


@runtime_router.put("/jobs/{job_id}/outputs/{output_id}")
async def upload_compute_output(
    job_id: UUID,
    output_id: UUID,
    request: Request,
    runner_token: RunnerToken,
    lease_token: LeaseToken,
    content_length: Annotated[int, Header(alias="Content-Length", ge=0)],
    checksum_sha256: Annotated[
        str, Header(alias="X-Airalogy-Content-SHA256", min_length=64, max_length=64)
    ],
    content_type: Annotated[
        str, Header(alias="Content-Type", min_length=3, max_length=255)
    ],
    db_session: DBSession,
):
    checksum_sha256 = checksum_sha256.strip().lower()
    content_type = content_type.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", checksum_sha256):
        raise HTTPException(
            status_code=422, detail="Compute output checksum is invalid"
        )
    runner = await authenticate_compute_runner(db_session, runner_token)
    job, _action, _run, _task = await _runner_job_context(
        db_session, runner=runner, job_id=job_id, lease_token=lease_token
    )
    output = (
        await db_session.scalars(
            select(ResearchComputeJobOutput)
            .where(
                ResearchComputeJobOutput.id == output_id,
                ResearchComputeJobOutput.compute_job_id == job.id,
            )
            .with_for_update()
        )
    ).first()
    if output is None:
        raise HTTPException(status_code=404, detail="Compute output is not declared")
    if output.blob_id is not None:
        blob = await db_session.get(ResearchFileBlob, output.blob_id)
        if (
            blob is None
            or blob.checksum_sha256 != checksum_sha256
            or blob.size_bytes != content_length
            or output.media_type != content_type
        ):
            raise HTTPException(
                status_code=409,
                detail="Compute output was already uploaded with different content",
            )
        await db_session.commit()
        return {
            "status": "uploaded",
            "output_id": str(output.id),
            "checksum_sha256": blob.checksum_sha256,
            "byte_size": blob.size_bytes,
        }
    if job.status != ResearchComputeJobStatus.RUNNING.value:
        raise HTTPException(status_code=409, detail="Compute Job is not running")
    _ensure_live_lease(job)
    if content_length > output.max_bytes:
        raise HTTPException(
            status_code=413, detail="Compute output exceeds its declared limit"
        )
    if content_type != output.media_type:
        raise HTTPException(status_code=415, detail="Compute output media type changed")
    await assert_research_file_upload_quota(
        db_session,
        job.created_by_user_id,
        content_length,
    )
    upload_window = min(
        86_400,
        max(
            LEASE_SECONDS,
            math.ceil(content_length / OUTPUT_UPLOAD_MIN_BYTES_PER_SECOND) + 120,
        ),
    )
    now = utcnow()
    job.lease_expires_at = now + timedelta(seconds=upload_window)
    job.heartbeat_at = now
    runner.last_seen_at = now
    await db_session.commit()

    digest = hashlib.sha256()
    received = 0
    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b") as staged:
        async for chunk in request.stream():
            if not chunk:
                continue
            received += len(chunk)
            if received > content_length or received > output.max_bytes:
                raise HTTPException(
                    status_code=413, detail="Compute output exceeded its declared size"
                )
            digest.update(chunk)
            staged.write(chunk)
        if received != content_length:
            raise HTTPException(
                status_code=422,
                detail="Compute output byte count changed during upload",
            )
        if not hmac.compare_digest(digest.hexdigest(), checksum_sha256):
            raise HTTPException(
                status_code=422, detail="Compute output checksum does not match"
            )

        existing_blob = await db_session.scalar(
            select(ResearchFileBlob).where(
                ResearchFileBlob.checksum_sha256 == checksum_sha256
            )
        )
        object_key = f"knowledge/blobs/{checksum_sha256[:2]}/{checksum_sha256}"
        if existing_blob is None:
            staged.seek(0)
            await upload_file(
                object_key,
                staged,
                content_type=content_type,
                length=content_length,
            )

    db_session.expire_all()
    runner = await authenticate_compute_runner(db_session, runner_token)
    job, action, run, task = await _runner_job_context(
        db_session, runner=runner, job_id=job_id, lease_token=lease_token
    )
    if job.status != ResearchComputeJobStatus.RUNNING.value:
        raise HTTPException(status_code=409, detail="Compute Job is not running")
    _ensure_live_lease(job)
    output = (
        await db_session.scalars(
            select(ResearchComputeJobOutput)
            .where(
                ResearchComputeJobOutput.id == output_id,
                ResearchComputeJobOutput.compute_job_id == job.id,
            )
            .with_for_update()
        )
    ).first()
    if output is None:
        raise HTTPException(status_code=404, detail="Compute output is not declared")
    if output.blob_id is None:
        inserted_id = await db_session.scalar(
            postgresql_insert(ResearchFileBlob)
            .values(
                checksum_sha256=checksum_sha256,
                content_type=content_type,
                size_bytes=content_length,
                storage_backend=default_storage_backend(),
                storage_namespace=default_storage_namespace(),
                storage_object_key=object_key,
                extracted_text="",
            )
            .on_conflict_do_nothing(index_elements=["checksum_sha256"])
            .returning(ResearchFileBlob.id)
        )
        blob = (
            await db_session.get(ResearchFileBlob, inserted_id)
            if inserted_id is not None
            else await db_session.scalar(
                select(ResearchFileBlob).where(
                    ResearchFileBlob.checksum_sha256 == checksum_sha256
                )
            )
        )
        if (
            blob is None
            or blob.size_bytes != content_length
            or blob.content_type != content_type
        ):
            raise HTTPException(
                status_code=409, detail="Stored Compute output metadata conflicts"
            )
        output.blob_id = blob.id
        output.uploaded_at = utcnow()
        job.revision += 1
    else:
        blob = await db_session.get(ResearchFileBlob, output.blob_id)
        if (
            blob is None
            or blob.checksum_sha256 != checksum_sha256
            or blob.size_bytes != content_length
        ):
            raise HTTPException(
                status_code=409,
                detail="Compute output was concurrently uploaded with different content",
            )
    await _refresh_output_manifest(db_session, job)
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="compute_output.uploaded",
        actor_user_id=None,
        payload={
            "compute_job_id": str(job.id),
            "output_id": str(output.id),
            "mount_name": output.mount_name,
            "checksum_sha256": blob.checksum_sha256,
            "byte_size": blob.size_bytes,
        },
        idempotency_key=f"compute-output:{output.id}:uploaded:{blob.checksum_sha256}",
    )
    await db_session.commit()
    return {
        "status": "uploaded",
        "output_id": str(output.id),
        "checksum_sha256": blob.checksum_sha256,
        "byte_size": blob.size_bytes,
        "lease_expires_at": job.lease_expires_at,
    }


def _completed_output_contract(
    outputs: list[RunnerCompletedOutput],
) -> list[dict[str, Any]]:
    return sorted(
        [
            {
                "output_id": str(output.output_id),
                "checksum_sha256": output.checksum_sha256,
                "byte_size": output.byte_size,
            }
            for output in outputs
        ],
        key=lambda item: item["output_id"],
    )


def _manifest_output_contract(manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [
            {
                "output_id": str(item["id"]),
                "checksum_sha256": item["checksum_sha256"],
                "byte_size": item["byte_size"],
            }
            for item in manifest
            if item.get("status") == "registered"
        ],
        key=lambda item: item["output_id"],
    )


def _registered_output_results(
    manifest: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "output_id": item["id"],
            "mount_name": item["mount_name"],
            "asset_name": item["asset_name"],
            "kind": item["kind"],
            "media_type": item["media_type"],
            "checksum_sha256": item["checksum_sha256"],
            "byte_size": item["byte_size"],
            "research_file_id": item["research_file_id"],
            "data_asset_id": item["data_asset_id"],
            "data_asset_version_id": item["data_asset_version_id"],
        }
        for item in manifest
        if item.get("status") == "registered"
    ]


async def _register_compute_output_assets(
    db_session: DBSession,
    *,
    job: ResearchComputeJob,
    task: ResearchTask,
    completed_outputs: list[RunnerCompletedOutput],
) -> list[dict[str, Any]]:
    rows = await _output_rows(db_session, job.id)
    provided = {item.output_id: item for item in completed_outputs}
    declared_ids = {output.id for output, _blob in rows}
    if set(provided) - declared_ids:
        raise HTTPException(status_code=422, detail="Compute output was not declared")
    uploaded: list[tuple[ResearchComputeJobOutput, ResearchFileBlob]] = []
    for output, blob in rows:
        completion = provided.get(output.id)
        if blob is None:
            if output.required:
                raise HTTPException(
                    status_code=422,
                    detail=f"Required Compute output {output.mount_name} was not uploaded",
                )
            if completion is not None:
                raise HTTPException(
                    status_code=422,
                    detail="Compute completion references an output that was not uploaded",
                )
            continue
        if completion is None:
            raise HTTPException(
                status_code=422,
                detail=f"Uploaded Compute output {output.mount_name} is missing from completion",
            )
        if (
            completion.checksum_sha256 != blob.checksum_sha256
            or completion.byte_size != blob.size_bytes
            or blob.content_type != output.media_type
            or blob.size_bytes > output.max_bytes
        ):
            raise HTTPException(
                status_code=422,
                detail=f"Compute output {output.mount_name} changed after upload",
            )
        uploaded.append((output, blob))

    if uploaded:
        await assert_research_file_upload_quota(
            db_session,
            job.created_by_user_id,
            sum(blob.size_bytes for _output, blob in uploaded),
            incoming_count=len(uploaded),
        )
    now = utcnow()
    for output, blob in uploaded:
        if output.data_asset_version_id is not None:
            continue
        research_file = ResearchFile(
            blob_id=blob.id,
            filename=output.mount_name,
            scope_type=OwnerScope.PROJECT.value,
            owner_user_id=None,
            lab_id=task.lab_id,
            project_id=task.project_id,
            visibility=Visibility.PROJECT.value,
            uploaded_by_user_id=job.created_by_user_id,
        )
        db_session.add(research_file)
        await db_session.flush()
        asset = DataAsset(
            lab_id=task.lab_id,
            project_id=task.project_id,
            task_id=task.id,
            name=output.asset_name,
            description=output.description,
            kind=output.kind,
            status=DataAssetStatus.DRAFT.value,
            current_version=1,
            created_by_user_id=job.created_by_user_id,
        )
        db_session.add(asset)
        await db_session.flush()
        version = DataAssetVersion(
            data_asset_id=asset.id,
            version=1,
            research_file_id=research_file.id,
            external_uri="",
            media_type=output.media_type,
            checksum=blob.checksum_sha256,
            byte_size=blob.size_bytes,
            data_schema=output.data_schema,
            version_metadata=output.version_metadata,
            source={
                "type": "research_compute_job_output",
                "compute_job_id": str(job.id),
                "action_id": str(job.action_id),
                "compute_environment_revision_id": str(
                    job.compute_environment_revision_id
                ),
                "source_sha256": job.source_sha256,
                "output_id": str(output.id),
                "mount_name": output.mount_name,
            },
            change_summary="Created from checksum-verified Compute Job output",
            created_by_user_id=job.created_by_user_id,
        )
        db_session.add(version)
        await db_session.flush()
        output.research_file_id = research_file.id
        output.data_asset_id = asset.id
        output.data_asset_version_id = version.id
        output.registered_at = now
    return await _refresh_output_manifest(db_session, job)


@runtime_router.post("/jobs/{job_id}/complete")
async def complete_compute_job(
    job_id: UUID,
    params: RunnerComplete,
    runner_token: RunnerToken,
    lease_token: LeaseToken,
    db_session: DBSession,
):
    runner = await authenticate_compute_runner(db_session, runner_token)
    job, action, run, task = await _runner_job_context(
        db_session, runner=runner, job_id=job_id, lease_token=lease_token
    )
    if job.status == ResearchComputeJobStatus.COMPLETED.value:
        if (
            job.result != params.result
            or job.usage != params.usage.model_dump(mode="json")
            or _manifest_output_contract(job.output_manifest or [])
            != _completed_output_contract(params.outputs)
        ):
            raise HTTPException(
                status_code=409,
                detail="Compute Job was already completed with a different result",
            )
        await db_session.commit()
        return {"status": job.status}
    if job.status != ResearchComputeJobStatus.RUNNING.value:
        raise HTTPException(status_code=409, detail="Compute Job is not running")
    _ensure_live_lease(job)
    _validate_usage(job, params.usage)
    output_rows = await _output_rows(db_session, job.id)
    uploaded_output_bytes = sum(
        blob.size_bytes for _output, blob in output_rows if blob is not None
    )
    result_bytes = len(
        json.dumps(
            params.result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    if params.usage.output_bytes < uploaded_output_bytes + result_bytes:
        raise HTTPException(
            status_code=422,
            detail="Compute output usage is smaller than the submitted results",
        )
    try:
        validate_schema_payload(job.result_schema, params.result, "compute result")
        actual_cost = await settle_compute_budget(
            db_session,
            task=task,
            run=run,
            action=action,
            job=job,
            wall_seconds=params.usage.wall_seconds,
        )
    except (ValueError, ResearchBudgetError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    output_manifest = await _register_compute_output_assets(
        db_session,
        job=job,
        task=task,
        completed_outputs=params.outputs,
    )
    output_results = _registered_output_results(output_manifest)
    now = utcnow()
    runner.last_seen_at = now
    job.status = ResearchComputeJobStatus.COMPLETED.value
    job.result = params.result
    job.usage = params.usage.model_dump(mode="json")
    job.error = None
    job.completed_at = now
    job.lease_expires_at = None
    job.revision += 1
    action.status = ResearchActionStatus.COMPLETED.value
    action.output_data = {
        "compute_job_id": str(job.id),
        "environment_revision_id": str(job.compute_environment_revision_id),
        "source_sha256": job.source_sha256,
        "result": params.result,
        "outputs": output_results,
        "usage": job.usage,
        "actual_cost": str(actual_cost) if actual_cost is not None else None,
        "currency": job.currency,
    }
    action.error = None
    action.completed_at = now
    action.revision += 1
    append_aira_result(
        run,
        "compute_results",
        {
            "action_id": str(action.id),
            "compute_job_id": str(job.id),
            "environment_revision_id": str(job.compute_environment_revision_id),
            "source_sha256": job.source_sha256,
            "result": params.result,
            "outputs": output_results,
            "usage": job.usage,
            "actual_cost": str(actual_cost) if actual_cost is not None else None,
            "currency": job.currency,
            "completed_at": now.isoformat(),
        },
    )
    run.status = (
        ResearchRunStatus.PAUSED.value
        if task.status == ResearchTaskStatus.PAUSED.value
        else ResearchRunStatus.RUNNING.value
    )
    run.last_error = None
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="compute_job.completed",
        actor_user_id=None,
        payload={
            "compute_job_id": str(job.id),
            "runner_id": str(runner.id),
            "source_sha256": job.source_sha256,
            "usage": job.usage,
            "outputs": output_results,
            "actual_cost": str(actual_cost) if actual_cost is not None else None,
            "currency": job.currency,
        },
        idempotency_key=f"compute-job:{job.id}:completed",
    )
    if (
        task.status == ResearchTaskStatus.ACTIVE.value
        and config.effective_ai_enabled
        and await research_run_has_executable_ai_path(db_session, task=task, run=run)
    ):
        await enqueue_research_advance(db_session, task=task, run=run)
    elif task.status == ResearchTaskStatus.ACTIVE.value:
        run.last_error = "AI is unavailable; continue this Research Task manually."
        await emit_research_event(
            db_session,
            task_id=task.id,
            run_id=run.id,
            action_id=action.id,
            kind="run.manual_control_required",
            actor_user_id=None,
            payload={"reason": "compute_completed_without_ai"},
            idempotency_key=f"run:{run.id}:manual:compute-job:{job.id}",
        )
    await db_session.commit()
    return {"status": job.status}


@runtime_router.post("/jobs/{job_id}/fail")
async def fail_compute_job(
    job_id: UUID,
    params: RunnerFail,
    runner_token: RunnerToken,
    lease_token: LeaseToken,
    db_session: DBSession,
):
    runner = await authenticate_compute_runner(db_session, runner_token)
    job, action, run, task = await _runner_job_context(
        db_session, runner=runner, job_id=job_id, lease_token=lease_token
    )
    if job.status == ResearchComputeJobStatus.FAILED.value:
        expected_usage = params.usage.model_dump(mode="json") if params.usage else {}
        if job.error != params.error or job.usage != expected_usage:
            raise HTTPException(
                status_code=409,
                detail="Compute Job was already failed with a different reason",
            )
        await db_session.commit()
        return {"status": job.status}
    if job.status not in {
        ResearchComputeJobStatus.LEASED.value,
        ResearchComputeJobStatus.RUNNING.value,
    }:
        raise HTTPException(status_code=409, detail="Compute Job is not active")
    _ensure_live_lease(job)
    if params.usage is not None:
        _validate_usage(job, params.usage)
        job.usage = params.usage.model_dump(mode="json")
    try:
        if params.usage is not None:
            await settle_compute_budget(
                db_session,
                task=task,
                run=run,
                action=action,
                job=job,
                wall_seconds=params.usage.wall_seconds,
            )
        else:
            await release_compute_budget(
                db_session,
                task=task,
                run=run,
                action=action,
                job=job,
                suffix="failure-release",
                actor_user_id=None,
            )
    except ResearchBudgetError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    runner.last_seen_at = utcnow()
    await _pause_compute_failure(
        job=job, action=action, run=run, task=task, error=params.error
    )
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="compute_job.failed",
        actor_user_id=None,
        payload={
            "compute_job_id": str(job.id),
            "runner_id": str(runner.id),
            "error": params.error,
            "usage": job.usage,
        },
        idempotency_key=f"compute-job:{job.id}:failed",
    )
    await db_session.commit()
    return {"status": job.status}


@runtime_router.post("/jobs/{job_id}/cancelled")
async def acknowledge_compute_cancellation(
    job_id: UUID,
    params: RunnerCancelled,
    runner_token: RunnerToken,
    lease_token: LeaseToken,
    db_session: DBSession,
):
    runner = await authenticate_compute_runner(db_session, runner_token)
    job, action, run, task = await _runner_job_context(
        db_session, runner=runner, job_id=job_id, lease_token=lease_token
    )
    if job.status == ResearchComputeJobStatus.CANCELLED.value:
        expected_usage = params.usage.model_dump(mode="json") if params.usage else {}
        expected_reason = params.reason.strip() or job.cancel_reason
        if job.usage != expected_usage or job.cancel_reason != expected_reason:
            raise HTTPException(
                status_code=409,
                detail="Compute Job was already cancelled with a different result",
            )
        await db_session.commit()
        return {"status": job.status}
    if job.status != ResearchComputeJobStatus.CANCEL_REQUESTED.value:
        raise HTTPException(status_code=409, detail="Cancellation was not requested")
    now = utcnow()
    runner.last_seen_at = now
    if params.usage is not None:
        _validate_usage(job, params.usage)
        job.usage = params.usage.model_dump(mode="json")
    try:
        if params.usage is not None:
            await settle_compute_budget(
                db_session,
                task=task,
                run=run,
                action=action,
                job=job,
                wall_seconds=params.usage.wall_seconds,
            )
        else:
            await release_compute_budget(
                db_session,
                task=task,
                run=run,
                action=action,
                job=job,
                suffix="cancelled-release",
                actor_user_id=None,
            )
    except ResearchBudgetError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    job.status = ResearchComputeJobStatus.CANCELLED.value
    job.cancel_reason = params.reason.strip() or job.cancel_reason
    job.completed_at = now
    job.lease_expires_at = None
    job.revision += 1
    action.status = ResearchActionStatus.CANCELLED.value
    action.error = f"Cancelled: {job.cancel_reason or 'requested'}"
    action.completed_at = now
    action.revision += 1
    if task.status != ResearchTaskStatus.CANCELLED.value:
        run.status = ResearchRunStatus.PAUSED.value
        run.last_error = (
            "Compute Job cancelled; inspect partial outputs before resuming."
        )
        task.status = ResearchTaskStatus.PAUSED.value
        task.revision += 1
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="compute_job.cancelled",
        actor_user_id=None,
        payload={
            "compute_job_id": str(job.id),
            "runner_id": str(runner.id),
            "reason": job.cancel_reason,
            "usage": job.usage,
        },
        idempotency_key=f"compute-job:{job.id}:cancelled",
    )
    await db_session.commit()
    return {"status": job.status}
