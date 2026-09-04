"""Leased, schema-bounded Instrument Job Research Actions."""

from __future__ import annotations

import hmac
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select

from app.config import config
from app.database import DBSession
from app.models.lab import Lab
from app.models.project import Project
from app.models.research import (
    ResearchAction,
    ResearchActionKind,
    ResearchActionStatus,
    ResearchRun,
    ResearchRunStatus,
    ResearchTask,
    ResearchTaskStatus,
)
from app.models.research_execution import (
    ResearchInstrumentCommand,
    ResearchInstrumentControlSession,
    ResearchInstrumentControlStatus,
    ResearchInstrumentGateway,
    ResearchInstrumentJob,
    ResearchInstrumentJobStatus,
)
from app.models.resource import (
    BookingStatus,
    EquipmentBooking,
    Resource,
    ResourceRevision,
    ResourceStatus,
)
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.access_control import resolve_resource_access
from app.services.model_usage import create_usage_context
from app.services.research_budget import reached_operational_limit
from app.services.research_executor_bindings import (
    enforce_environment_binding_action_limit,
    executor_binding_command_ref,
)
from app.services.research_instrument_control import (
    STEP_KEY_RE,
    advance_control_session_after_job,
    control_command_pin,
    control_program_step,
    instrument_control_snapshot,
    mark_control_session_failed,
    mark_control_session_running,
    mark_control_session_stopping,
    pause_control_session_before_start,
    queue_control_step,
    validate_control_structure,
)
from app.services.research_instrument_control_drafts import (
    generate_instrument_control_draft,
    validate_instrument_control_output,
)
from app.services.research_instruments import (
    available_instrument_command_options,
    command_snapshot,
    gateway_token_digest,
    generate_job_lease_token,
    instrument_job_snapshot,
    job_lease_token_digest,
    resolve_instrument_executor_binding,
    sign_job_envelope,
    validate_safety_attestation,
    validate_schema_payload,
)
from app.services.research_runtime import (
    append_aira_result,
    canonical_digest,
    create_plan_version,
    emit_research_event,
    enqueue_research_advance,
    hold_or_release_aira_action_group,
    require_research_capability,
    utcnow,
)

router = APIRouter(tags=["research-instrument-jobs"])
gateway_router = APIRouter(
    prefix="/instrument-gateway/v1", tags=["instrument-gateway-runtime"]
)

GatewayToken = Annotated[str, Header(alias="X-Airalogy-Gateway-Token")]
LeaseToken = Annotated[str, Header(alias="X-Airalogy-Instrument-Lease")]
LEASE_SECONDS = 120
FINAL_JOB_STATUSES = {
    ResearchInstrumentJobStatus.COMPLETED.value,
    ResearchInstrumentJobStatus.FAILED.value,
    ResearchInstrumentJobStatus.CANCELLED.value,
    ResearchInstrumentJobStatus.STOPPED.value,
}
ACTIVE_JOB_STATUSES = {
    ResearchInstrumentJobStatus.QUEUED.value,
    ResearchInstrumentJobStatus.LEASED.value,
    ResearchInstrumentJobStatus.RUNNING.value,
    ResearchInstrumentJobStatus.STOP_REQUESTED.value,
}


class InstrumentActionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: UUID
    equipment_booking_id: UUID
    arguments: dict[str, Any] = Field(default_factory=dict)
    title: str = Field(default="", max_length=255)
    description: str = Field(default="", max_length=20_000)
    idempotency_key: str = Field(min_length=8, max_length=160)

    @model_validator(mode="after")
    def normalize(self):
        self.title = self.title.strip()
        self.description = self.description.strip()
        self.idempotency_key = self.idempotency_key.strip()
        return self


class InstrumentActionCreate(InstrumentActionDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class InstrumentControlCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=255)
    operator: Literal["eq", "ne", "lt", "lte", "gt", "gte", "in", "exists"]
    value: Any


class InstrumentControlTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condition: InstrumentControlCondition | None = None
    on_true: str = Field(min_length=1, max_length=64)
    on_false: str | None = Field(default=None, max_length=64)


class InstrumentControlStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=64)
    command_id: UUID
    arguments: dict[str, Any] = Field(default_factory=dict)
    transition: InstrumentControlTransition

    @model_validator(mode="after")
    def normalize(self):
        self.key = self.key.strip().lower()
        if not STEP_KEY_RE.fullmatch(self.key):
            raise ValueError("Instrument Control step key is invalid")
        self.transition.on_true = self.transition.on_true.strip().lower()
        if self.transition.on_false is not None:
            self.transition.on_false = self.transition.on_false.strip().lower()
        return self


class InstrumentControlDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["bounded_sequence", "feedback_loop"]
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=20_000)
    equipment_booking_id: UUID
    entry_step_key: str = Field(min_length=1, max_length=64)
    steps: list[InstrumentControlStep] = Field(min_length=1, max_length=20)
    max_steps: int = Field(ge=1, le=50)
    max_duration_seconds: int = Field(ge=1, le=86_400)
    idempotency_key: str = Field(min_length=8, max_length=160)

    @model_validator(mode="after")
    def normalize(self):
        self.title = self.title.strip()
        self.description = self.description.strip()
        self.entry_step_key = self.entry_step_key.strip().lower()
        self.idempotency_key = self.idempotency_key.strip()
        if not self.title:
            raise ValueError("Instrument Control title is required")
        if not self.idempotency_key:
            raise ValueError("Instrument Control idempotency key is required")
        provisional = {
            "schema": "airalogy.instrument-control.v1",
            "mode": self.mode,
            "entry_step_key": self.entry_step_key,
            "max_steps": self.max_steps,
            "max_duration_seconds": self.max_duration_seconds,
            "steps": [
                {
                    "key": step.key,
                    "command": {"id": str(step.command_id)},
                    "arguments": step.arguments,
                    "transition": step.transition.model_dump(),
                }
                for step in self.steps
            ],
        }
        validate_control_structure(provisional)
        return self


class InstrumentControlCreate(InstrumentControlDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class AiraInstrumentControlDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(min_length=1, max_length=4_000)
    mode: Literal["bounded_sequence", "feedback_loop"]
    equipment_booking_id: UUID
    max_step_templates: int = Field(ge=1, le=20)
    max_steps: int = Field(ge=1, le=50)
    max_duration_seconds: int = Field(ge=1, le=86_400)

    @model_validator(mode="after")
    def normalize(self):
        self.instruction = self.instruction.strip()
        if not self.instruction:
            raise ValueError("Aira Instrument Control instruction is required")
        if self.max_step_templates > self.max_steps:
            raise ValueError("Step template limit cannot exceed maximum executions")
        return self


class InstrumentControlDecisionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def normalize(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("Decision reason is required")
        return self


class InstrumentControlDecision(InstrumentControlDecisionDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class InstrumentStopDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def normalize(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("Stop reason is required")
        return self


class InstrumentStop(InstrumentStopDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class GatewayStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_confirmed: bool = False
    confirmation_reference: str = Field(default="", max_length=255)
    safety_attestation: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize(self):
        self.confirmation_reference = self.confirmation_reference.strip()
        return self


class GatewayComplete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: dict[str, Any] = Field(default_factory=dict)


class GatewayFail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: str = Field(min_length=1, max_length=20_000)

    @model_validator(mode="after")
    def normalize(self):
        self.error = self.error.strip()
        if not self.error:
            raise ValueError("Failure reason is required")
        return self


class GatewayStopped(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="", max_length=2_000)

    @model_validator(mode="after")
    def normalize(self):
        self.reason = self.reason.strip()
        return self


async def _project(db_session: DBSession, project_id: UUID) -> Project:
    project = await Project.find_by(
        db_session, [Project.id == project_id, Project.deleted_at.is_(None)]
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _active_task_context(
    db_session: DBSession,
    current_user: User,
    task_id: UUID,
    *,
    capability: str = "research.run",
    enforce_limits: bool = False,
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
    if task.status != ResearchTaskStatus.ACTIVE.value:
        raise HTTPException(status_code=409, detail="Research Task must be active")
    run = (
        await db_session.scalars(
            select(ResearchRun)
            .where(ResearchRun.task_id == task.id)
            .order_by(ResearchRun.run_number.desc())
            .limit(1)
        )
    ).first()
    if run is None or run.status in {
        ResearchRunStatus.COMPLETED.value,
        ResearchRunStatus.FAILED.value,
        ResearchRunStatus.CANCELLED.value,
    }:
        raise HTTPException(status_code=409, detail="Active Research Run not found")
    if enforce_limits:
        operational_limit = await reached_operational_limit(db_session, task=task)
        if operational_limit is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Research Task {operational_limit[0]} limit has been reached",
            )
    return task, project, lab, run


def _destination(
    *, task: ResearchTask, project: Project, lab: Lab, run: ResearchRun
) -> dict[str, Any]:
    return {
        "lab": {"id": str(lab.id), "uid": lab.uid, "name": lab.name},
        "project": {
            "id": str(project.id),
            "uid": project.uid,
            "name": project.name,
        },
        "task": {"id": str(task.id), "title": task.title},
        "run": {"id": str(run.id), "number": run.run_number},
    }


async def _next_sequence(db_session: DBSession, run_id: UUID) -> int:
    return (
        await db_session.scalar(
            select(func.max(ResearchAction.sequence)).where(
                ResearchAction.run_id == run_id
            )
        )
        or 0
    ) + 1


def _resource_type_is_pinned(run: ResearchRun, resource: Resource) -> bool:
    return any(
        str(item.get("source_id") or "") == str(resource.resource_type_id)
        for item in list((run.environment_snapshot or {}).get("resources") or [])
    )


async def _command_context(
    db_session: DBSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
    current_user: User,
    command_id: UUID,
    booking_id: UUID,
    lock: bool = False,
) -> tuple[
    ResearchInstrumentCommand,
    ResearchInstrumentGateway,
    Resource,
    ResourceRevision,
    EquipmentBooking,
]:
    statement = select(ResearchInstrumentCommand).where(
        ResearchInstrumentCommand.id == command_id,
        ResearchInstrumentCommand.archived_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    command = (await db_session.scalars(statement)).first()
    if command is None or command.lab_id != task.lab_id or not command.enabled:
        raise HTTPException(status_code=422, detail="Instrument command is unavailable")
    gateway = await db_session.get(ResearchInstrumentGateway, command.gateway_id)
    if gateway is None or gateway.revoked_at is not None or not gateway.enabled:
        raise HTTPException(status_code=422, detail="Instrument Gateway is unavailable")
    resource = await db_session.get(Resource, command.resource_id)
    revision = await db_session.get(ResourceRevision, command.resource_revision_id)
    if (
        resource is None
        or revision is None
        or resource.lab_id != task.lab_id
        or resource.archived_at is not None
        or resource.status != ResourceStatus.ACTIVE.value
        or resource.current_revision_id != revision.id
        or revision.revision != command.resource_revision
    ):
        raise HTTPException(
            status_code=409,
            detail="The pinned equipment revision is no longer current",
        )
    if not _resource_type_is_pinned(run, resource):
        raise HTTPException(
            status_code=422,
            detail="Equipment type is not pinned in this Research Environment",
        )
    access = await resolve_resource_access(
        db_session,
        current_user.id,
        task.lab_id,
        resource_type_id=resource.resource_type_id,
        resource_id=resource.id,
    )
    if not access.allows("equipment.book"):
        raise HTTPException(status_code=403, detail="Equipment execution access denied")
    booking_statement = select(EquipmentBooking).where(
        EquipmentBooking.id == booking_id
    )
    if lock:
        booking_statement = booking_statement.with_for_update()
    booking = (await db_session.scalars(booking_statement)).first()
    if (
        booking is None
        or booking.lab_id != task.lab_id
        or booking.resource_id != resource.id
        or booking.user_id != current_user.id
        or booking.status != BookingStatus.APPROVED.value
        or booking.ends_at <= utcnow()
    ):
        raise HTTPException(
            status_code=422,
            detail="An approved, unexpired equipment booking is required",
        )
    return command, gateway, resource, revision, booking


def _action_command(
    *,
    task: ResearchTask,
    run: ResearchRun,
    command: ResearchInstrumentCommand,
    booking: EquipmentBooking,
    executor_binding: dict[str, Any],
    params: InstrumentActionDraft,
) -> dict[str, Any]:
    try:
        validate_schema_payload(command.input_schema, params.arguments, "command input")
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "task_id": str(task.id),
        "task_revision": task.revision,
        "run_id": str(run.id),
        "run_plan_version": run.plan_version,
        "command_id": str(command.id),
        "command_key": command.command_key,
        "command_version": command.command_version,
        "command_revision": command.revision,
        "safety_contract": command.safety_contract,
        "executor_binding": executor_binding_command_ref(executor_binding),
        "resource_id": str(command.resource_id),
        "resource_revision_id": str(command.resource_revision_id),
        "resource_revision": command.resource_revision,
        "equipment_booking_id": str(booking.id),
        "booking_window": {
            "starts_at": booking.starts_at.isoformat(),
            "ends_at": booking.ends_at.isoformat(),
        },
        "arguments": params.arguments,
        "title": params.title or command.name,
        "description": params.description,
        "idempotency_key": params.idempotency_key,
    }


@router.get("/research-instrument-commands")
async def list_available_instrument_commands(
    task_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, _project_context, _lab, run = await _active_task_context(
        db_session, current_user, task_id, capability="research.read"
    )
    return {
        "items": await available_instrument_command_options(
            db_session,
            task=task,
            run=run,
            user_id=current_user.id,
            resolve_bindings=True,
        )
    }


async def _aira_instrument_control_catalog(
    db_session: DBSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
    current_user: User,
    params: AiraInstrumentControlDraftRequest,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    options = await available_instrument_command_options(
        db_session,
        task=task,
        run=run,
        user_id=current_user.id,
        resolve_bindings=True,
    )
    booking: dict[str, Any] | None = None
    commands: list[dict[str, Any]] = []
    for item in options:
        selected_booking = next(
            (
                candidate
                for candidate in item.get("bookings") or []
                if str(candidate.get("id") or "") == str(params.equipment_booking_id)
            ),
            None,
        )
        if selected_booking is None:
            continue
        starts_at = selected_booking.get("starts_at")
        ends_at = selected_booking.get("ends_at")
        booking_snapshot = {
            "id": str(selected_booking.get("id") or ""),
            "status": selected_booking.get("status"),
            "starts_at": (
                starts_at.isoformat()
                if isinstance(starts_at, datetime)
                else str(starts_at or "")
            ),
            "ends_at": (
                ends_at.isoformat()
                if isinstance(ends_at, datetime)
                else str(ends_at or "")
            ),
            "purpose": str(selected_booking.get("purpose") or "")[:1_000],
            "resource": item["resource"],
        }
        if booking is None:
            booking = booking_snapshot
        elif canonical_digest(booking) != canonical_digest(booking_snapshot):
            raise HTTPException(
                status_code=409,
                detail="The approved equipment booking changed while resolving commands",
            )
        commands.append(
            {
                "id": item["id"],
                "name": item["name"],
                "description": str(item.get("description") or "")[:1_000],
                "command_key": item["command_key"],
                "command_version": item["command_version"],
                "revision": item["revision"],
                "risk": item["risk"],
                "input_schema": item["input_schema"],
                "output_schema": item["output_schema"],
                "device_confirmation_required": item["device_confirmation_required"],
                "safety_contract": item["safety_contract"],
                "gateway": item["gateway"],
                "resource": item["resource"],
                "executor_binding": executor_binding_command_ref(
                    item["executor_binding"]
                ),
            }
        )
    if booking is None or not commands:
        raise HTTPException(
            status_code=422,
            detail=(
                "The selected booking has no currently authorized Instrument commands"
            ),
        )
    if len(commands) > 50:
        raise HTTPException(
            status_code=422,
            detail="The selected booking exposes too many commands for safe Aira drafting",
        )
    booking_start = booking.get("starts_at")
    booking_end = booking.get("ends_at")
    if not isinstance(booking_start, str) or not isinstance(booking_end, str):
        raise HTTPException(status_code=409, detail="Equipment booking is incomplete")
    try:
        available_seconds = int(
            (
                datetime.fromisoformat(booking_end)
                - max(datetime.fromisoformat(booking_start), utcnow())
            ).total_seconds()
        )
    except ValueError as error:
        raise HTTPException(
            status_code=409, detail="Equipment booking window is invalid"
        ) from error
    if params.max_duration_seconds > available_seconds:
        raise HTTPException(
            status_code=422,
            detail="Instrument Control duration exceeds the approved booking window",
        )
    return booking, commands


@router.post("/research-tasks/{task_id}/instrument-control-sessions/draft-with-aira")
async def draft_instrument_control_session_with_aira(
    task_id: UUID,
    params: AiraInstrumentControlDraftRequest,
    current_user: CurrentUser,
    db_session: DBSession,
):
    if not config.effective_ai_enabled:
        raise HTTPException(
            status_code=409,
            detail=(
                "Aira is unavailable. Build the same Instrument Control draft "
                "manually with the deterministic editor."
            ),
        )
    task, _project_context, _lab, run = await _active_task_context(
        db_session, current_user, task_id, enforce_limits=True
    )
    booking, commands = await _aira_instrument_control_catalog(
        db_session,
        task=task,
        run=run,
        current_user=current_user,
        params=params,
    )
    source_snapshot = {
        "task_id": str(task.id),
        "task_revision": task.revision,
        "run_id": str(run.id),
        "run_plan_version": run.plan_version,
        "mode": params.mode,
        "max_step_templates": params.max_step_templates,
        "max_steps": params.max_steps,
        "max_duration_seconds": params.max_duration_seconds,
        "booking": booking,
        "commands": commands,
    }
    source_digest = canonical_digest(source_snapshot)
    model_name = config.CHAT_MODEL_FAST
    usage_context = create_usage_context(
        feature="research.instrument_control.draft",
        user_id=current_user.id,
        lab_id=task.lab_id,
        project_id=task.project_id,
        attributes={
            "mode": params.mode,
            "command_count": str(len(commands)),
            "max_steps": str(params.max_steps),
        },
    )
    # Never hold database locks or a transaction open across model latency.
    await db_session.commit()
    try:
        output, _program = await generate_instrument_control_draft(
            instruction=params.instruction,
            mode=params.mode,
            max_step_templates=params.max_step_templates,
            max_steps=params.max_steps,
            max_duration_seconds=params.max_duration_seconds,
            booking=booking,
            commands=commands,
            model_name=model_name,
            usage_context=usage_context,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail="Aira could not produce a valid Instrument Control draft",
        ) from error
    db_session.expire_all()
    current_task, _project_context, _lab, current_run = await _active_task_context(
        db_session, current_user, task_id, enforce_limits=True
    )
    current_booking, current_commands = await _aira_instrument_control_catalog(
        db_session,
        task=current_task,
        run=current_run,
        current_user=current_user,
        params=params,
    )
    current_snapshot = {
        **source_snapshot,
        "task_revision": current_task.revision,
        "run_id": str(current_run.id),
        "run_plan_version": current_run.plan_version,
        "booking": current_booking,
        "commands": current_commands,
    }
    if canonical_digest(current_snapshot) != source_digest:
        raise HTTPException(
            status_code=409,
            detail=(
                "Instrument commands, booking, permissions, or Research Run changed "
                "while Aira prepared the draft"
            ),
        )
    try:
        program = validate_instrument_control_output(
            output,
            mode=params.mode,
            max_step_templates=params.max_step_templates,
            max_steps=params.max_steps,
            max_duration_seconds=params.max_duration_seconds,
            commands=current_commands,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=409,
            detail=(
                "Instrument Control constraints changed while Aira prepared the draft"
            ),
        ) from error
    return {
        "draft": {
            "mode": params.mode,
            "title": output.title,
            "description": output.description,
            "equipment_booking_id": str(params.equipment_booking_id),
            "entry_step_key": output.entry_step_key,
            "steps": [
                {
                    "key": step.key,
                    "command_id": str(step.command_id),
                    "arguments": step.arguments,
                    "transition": step.transition.model_dump(mode="json"),
                }
                for step in output.steps
            ],
            "max_steps": program["max_steps"],
            "max_duration_seconds": params.max_duration_seconds,
            "idempotency_key": f"aira-instrument-control-{uuid4()}",
        },
        "rationale": output.rationale,
        "assumptions": output.assumptions,
        "warnings": output.warnings,
        "model": model_name,
        "source_digest": source_digest,
        "boundary": (
            "Editable draft only. No Control Session, Instrument Job, approval, "
            "reservation, or device command was created."
        ),
    }


async def _instrument_control_command(
    db_session: DBSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
    current_user: User,
    params: InstrumentControlDraft,
    lock: bool = False,
) -> tuple[dict[str, Any], ResearchInstrumentGateway, Resource, EquipmentBooking]:
    pinned_steps: list[dict[str, Any]] = []
    base_gateway: ResearchInstrumentGateway | None = None
    base_resource: Resource | None = None
    base_booking: EquipmentBooking | None = None
    for step in params.steps:
        command, gateway, resource, _revision, booking = await _command_context(
            db_session,
            task=task,
            run=run,
            current_user=current_user,
            command_id=step.command_id,
            booking_id=params.equipment_booking_id,
            lock=lock,
        )
        if base_gateway is None:
            base_gateway = gateway
            base_resource = resource
            base_booking = booking
        elif gateway.id != base_gateway.id or resource.id != base_resource.id:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Every Instrument Control step must use the same Gateway and "
                    "equipment booking"
                ),
            )
        try:
            validate_schema_payload(
                command.input_schema, step.arguments, f"step {step.key} input"
            )
            executor_binding = await resolve_instrument_executor_binding(
                db_session,
                task=task,
                command=command,
                gateway=gateway,
                resource=resource,
            )
            await enforce_environment_binding_action_limit(
                db_session, run=run, binding=executor_binding
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        pinned_steps.append(
            {
                "key": step.key,
                "command": {
                    **control_command_pin(command),
                    "executor_binding": executor_binding,
                },
                "arguments": step.arguments,
                "transition": step.transition.model_dump(),
            }
        )
    if base_gateway is None or base_resource is None or base_booking is None:
        raise HTTPException(status_code=422, detail="Instrument Control has no steps")
    booking_seconds = int(
        (base_booking.ends_at - max(base_booking.starts_at, utcnow())).total_seconds()
    )
    if params.max_duration_seconds > booking_seconds:
        raise HTTPException(
            status_code=422,
            detail="Instrument Control duration exceeds the approved booking window",
        )
    program = {
        "schema": "airalogy.instrument-control.v1",
        "mode": params.mode,
        "entry_step_key": params.entry_step_key,
        "max_steps": params.max_steps,
        "max_duration_seconds": params.max_duration_seconds,
        "steps": pinned_steps,
    }
    try:
        validate_control_structure(program)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    command_data = {
        "operation": "create_instrument_control_session",
        "task_id": str(task.id),
        "task_revision": task.revision,
        "run_id": str(run.id),
        "run_plan_version": run.plan_version,
        "title": params.title,
        "description": params.description,
        "equipment_booking_id": str(base_booking.id),
        "booking_window": {
            "starts_at": base_booking.starts_at.isoformat(),
            "ends_at": base_booking.ends_at.isoformat(),
        },
        "program": program,
        "idempotency_key": params.idempotency_key,
    }
    return command_data, base_gateway, base_resource, base_booking


@router.post("/research-tasks/{task_id}/instrument-control-sessions/preview")
async def preview_instrument_control_session(
    task_id: UUID,
    params: InstrumentControlDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, project, lab, run = await _active_task_context(
        db_session, current_user, task_id, enforce_limits=True
    )
    command, gateway, resource, booking = await _instrument_control_command(
        db_session,
        task=task,
        run=run,
        current_user=current_user,
        params=params,
    )
    risks = [step["command"]["risk"] for step in command["program"]["steps"]]
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": _destination(task=task, project=project, lab=lab, run=run),
        "instrument_control": {
            "mode": params.mode,
            "gateway": {"id": str(gateway.id), "name": gateway.name},
            "resource": {
                "id": str(resource.id),
                "name": resource.name,
                "code": resource.code,
            },
            "booking": booking.as_dict(),
            "step_count": len(params.steps),
            "max_steps": params.max_steps,
            "max_duration_seconds": params.max_duration_seconds,
            "highest_risk": next(
                (
                    risk
                    for risk in ("high", "medium", "low", "read_only")
                    if risk in risks
                ),
                "read_only",
            ),
            "program": command["program"],
        },
        "effects": [
            "Create a version-pinned, bounded Instrument Control Session",
            "Release only one ordinary Instrument Job at a time",
            "Evaluate each transition deterministically from a schema-validated result",
            "Preserve Gateway leases, device confirmation, interlocks, audit, and stop handling for every step",
        ],
        "warnings": [
            "Physical operations are never retried automatically.",
            "Every later high-risk step pauses for a fresh human checkpoint.",
            "A limit, stale pin, missing result path, or failed comparison pauses the session instead of guessing.",
        ],
    }


@router.post("/research-tasks/{task_id}/instrument-control-sessions")
async def create_instrument_control_session(
    task_id: UUID,
    params: InstrumentControlCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, _project_context, _lab, run = await _active_task_context(
        db_session, current_user, task_id, enforce_limits=True
    )
    command, gateway, resource, booking = await _instrument_control_command(
        db_session,
        task=task,
        run=run,
        current_user=current_user,
        params=params,
        lock=True,
    )
    digest = canonical_digest(command)
    if digest != params.preview_digest:
        raise HTTPException(
            status_code=409, detail="Instrument Control preview changed"
        )
    existing = await ResearchInstrumentControlSession.find_by(
        db_session,
        [
            ResearchInstrumentControlSession.run_id == run.id,
            ResearchInstrumentControlSession.idempotency_key == params.idempotency_key,
        ],
    )
    if existing is not None:
        if existing.creation_digest != digest:
            raise HTTPException(
                status_code=409,
                detail="Instrument Control idempotency key is already in use",
            )
        jobs = list(
            (
                await db_session.scalars(
                    select(ResearchInstrumentJob)
                    .where(ResearchInstrumentJob.control_session_id == existing.id)
                    .order_by(ResearchInstrumentJob.control_execution_index)
                )
            ).all()
        )
        return instrument_control_snapshot(existing, jobs=jobs)
    active = await db_session.scalar(
        select(func.count())
        .select_from(ResearchInstrumentJob)
        .where(
            ResearchInstrumentJob.equipment_booking_id == booking.id,
            ResearchInstrumentJob.status.in_(ACTIVE_JOB_STATUSES),
        )
    )
    if active:
        raise HTTPException(
            status_code=409,
            detail="This equipment booking already has an active Instrument Job",
        )
    await create_plan_version(
        db_session,
        task=task,
        run=run,
        kind="manual",
        plan={
            "instrument_control": command,
            "previous_plan_version": run.plan_version,
        },
        summary=f"Run bounded Instrument Control: {params.title}",
    )
    session = ResearchInstrumentControlSession(
        run_id=run.id,
        gateway_id=gateway.id,
        resource_id=resource.id,
        equipment_booking_id=booking.id,
        mode=params.mode,
        status=ResearchInstrumentControlStatus.QUEUED.value,
        title=params.title,
        description=params.description,
        program=command["program"],
        program_digest=canonical_digest(command["program"]),
        creation_digest=digest,
        idempotency_key=params.idempotency_key,
        entry_step_key=params.entry_step_key,
        max_steps=params.max_steps,
        max_duration_seconds=params.max_duration_seconds,
        created_by_user_id=current_user.id,
    )
    db_session.add(session)
    await db_session.flush()
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=None,
        kind="instrument_control.created",
        actor_user_id=current_user.id,
        payload={
            "control_session_id": str(session.id),
            "mode": session.mode,
            "program_digest": session.program_digest,
            "max_steps": session.max_steps,
            "max_duration_seconds": session.max_duration_seconds,
        },
        idempotency_key=f"instrument-control:{session.id}:created",
    )
    try:
        _action, job = await queue_control_step(
            db_session,
            session=session,
            task=task,
            run=run,
            step_key=session.entry_step_key,
            actor_user_id=current_user.id,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    await db_session.commit()
    return instrument_control_snapshot(session, jobs=[job])


async def _control_session_context(
    db_session: DBSession,
    current_user: User,
    session_id: UUID,
    *,
    lock: bool,
    capability: str = "research.run",
) -> tuple[
    ResearchInstrumentControlSession,
    ResearchRun,
    ResearchTask,
    Project,
    Lab,
]:
    statement = select(ResearchInstrumentControlSession).where(
        ResearchInstrumentControlSession.id == session_id
    )
    if lock:
        statement = statement.with_for_update()
    session = (await db_session.scalars(statement)).first()
    run = await db_session.get(ResearchRun, session.run_id) if session else None
    task = await db_session.get(ResearchTask, run.task_id) if run else None
    if session is None or run is None or task is None:
        raise HTTPException(
            status_code=404, detail="Instrument Control Session not found"
        )
    project = await _project(db_session, task.project_id)
    await require_research_capability(
        db_session, user=current_user, project=project, capability=capability
    )
    lab = await db_session.get(Lab, task.lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    return session, run, task, project, lab


@router.get("/research-instrument-control-sessions/{session_id}")
async def get_instrument_control_session(
    session_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    session, _run, _task, _project_context, _lab = await _control_session_context(
        db_session,
        current_user,
        session_id,
        lock=False,
        capability="research.read",
    )
    jobs = list(
        (
            await db_session.scalars(
                select(ResearchInstrumentJob)
                .where(ResearchInstrumentJob.control_session_id == session.id)
                .order_by(ResearchInstrumentJob.control_execution_index)
            )
        ).all()
    )
    return instrument_control_snapshot(session, jobs=jobs)


def _control_decision_command(
    *,
    operation: str,
    session: ResearchInstrumentControlSession,
    params: InstrumentControlDecisionDraft,
) -> dict[str, Any]:
    return {
        "operation": operation,
        "control_session_id": str(session.id),
        "expected_revision": params.expected_revision,
        "program_digest": session.program_digest,
        "pending_step_key": session.pending_step_key,
        "reason": params.reason,
    }


@router.post("/research-instrument-control-sessions/{session_id}/resume/preview")
async def preview_resume_instrument_control_session(
    session_id: UUID,
    params: InstrumentControlDecisionDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    session, run, task, project, lab = await _control_session_context(
        db_session, current_user, session_id, lock=False
    )
    if session.revision != params.expected_revision:
        raise HTTPException(
            status_code=409, detail="Instrument Control Session changed"
        )
    if (
        session.status != ResearchInstrumentControlStatus.PAUSED_FOR_REVIEW.value
        or not session.pending_step_key
    ):
        raise HTTPException(
            status_code=409,
            detail="Instrument Control Session has no resumable pending step",
        )
    command = _control_decision_command(
        operation="resume_instrument_control_session",
        session=session,
        params=params,
    )
    step = control_program_step(session.program, session.pending_step_key)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": _destination(task=task, project=project, lab=lab, run=run),
        "instrument_control": instrument_control_snapshot(session),
        "pending_step": step,
        "effects": [
            "Revalidate the exact pending command, booking, access, and device revision",
            "Queue one Instrument Job; no later high-risk command is pre-approved",
        ],
    }


@router.post("/research-instrument-control-sessions/{session_id}/resume")
async def resume_instrument_control_session(
    session_id: UUID,
    params: InstrumentControlDecision,
    current_user: CurrentUser,
    db_session: DBSession,
):
    session, run, task, _project_context, _lab = await _control_session_context(
        db_session, current_user, session_id, lock=True
    )
    if session.revision != params.expected_revision:
        raise HTTPException(
            status_code=409, detail="Instrument Control Session changed"
        )
    if (
        session.status != ResearchInstrumentControlStatus.PAUSED_FOR_REVIEW.value
        or not session.pending_step_key
    ):
        raise HTTPException(
            status_code=409,
            detail="Instrument Control Session has no resumable pending step",
        )
    command = _control_decision_command(
        operation="resume_instrument_control_session",
        session=session,
        params=params,
    )
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="Resume preview changed")
    step_key = session.pending_step_key
    try:
        _action, job = await queue_control_step(
            db_session,
            session=session,
            task=task,
            run=run,
            step_key=step_key,
            actor_user_id=current_user.id,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=job.action_id,
        kind="instrument_control.resumed",
        actor_user_id=current_user.id,
        payload={
            "control_session_id": str(session.id),
            "step_key": step_key,
            "reason": params.reason,
        },
        idempotency_key=(
            f"instrument-control:{session.id}:resumed:{job.control_execution_index}"
        ),
    )
    await db_session.commit()
    return instrument_control_snapshot(session, jobs=[job])


@router.post("/research-instrument-control-sessions/{session_id}/stop/preview")
async def preview_stop_instrument_control_session(
    session_id: UUID,
    params: InstrumentControlDecisionDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    session, run, task, project, lab = await _control_session_context(
        db_session, current_user, session_id, lock=False
    )
    if session.revision != params.expected_revision:
        raise HTTPException(
            status_code=409, detail="Instrument Control Session changed"
        )
    if session.status in {
        ResearchInstrumentControlStatus.COMPLETED.value,
        ResearchInstrumentControlStatus.FAILED.value,
        ResearchInstrumentControlStatus.CANCELLED.value,
        ResearchInstrumentControlStatus.STOPPED.value,
    }:
        raise HTTPException(
            status_code=409, detail="Instrument Control Session is already final"
        )
    command = _control_decision_command(
        operation="stop_instrument_control_session",
        session=session,
        params=params,
    )
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": _destination(task=task, project=project, lab=lab, run=run),
        "instrument_control": instrument_control_snapshot(session),
        "effects": [
            "Prevent any later control step from being queued",
            "Cancel an undelivered job or request a device-side stop for active work",
            "Pause the Research Task for equipment inspection",
        ],
    }


@router.post("/research-instrument-control-sessions/{session_id}/stop")
async def stop_instrument_control_session(
    session_id: UUID,
    params: InstrumentControlDecision,
    current_user: CurrentUser,
    db_session: DBSession,
):
    session, run, task, _project_context, _lab = await _control_session_context(
        db_session, current_user, session_id, lock=True
    )
    if session.revision != params.expected_revision:
        raise HTTPException(
            status_code=409, detail="Instrument Control Session changed"
        )
    if session.status in {
        ResearchInstrumentControlStatus.COMPLETED.value,
        ResearchInstrumentControlStatus.FAILED.value,
        ResearchInstrumentControlStatus.CANCELLED.value,
        ResearchInstrumentControlStatus.STOPPED.value,
    }:
        raise HTTPException(
            status_code=409, detail="Instrument Control Session is already final"
        )
    command = _control_decision_command(
        operation="stop_instrument_control_session",
        session=session,
        params=params,
    )
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="Stop preview changed")
    active_job = (
        await db_session.scalars(
            select(ResearchInstrumentJob)
            .where(
                ResearchInstrumentJob.control_session_id == session.id,
                ResearchInstrumentJob.status.in_(ACTIVE_JOB_STATUSES),
            )
            .order_by(ResearchInstrumentJob.control_execution_index.desc())
            .limit(1)
            .with_for_update()
        )
    ).first()
    now = utcnow()
    if active_job is None:
        session.status = ResearchInstrumentControlStatus.STOPPED.value
        session.stop_reason = params.reason
        session.completed_at = now
        session.revision += 1
    else:
        action = await db_session.get(ResearchAction, active_job.action_id)
        if action is None:
            raise HTTPException(status_code=409, detail="Instrument Action is missing")
        previous_job_status = active_job.status
        active_job.stop_reason = params.reason
        active_job.stop_requested_at = now
        active_job.revision += 1
        if active_job.status == ResearchInstrumentJobStatus.QUEUED.value:
            active_job.status = ResearchInstrumentJobStatus.CANCELLED.value
            active_job.completed_at = now
            action.status = ResearchActionStatus.CANCELLED.value
            action.completed_at = now
            session.status = ResearchInstrumentControlStatus.STOPPED.value
            session.completed_at = now
        else:
            active_job.status = ResearchInstrumentJobStatus.STOP_REQUESTED.value
            action.status = ResearchActionStatus.WAITING.value
            session.status = ResearchInstrumentControlStatus.STOP_REQUESTED.value
        action.error = f"Stop requested: {params.reason}"
        action.revision += 1
        session.stop_reason = params.reason
        session.revision += 1
        await emit_research_event(
            db_session,
            task_id=task.id,
            run_id=run.id,
            action_id=action.id,
            kind="instrument_job.stop_requested",
            actor_user_id=current_user.id,
            payload={
                "instrument_job_id": str(active_job.id),
                "control_session_id": str(session.id),
                "previous_status": previous_job_status,
                "reason": params.reason,
            },
            idempotency_key=(
                f"instrument-job:{active_job.id}:control-stop:{active_job.revision}"
            ),
        )
    run.status = ResearchRunStatus.PAUSED.value
    run.last_error = (
        "Instrument Control stopped; inspect the equipment before resuming."
    )
    task.status = ResearchTaskStatus.PAUSED.value
    task.revision += 1
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=active_job.action_id if active_job is not None else None,
        kind=(
            "instrument_control.stop_requested"
            if session.status == ResearchInstrumentControlStatus.STOP_REQUESTED.value
            else "instrument_control.stopped"
        ),
        actor_user_id=current_user.id,
        payload={
            "control_session_id": str(session.id),
            "instrument_job_id": str(active_job.id) if active_job else None,
            "reason": params.reason,
        },
        idempotency_key=f"instrument-control:{session.id}:stop:{session.revision}",
    )
    await db_session.commit()
    return instrument_control_snapshot(
        session, jobs=[active_job] if active_job is not None else []
    )


@router.post("/research-tasks/{task_id}/instrument-actions/preview")
async def preview_instrument_action(
    task_id: UUID,
    params: InstrumentActionDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, project, lab, run = await _active_task_context(
        db_session, current_user, task_id, enforce_limits=True
    )
    command, gateway, resource, _revision, booking = await _command_context(
        db_session,
        task=task,
        run=run,
        current_user=current_user,
        command_id=params.command_id,
        booking_id=params.equipment_booking_id,
    )
    try:
        executor_binding = await resolve_instrument_executor_binding(
            db_session,
            task=task,
            command=command,
            gateway=gateway,
            resource=resource,
        )
        await enforce_environment_binding_action_limit(
            db_session, run=run, binding=executor_binding
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    command_data = _action_command(
        task=task,
        run=run,
        command=command,
        booking=booking,
        executor_binding=executor_binding,
        params=params,
    )
    return {
        "preview_digest": canonical_digest(command_data),
        "command": command_data,
        "destination": _destination(task=task, project=project, lab=lab, run=run),
        "instrument": {
            **command_snapshot(command),
            "gateway": {"id": str(gateway.id), "name": gateway.name},
            "resource": {
                "id": str(resource.id),
                "name": resource.name,
                "code": resource.code,
            },
            "booking": booking.as_dict(),
        },
        "executor_binding": executor_binding,
        "effects": [
            "Create an immutable, version-pinned Instrument Job",
            "Queue it for pull-only delivery to the selected Lab Gateway",
            "Require the approved booking and device-side confirmation at execution time",
            "Validate the result before the Research Run can continue",
        ],
        "warnings": [
            "Physical operations are never retried automatically.",
            "A stop request requires acknowledgement from the on-premises Gateway.",
        ],
    }


@router.post("/research-tasks/{task_id}/instrument-actions")
async def create_instrument_action(
    task_id: UUID,
    params: InstrumentActionCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, _project_context, _lab, run = await _active_task_context(
        db_session, current_user, task_id, enforce_limits=True
    )
    command, gateway, resource, _revision, booking = await _command_context(
        db_session,
        task=task,
        run=run,
        current_user=current_user,
        command_id=params.command_id,
        booking_id=params.equipment_booking_id,
        lock=True,
    )
    try:
        executor_binding = await resolve_instrument_executor_binding(
            db_session,
            task=task,
            command=command,
            gateway=gateway,
            resource=resource,
        )
        await enforce_environment_binding_action_limit(
            db_session, run=run, binding=executor_binding
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    command_data = _action_command(
        task=task,
        run=run,
        command=command,
        booking=booking,
        executor_binding=executor_binding,
        params=params,
    )
    digest = canonical_digest(command_data)
    if digest != params.preview_digest:
        raise HTTPException(status_code=409, detail="Instrument Action preview changed")
    existing = await ResearchAction.find_by(
        db_session,
        [
            ResearchAction.run_id == run.id,
            ResearchAction.idempotency_key == params.idempotency_key,
        ],
    )
    if existing is not None:
        if (
            existing.preview_digest != digest
            or existing.kind != ResearchActionKind.INSTRUMENT_JOB.value
        ):
            raise HTTPException(
                status_code=409, detail="Action idempotency key is already in use"
            )
        existing_job = await ResearchInstrumentJob.find_by(
            db_session, [ResearchInstrumentJob.action_id == existing.id]
        )
        if existing_job is None:
            raise HTTPException(
                status_code=409, detail="Instrument Action is incomplete"
            )
        return {
            **existing.as_dict(),
            "instrument_job": instrument_job_snapshot(existing_job),
        }
    booking_in_use = await db_session.scalar(
        select(func.count())
        .select_from(ResearchInstrumentJob)
        .where(
            ResearchInstrumentJob.equipment_booking_id == booking.id,
            ResearchInstrumentJob.status.in_(ACTIVE_JOB_STATUSES),
        )
    )
    if booking_in_use:
        raise HTTPException(
            status_code=409,
            detail="This equipment booking already has an active Instrument Job",
        )

    await create_plan_version(
        db_session,
        task=task,
        run=run,
        kind="manual",
        plan={"action": command_data, "previous_plan_version": run.plan_version},
        summary=f"Run {command.name} on {booking.resource_id}",
    )
    action = ResearchAction(
        run_id=run.id,
        sequence=await _next_sequence(db_session, run.id),
        plan_version=run.plan_version,
        kind=ResearchActionKind.INSTRUMENT_JOB.value,
        status=ResearchActionStatus.QUEUED.value,
        title=command_data["title"],
        description=command_data["description"],
        executor_type=executor_binding["executor_type"],
        input_data={
            "command_id": str(command.id),
            "command_key": command.command_key,
            "command_version": command.command_version,
            "command_revision": command.revision,
            "resource_id": str(command.resource_id),
            "equipment_booking_id": str(booking.id),
            "arguments": params.arguments,
            "source": "manual",
            "resume_run": True,
        },
        requirements={
            "risk": command.risk,
            "device_confirmation_required": command.device_confirmation_required,
            "safety_contract": command.safety_contract,
            "input_schema": command.input_schema,
            "output_schema": command.output_schema,
            "booking_window": command_data["booking_window"],
            "approval_policy": executor_binding["approval_policy"],
            "executor_binding": executor_binding,
        },
        policy_decision="allow",
        preview_digest=digest,
        idempotency_key=params.idempotency_key,
    )
    db_session.add(action)
    await db_session.flush()
    job = ResearchInstrumentJob(
        action_id=action.id,
        gateway_id=gateway.id,
        command_id=command.id,
        resource_id=command.resource_id,
        resource_revision_id=command.resource_revision_id,
        resource_revision=command.resource_revision,
        equipment_booking_id=booking.id,
        command_key=command.command_key,
        command_version=command.command_version,
        command_revision=command.revision,
        arguments=params.arguments,
        input_schema=command.input_schema,
        output_schema=command.output_schema,
        risk=command.risk,
        device_confirmation_required=command.device_confirmation_required,
        safety_contract=command.safety_contract,
        timeout_seconds=command.timeout_seconds,
    )
    db_session.add(job)
    run.advance_generation += 1
    run.status = ResearchRunStatus.WAITING_FOR_INSTRUMENT.value
    run.last_error = None
    await db_session.flush()
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="instrument_job.queued",
        actor_user_id=current_user.id,
        payload={
            "instrument_job_id": str(job.id),
            "gateway_id": str(gateway.id),
            "command_key": job.command_key,
            "command_version": job.command_version,
            "equipment_booking_id": str(booking.id),
        },
        idempotency_key=f"instrument-job:{job.id}:queued",
    )
    await db_session.commit()
    return {**action.as_dict(), "instrument_job": instrument_job_snapshot(job)}


async def _user_job_context(
    db_session: DBSession,
    current_user: User,
    job_id: UUID,
    *,
    lock: bool,
) -> tuple[
    ResearchInstrumentJob, ResearchAction, ResearchRun, ResearchTask, Project, Lab
]:
    statement = select(ResearchInstrumentJob).where(ResearchInstrumentJob.id == job_id)
    if lock:
        statement = statement.with_for_update()
    job = (await db_session.scalars(statement)).first()
    action = await db_session.get(ResearchAction, job.action_id) if job else None
    run = await db_session.get(ResearchRun, action.run_id) if action else None
    task = await db_session.get(ResearchTask, run.task_id) if run else None
    if job is None or action is None or run is None or task is None:
        raise HTTPException(status_code=404, detail="Instrument Job not found")
    project = await _project(db_session, task.project_id)
    await require_research_capability(
        db_session, user=current_user, project=project, capability="research.run"
    )
    lab = await db_session.get(Lab, task.lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    return job, action, run, task, project, lab


def _stop_command(
    job: ResearchInstrumentJob, params: InstrumentStopDraft
) -> dict[str, Any]:
    return {
        "operation": "stop_instrument_job",
        "instrument_job_id": str(job.id),
        "expected_revision": params.expected_revision,
        "reason": params.reason,
    }


@router.post("/research-instrument-jobs/{job_id}/stop/preview")
async def preview_stop_instrument_job(
    job_id: UUID,
    params: InstrumentStopDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    job, action, run, task, project, lab = await _user_job_context(
        db_session, current_user, job_id, lock=False
    )
    if job.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Instrument Job changed")
    if job.status in FINAL_JOB_STATUSES:
        raise HTTPException(status_code=409, detail="Instrument Job is already final")
    command = _stop_command(job, params)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": _destination(task=task, project=project, lab=lab, run=run),
        "action": {"id": str(action.id), "title": action.title},
        "effects": [
            "Pause the Research Task for safety review",
            (
                "Cancel the queued job before delivery"
                if job.status == ResearchInstrumentJobStatus.QUEUED.value
                else "Request an on-device stop and wait for Gateway acknowledgement"
            ),
        ],
    }


@router.post("/research-instrument-jobs/{job_id}/stop")
async def stop_instrument_job(
    job_id: UUID,
    params: InstrumentStop,
    current_user: CurrentUser,
    db_session: DBSession,
):
    job, action, run, task, _project_context, _lab = await _user_job_context(
        db_session, current_user, job_id, lock=True
    )
    if job.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Instrument Job changed")
    if job.status in FINAL_JOB_STATUSES:
        raise HTTPException(status_code=409, detail="Instrument Job is already final")
    command = _stop_command(job, params)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="Stop preview changed")
    now = utcnow()
    previous_status = job.status
    job.stop_reason = params.reason
    job.stop_requested_at = now
    job.revision += 1
    if previous_status == ResearchInstrumentJobStatus.QUEUED.value:
        job.status = ResearchInstrumentJobStatus.CANCELLED.value
        job.completed_at = now
        action.status = ResearchActionStatus.CANCELLED.value
        action.completed_at = now
    else:
        job.status = ResearchInstrumentJobStatus.STOP_REQUESTED.value
        action.status = ResearchActionStatus.WAITING.value
    action.error = f"Stop requested: {params.reason}"
    action.revision += 1
    run.status = ResearchRunStatus.PAUSED.value
    run.last_error = "Instrument stop requested; inspect the equipment before resuming."
    task.status = ResearchTaskStatus.PAUSED.value
    task.revision += 1
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="instrument_job.stop_requested",
        actor_user_id=current_user.id,
        payload={
            "instrument_job_id": str(job.id),
            "previous_status": previous_status,
            "reason": params.reason,
        },
        idempotency_key=f"instrument-job:{job.id}:stop:{job.revision}",
    )
    if action.status == ResearchActionStatus.CANCELLED.value:
        await hold_or_release_aira_action_group(
            db_session,
            task=task,
            run=run,
            action=action,
        )
    await mark_control_session_stopping(
        db_session,
        job=job,
        task=task,
        run=run,
        reason=params.reason,
        stopped=previous_status == ResearchInstrumentJobStatus.QUEUED.value,
    )
    await db_session.commit()
    return {**action.as_dict(), "instrument_job": instrument_job_snapshot(job)}


async def _authenticate_gateway(
    db_session: DBSession,
    token: str,
) -> ResearchInstrumentGateway:
    if not token or not token.startswith("aigw_"):
        raise HTTPException(
            status_code=401, detail="Invalid Instrument Gateway credential"
        )
    digest = gateway_token_digest(token)
    gateway = await ResearchInstrumentGateway.find_by(
        db_session,
        [
            ResearchInstrumentGateway.token_digest == digest,
            ResearchInstrumentGateway.revoked_at.is_(None),
        ],
    )
    if gateway is None or not hmac.compare_digest(gateway.token_digest, digest):
        raise HTTPException(
            status_code=401, detail="Invalid Instrument Gateway credential"
        )
    gateway.last_seen_at = utcnow()
    return gateway


async def _gateway_job_context(
    db_session: DBSession,
    *,
    gateway: ResearchInstrumentGateway,
    job_id: UUID,
    lease_token: str,
    lock: bool = True,
) -> tuple[ResearchInstrumentJob, ResearchAction, ResearchRun, ResearchTask]:
    statement = select(ResearchInstrumentJob).where(
        ResearchInstrumentJob.id == job_id,
        ResearchInstrumentJob.gateway_id == gateway.id,
    )
    if lock:
        statement = statement.with_for_update()
    job = (await db_session.scalars(statement)).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Instrument Job not found")
    provided_digest = job_lease_token_digest(lease_token)
    if job.lease_token_digest is None or not hmac.compare_digest(
        job.lease_token_digest, provided_digest
    ):
        raise HTTPException(status_code=401, detail="Invalid Instrument Job lease")
    action = await db_session.get(ResearchAction, job.action_id)
    run = await db_session.get(ResearchRun, action.run_id) if action else None
    task = await db_session.get(ResearchTask, run.task_id) if run else None
    if action is None or run is None or task is None:
        raise HTTPException(status_code=409, detail="Instrument Job context is missing")
    return job, action, run, task


async def _pause_for_instrument_failure(
    *,
    db_session: DBSession,
    job: ResearchInstrumentJob,
    action: ResearchAction,
    run: ResearchRun,
    task: ResearchTask,
    error: str,
) -> None:
    now = utcnow()
    job.status = ResearchInstrumentJobStatus.FAILED.value
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
        await hold_or_release_aira_action_group(
            db_session,
            task=task,
            run=run,
            action=action,
        )
    await mark_control_session_failed(
        db_session,
        job=job,
        task=task,
        run=run,
        error=error,
    )


@gateway_router.post("/jobs/lease")
async def lease_instrument_job(
    gateway_token: GatewayToken,
    db_session: DBSession,
):
    gateway = await _authenticate_gateway(db_session, gateway_token)
    if not gateway.enabled:
        raise HTTPException(status_code=403, detail="Instrument Gateway is disabled")
    now = utcnow()
    active_jobs = list(
        (
            await db_session.scalars(
                select(ResearchInstrumentJob)
                .where(
                    ResearchInstrumentJob.gateway_id == gateway.id,
                    ResearchInstrumentJob.status.in_(
                        {
                            ResearchInstrumentJobStatus.LEASED.value,
                            ResearchInstrumentJobStatus.RUNNING.value,
                            ResearchInstrumentJobStatus.STOP_REQUESTED.value,
                        }
                    ),
                )
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    for active in active_jobs:
        if (
            active.status == ResearchInstrumentJobStatus.LEASED.value
            and active.started_at is None
            and active.lease_expires_at is not None
            and active.lease_expires_at <= now
        ):
            active.status = ResearchInstrumentJobStatus.QUEUED.value
            active.lease_token_digest = None
            active.lease_expires_at = None
            active.revision += 1
            continue
        await db_session.commit()
        return {"job": None, "retry_after_seconds": 10}

    job = (
        await db_session.scalars(
            select(ResearchInstrumentJob)
            .join(
                ResearchAction,
                ResearchAction.id == ResearchInstrumentJob.action_id,
            )
            .join(
                EquipmentBooking,
                EquipmentBooking.id == ResearchInstrumentJob.equipment_booking_id,
            )
            .where(
                ResearchInstrumentJob.gateway_id == gateway.id,
                ResearchInstrumentJob.status
                == ResearchInstrumentJobStatus.QUEUED.value,
                ResearchAction.status == ResearchActionStatus.QUEUED.value,
                EquipmentBooking.status == BookingStatus.APPROVED.value,
                EquipmentBooking.starts_at <= now,
                EquipmentBooking.ends_at > now,
            )
            .order_by(ResearchInstrumentJob.created_at, ResearchInstrumentJob.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
    ).first()
    if job is None:
        await db_session.commit()
        return {"job": None, "retry_after_seconds": 15}
    action = await db_session.get(ResearchAction, job.action_id)
    run = await db_session.get(ResearchRun, action.run_id) if action else None
    task = await db_session.get(ResearchTask, run.task_id) if run else None
    command = await db_session.get(ResearchInstrumentCommand, job.command_id)
    resource = await db_session.get(Resource, job.resource_id)
    booking = await db_session.get(EquipmentBooking, job.equipment_booking_id)
    control_session = (
        await db_session.get(ResearchInstrumentControlSession, job.control_session_id)
        if job.control_session_id is not None
        else None
    )
    invalid_reason = None
    if action is None or run is None or task is None or booking is None:
        invalid_reason = "Instrument Job context is missing"
    elif command is None or not command.enabled or command.archived_at is not None:
        invalid_reason = "Instrument command is disabled"
    elif resource is None or resource.current_revision_id != job.resource_revision_id:
        invalid_reason = "Equipment revision changed before delivery"
    elif job.control_session_id is not None and control_session is None:
        invalid_reason = "Instrument Control Session is missing"
    elif control_session is not None and control_session.status not in {
        ResearchInstrumentControlStatus.QUEUED.value,
        ResearchInstrumentControlStatus.RUNNING.value,
    }:
        invalid_reason = "Instrument Control Session is not executable"
    if task is not None and task.status != ResearchTaskStatus.ACTIVE.value:
        await db_session.commit()
        return {"job": None, "retry_after_seconds": 15}
    if invalid_reason is not None:
        if action is not None and run is not None and task is not None:
            await _pause_for_instrument_failure(
                db_session=db_session,
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
                kind="instrument_job.failed",
                actor_user_id=None,
                payload={"instrument_job_id": str(job.id), "error": invalid_reason},
                idempotency_key=f"instrument-job:{job.id}:failed:{job.revision}",
            )
        await db_session.commit()
        return {"job": None, "retry_after_seconds": 15}

    if (
        control_session is not None
        and control_session.started_at is not None
        and now
        >= control_session.started_at
        + timedelta(seconds=control_session.max_duration_seconds)
    ):
        await pause_control_session_before_start(
            db_session,
            job=job,
            action=action,
            task=task,
            run=run,
            reason="Instrument Control duration limit reached before step delivery",
        )
        await db_session.commit()
        return {"job": None, "retry_after_seconds": 15}

    lease_token = generate_job_lease_token()
    expires_at = now + timedelta(seconds=LEASE_SECONDS)
    job.status = ResearchInstrumentJobStatus.LEASED.value
    job.lease_token_digest = job_lease_token_digest(lease_token)
    job.lease_expires_at = expires_at
    job.leased_at = now
    job.heartbeat_at = now
    job.attempt_count += 1
    job.revision += 1
    envelope = {
        "schema": "airalogy.instrument-job.v1",
        "job_id": str(job.id),
        "action_id": str(action.id),
        "task_id": str(task.id),
        "run_id": str(run.id),
        "issued_at": now.isoformat(),
        "lease_expires_at": expires_at.isoformat(),
        "resource": {
            "id": str(job.resource_id),
            "revision_id": str(job.resource_revision_id),
            "revision": job.resource_revision,
        },
        "booking": {
            "id": str(booking.id),
            "starts_at": booking.starts_at.isoformat(),
            "ends_at": booking.ends_at.isoformat(),
        },
        "command": {
            "key": job.command_key,
            "version": job.command_version,
            "revision": job.command_revision,
            "arguments": job.arguments,
            "input_schema": job.input_schema,
            "output_schema": job.output_schema,
            "risk": job.risk,
            "device_confirmation_required": job.device_confirmation_required,
            "safety_contract": job.safety_contract,
            "timeout_seconds": job.timeout_seconds,
        },
    }
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="instrument_job.leased",
        actor_user_id=None,
        payload={
            "instrument_job_id": str(job.id),
            "gateway_id": str(gateway.id),
            "lease_expires_at": expires_at.isoformat(),
            "attempt": job.attempt_count,
        },
        idempotency_key=f"instrument-job:{job.id}:leased:{job.attempt_count}",
    )
    await db_session.commit()
    return {
        "job": envelope,
        "signature": sign_job_envelope(envelope, gateway.token_digest),
        "lease_token": lease_token,
    }


def _ensure_live_lease(job: ResearchInstrumentJob) -> None:
    if job.lease_expires_at is None or job.lease_expires_at <= utcnow():
        raise HTTPException(status_code=409, detail="Instrument Job lease expired")


@gateway_router.post("/jobs/{job_id}/start")
async def start_instrument_job(
    job_id: UUID,
    params: GatewayStart,
    gateway_token: GatewayToken,
    lease_token: LeaseToken,
    db_session: DBSession,
):
    gateway = await _authenticate_gateway(db_session, gateway_token)
    job, action, run, task = await _gateway_job_context(
        db_session,
        gateway=gateway,
        job_id=job_id,
        lease_token=lease_token,
    )
    if job.status != ResearchInstrumentJobStatus.LEASED.value:
        raise HTTPException(status_code=409, detail="Instrument Job cannot be started")
    if (
        task.status != ResearchTaskStatus.ACTIVE.value
        or run.status != ResearchRunStatus.WAITING_FOR_INSTRUMENT.value
        or action.status != ResearchActionStatus.QUEUED.value
    ):
        raise HTTPException(status_code=409, detail="Research Run is not ready")
    _ensure_live_lease(job)
    booking = await db_session.get(EquipmentBooking, job.equipment_booking_id)
    resource = await db_session.get(Resource, job.resource_id)
    now = utcnow()
    if resource is None or resource.current_revision_id != job.resource_revision_id:
        error = "Equipment revision changed after delivery"
        await _pause_for_instrument_failure(
            db_session=db_session,
            job=job,
            action=action,
            run=run,
            task=task,
            error=error,
        )
        await emit_research_event(
            db_session,
            task_id=task.id,
            run_id=run.id,
            action_id=action.id,
            kind="instrument_job.failed",
            actor_user_id=None,
            payload={"instrument_job_id": str(job.id), "error": error},
            idempotency_key=f"instrument-job:{job.id}:failed:{job.revision}",
        )
        await db_session.commit()
        raise HTTPException(status_code=409, detail=error)
    if (
        booking is None
        or booking.status != BookingStatus.APPROVED.value
        or not (booking.starts_at <= now < booking.ends_at)
    ):
        raise HTTPException(status_code=409, detail="Equipment booking is not active")
    if job.device_confirmation_required and (
        not params.device_confirmed or not params.confirmation_reference
    ):
        raise HTTPException(
            status_code=409,
            detail="Device-side confirmation and reference are required",
        )
    try:
        safety_attestation = validate_safety_attestation(
            job.safety_contract, params.safety_attestation
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    job.status = ResearchInstrumentJobStatus.RUNNING.value
    job.device_confirmation = {
        "confirmed": params.device_confirmed,
        "reference": params.confirmation_reference,
        "confirmed_at": now.isoformat() if params.device_confirmed else None,
    }
    job.safety_attestation = {
        **safety_attestation,
        "attested_at": now.isoformat(),
    }
    job.started_at = now
    job.heartbeat_at = now
    job.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    job.revision += 1
    action.status = ResearchActionStatus.RUNNING.value
    action.started_at = now
    action.revision += 1
    try:
        await mark_control_session_running(db_session, job=job)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="instrument_job.started",
        actor_user_id=None,
        payload={
            "instrument_job_id": str(job.id),
            "device_confirmed": params.device_confirmed,
            "confirmation_reference": params.confirmation_reference,
            "safety_attestation": job.safety_attestation,
        },
        idempotency_key=f"instrument-job:{job.id}:started",
    )
    await db_session.commit()
    return {"status": job.status, "lease_expires_at": job.lease_expires_at}


@gateway_router.post("/jobs/{job_id}/heartbeat")
async def heartbeat_instrument_job(
    job_id: UUID,
    gateway_token: GatewayToken,
    lease_token: LeaseToken,
    db_session: DBSession,
):
    gateway = await _authenticate_gateway(db_session, gateway_token)
    job, action, run, task = await _gateway_job_context(
        db_session,
        gateway=gateway,
        job_id=job_id,
        lease_token=lease_token,
    )
    if job.status == ResearchInstrumentJobStatus.STOP_REQUESTED.value:
        await db_session.commit()
        return {
            "status": job.status,
            "stop_requested": True,
            "reason": job.stop_reason,
        }
    if job.status not in {
        ResearchInstrumentJobStatus.LEASED.value,
        ResearchInstrumentJobStatus.RUNNING.value,
    }:
        raise HTTPException(status_code=409, detail="Instrument Job is not active")
    now = utcnow()
    if (
        job.status == ResearchInstrumentJobStatus.LEASED.value
        and job.lease_expires_at is not None
        and job.lease_expires_at <= now
    ):
        raise HTTPException(status_code=409, detail="Instrument Job lease expired")
    booking = await db_session.get(EquipmentBooking, job.equipment_booking_id)
    control_session = (
        await db_session.get(ResearchInstrumentControlSession, job.control_session_id)
        if job.control_session_id is not None
        else None
    )
    timed_out = bool(
        job.started_at
        and now >= job.started_at + timedelta(seconds=job.timeout_seconds)
    )
    control_timed_out = bool(
        control_session
        and control_session.started_at
        and now
        >= control_session.started_at
        + timedelta(seconds=control_session.max_duration_seconds)
    )
    booking_ended = booking is None or now >= booking.ends_at
    lease_expired_while_running = bool(
        job.status == ResearchInstrumentJobStatus.RUNNING.value
        and job.lease_expires_at
        and job.lease_expires_at <= now
    )
    if timed_out or control_timed_out or booking_ended or lease_expired_while_running:
        reason = (
            "Instrument Job timeout reached"
            if timed_out
            else (
                "Instrument Control duration limit reached"
                if control_timed_out
                else (
                    "Equipment booking window ended"
                    if booking_ended
                    else "Instrument Job heartbeat lease expired"
                )
            )
        )
        job.status = ResearchInstrumentJobStatus.STOP_REQUESTED.value
        job.stop_reason = reason
        job.stop_requested_at = now
        job.revision += 1
        action.status = ResearchActionStatus.WAITING.value
        action.error = reason
        action.revision += 1
        run.status = ResearchRunStatus.PAUSED.value
        run.last_error = f"{reason}; inspect the equipment before resuming."
        task.status = ResearchTaskStatus.PAUSED.value
        task.revision += 1
        await emit_research_event(
            db_session,
            task_id=task.id,
            run_id=run.id,
            action_id=action.id,
            kind="instrument_job.stop_requested",
            actor_user_id=None,
            payload={"instrument_job_id": str(job.id), "reason": reason},
            idempotency_key=f"instrument-job:{job.id}:auto-stop:{job.revision}",
        )
        await mark_control_session_stopping(
            db_session,
            job=job,
            task=task,
            run=run,
            reason=reason,
            stopped=False,
        )
        await db_session.commit()
        return {"status": job.status, "stop_requested": True, "reason": reason}
    job.heartbeat_at = now
    job.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    job.revision += 1
    await db_session.commit()
    return {
        "status": job.status,
        "stop_requested": False,
        "lease_expires_at": job.lease_expires_at,
    }


@gateway_router.post("/jobs/{job_id}/complete")
async def complete_instrument_job(
    job_id: UUID,
    params: GatewayComplete,
    gateway_token: GatewayToken,
    lease_token: LeaseToken,
    db_session: DBSession,
):
    gateway = await _authenticate_gateway(db_session, gateway_token)
    job, action, run, task = await _gateway_job_context(
        db_session,
        gateway=gateway,
        job_id=job_id,
        lease_token=lease_token,
    )
    if job.status == ResearchInstrumentJobStatus.COMPLETED.value:
        if job.result != params.result:
            raise HTTPException(
                status_code=409,
                detail="Instrument Job was already completed with a different result",
            )
        await db_session.commit()
        return {"status": job.status}
    if job.status != ResearchInstrumentJobStatus.RUNNING.value:
        raise HTTPException(status_code=409, detail="Instrument Job is not running")
    _ensure_live_lease(job)
    if task.status == ResearchTaskStatus.CANCELLED.value:
        raise HTTPException(status_code=409, detail="Research Task was cancelled")
    try:
        validate_schema_payload(job.output_schema, params.result, "command result")
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    now = utcnow()
    job.status = ResearchInstrumentJobStatus.COMPLETED.value
    job.result = params.result
    job.error = None
    job.completed_at = now
    job.lease_expires_at = None
    job.revision += 1
    action.status = ResearchActionStatus.COMPLETED.value
    action.output_data = {
        "command_key": job.command_key,
        "command_version": job.command_version,
        "resource_id": str(job.resource_id),
        "equipment_booking_id": str(job.equipment_booking_id),
        "result": params.result,
    }
    action.error = None
    action.completed_at = now
    action.revision += 1
    append_aira_result(
        run,
        "instrument_results",
        {
            "action_id": str(action.id),
            "command_key": job.command_key,
            "command_version": job.command_version,
            "resource_id": str(job.resource_id),
            "result": params.result,
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
        kind="instrument_job.completed",
        actor_user_id=None,
        payload={
            "instrument_job_id": str(job.id),
            "command_key": job.command_key,
            "resource_id": str(job.resource_id),
        },
        idempotency_key=f"instrument-job:{job.id}:completed",
    )
    try:
        control_progress = await advance_control_session_after_job(
            db_session,
            job=job,
            task=task,
            run=run,
        )
    except ValueError as error:
        await mark_control_session_failed(
            db_session,
            job=job,
            task=task,
            run=run,
            error=str(error),
        )
        run.status = ResearchRunStatus.PAUSED.value
        run.last_error = str(error)
        task.status = ResearchTaskStatus.PAUSED.value
        task.revision += 1
        control_progress = {"handled": True, "terminal": False}
    graph_settled = False
    if not control_progress["handled"] or control_progress["terminal"]:
        graph_settled = await hold_or_release_aira_action_group(
            db_session,
            task=task,
            run=run,
            action=action,
        )
    if (
        graph_settled
        and task.status == ResearchTaskStatus.ACTIVE.value
        and config.effective_ai_enabled
    ):
        await enqueue_research_advance(db_session, task=task, run=run)
    elif graph_settled and task.status == ResearchTaskStatus.ACTIVE.value:
        run.last_error = "AI is disabled; continue this Research Task manually."
        await emit_research_event(
            db_session,
            task_id=task.id,
            run_id=run.id,
            action_id=action.id,
            kind="run.manual_control_required",
            actor_user_id=None,
            payload={"reason": "ai_disabled"},
            idempotency_key=f"run:{run.id}:manual:instrument-job:{job.id}",
        )
    await db_session.commit()
    return {"status": job.status}


@gateway_router.post("/jobs/{job_id}/fail")
async def fail_instrument_job(
    job_id: UUID,
    params: GatewayFail,
    gateway_token: GatewayToken,
    lease_token: LeaseToken,
    db_session: DBSession,
):
    gateway = await _authenticate_gateway(db_session, gateway_token)
    job, action, run, task = await _gateway_job_context(
        db_session,
        gateway=gateway,
        job_id=job_id,
        lease_token=lease_token,
    )
    if job.status == ResearchInstrumentJobStatus.FAILED.value:
        if job.error != params.error:
            raise HTTPException(
                status_code=409,
                detail="Instrument Job was already failed with a different reason",
            )
        await db_session.commit()
        return {"status": job.status}
    if job.status not in {
        ResearchInstrumentJobStatus.LEASED.value,
        ResearchInstrumentJobStatus.RUNNING.value,
        ResearchInstrumentJobStatus.STOP_REQUESTED.value,
    }:
        raise HTTPException(status_code=409, detail="Instrument Job is not active")
    await _pause_for_instrument_failure(
        db_session=db_session,
        job=job,
        action=action,
        run=run,
        task=task,
        error=params.error,
    )
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="instrument_job.failed",
        actor_user_id=None,
        payload={"instrument_job_id": str(job.id), "error": params.error},
        idempotency_key=f"instrument-job:{job.id}:failed:{job.revision}",
    )
    await db_session.commit()
    return {"status": job.status}


@gateway_router.post("/jobs/{job_id}/stopped")
async def acknowledge_instrument_job_stopped(
    job_id: UUID,
    params: GatewayStopped,
    gateway_token: GatewayToken,
    lease_token: LeaseToken,
    db_session: DBSession,
):
    gateway = await _authenticate_gateway(db_session, gateway_token)
    job, action, run, task = await _gateway_job_context(
        db_session,
        gateway=gateway,
        job_id=job_id,
        lease_token=lease_token,
    )
    if job.status == ResearchInstrumentJobStatus.STOPPED.value:
        if params.reason and job.stop_reason != params.reason:
            raise HTTPException(
                status_code=409,
                detail="Instrument Job was already stopped with a different reason",
            )
        await db_session.commit()
        return {"status": job.status}
    if job.status not in {
        ResearchInstrumentJobStatus.RUNNING.value,
        ResearchInstrumentJobStatus.STOP_REQUESTED.value,
    }:
        raise HTTPException(
            status_code=409,
            detail="Instrument Job cannot acknowledge a safe stop",
        )
    now = utcnow()
    job.status = ResearchInstrumentJobStatus.STOPPED.value
    job.completed_at = now
    job.lease_expires_at = None
    job.stop_reason = params.reason or job.stop_reason
    job.revision += 1
    action.status = ResearchActionStatus.CANCELLED.value
    action.error = f"Instrument stopped: {job.stop_reason or 'acknowledged by Gateway'}"
    action.completed_at = now
    action.revision += 1
    if task.status != ResearchTaskStatus.CANCELLED.value:
        run.status = ResearchRunStatus.PAUSED.value
        run.last_error = "Instrument stopped; inspect the equipment before resuming."
        task.status = ResearchTaskStatus.PAUSED.value
        task.revision += 1
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="instrument_job.stopped",
        actor_user_id=None,
        payload={"instrument_job_id": str(job.id), "reason": job.stop_reason},
        idempotency_key=f"instrument-job:{job.id}:stopped",
    )
    await hold_or_release_aira_action_group(
        db_session,
        task=task,
        run=run,
        action=action,
    )
    await mark_control_session_stopping(
        db_session,
        job=job,
        task=task,
        run=run,
        reason=job.stop_reason or "Acknowledged by Instrument Gateway",
        stopped=True,
    )
    await db_session.commit()
    return {"status": job.status}
