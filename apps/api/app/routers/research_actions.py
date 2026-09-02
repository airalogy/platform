"""Digital Tool Job and asynchronous Wait Event Research Actions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from jsonschema import Draft202012Validator, SchemaError
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
    ResearchToolJob,
    ResearchToolJobStatus,
    ResearchWaitEvent,
    ResearchWaitEventStatus,
)
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.research_budget import reached_operational_limit
from app.services.research_capabilities import pinned_tool_definition
from app.services.research_runtime import (
    activate_tool_action,
    activate_wait_event_action,
    canonical_digest,
    create_plan_version,
    emit_research_event,
    enqueue_research_advance,
    require_research_capability,
    utcnow,
)
from app.services.research_tools import (
    research_tool_catalog,
    validate_tool_arguments,
)

router = APIRouter(tags=["research-actions"])


class ToolActionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_key: str = Field(min_length=1, max_length=128)
    arguments: dict[str, Any] = Field(default_factory=dict)
    title: str = Field(default="", max_length=255)
    description: str = Field(default="", max_length=20_000)
    idempotency_key: str = Field(min_length=8, max_length=160)

    @model_validator(mode="after")
    def normalize(self):
        self.tool_key = self.tool_key.strip()
        self.title = self.title.strip()
        self.description = self.description.strip()
        self.idempotency_key = self.idempotency_key.strip()
        return self


class ToolActionCreate(ToolActionDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class WaitEventDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=20_000)
    event_key: str = Field(min_length=8, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")
    expected_event_type: str = Field(min_length=1, max_length=128)
    payload_schema: dict[str, Any] = Field(default_factory=dict)
    due_at: datetime | None = None
    idempotency_key: str = Field(min_length=8, max_length=160)

    @model_validator(mode="after")
    def normalize(self):
        self.title = self.title.strip()
        self.description = self.description.strip()
        self.event_key = self.event_key.strip()
        self.expected_event_type = self.expected_event_type.strip()
        self.idempotency_key = self.idempotency_key.strip()
        try:
            Draft202012Validator.check_schema(self.payload_schema)
        except SchemaError as error:
            raise ValueError(
                f"Invalid event payload Schema: {error.message}"
            ) from error
        if self.due_at is not None and self.due_at.tzinfo is None:
            self.due_at = self.due_at.replace(tzinfo=UTC)
        if self.due_at is not None and self.due_at <= utcnow():
            raise ValueError("Wait Event due time must be in the future")
        return self


class WaitEventCreate(WaitEventDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class WaitEventSignalDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    event_type: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)


class WaitEventSignal(WaitEventSignalDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


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


async def _next_sequence(db_session: DBSession, run_id: UUID) -> int:
    return (
        await db_session.scalar(
            select(func.max(ResearchAction.sequence)).where(
                ResearchAction.run_id == run_id
            )
        )
        or 0
    ) + 1


def _tool_command(
    *,
    task: ResearchTask,
    run: ResearchRun,
    params: ToolActionDraft,
) -> dict[str, Any]:
    definition = pinned_tool_definition(run.environment_snapshot or {}, params.tool_key)
    validate_tool_arguments(definition, params.arguments)
    return {
        "task_id": str(task.id),
        "task_revision": task.revision,
        "run_id": str(run.id),
        "run_plan_version": run.plan_version,
        "tool_key": definition.key,
        "tool_version": definition.version,
        "arguments": params.arguments,
        "title": params.title or definition.name,
        "description": params.description,
        "idempotency_key": params.idempotency_key,
    }


def _wait_command(
    *,
    task: ResearchTask,
    run: ResearchRun,
    params: WaitEventDraft,
) -> dict[str, Any]:
    return {
        "task_id": str(task.id),
        "task_revision": task.revision,
        "run_id": str(run.id),
        "run_plan_version": run.plan_version,
        "title": params.title,
        "description": params.description,
        "event_key": params.event_key,
        "expected_event_type": params.expected_event_type,
        "payload_schema": params.payload_schema,
        "due_at": params.due_at.isoformat() if params.due_at else None,
        "idempotency_key": params.idempotency_key,
    }


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


def _digital_action_payload(
    action: ResearchAction,
    *,
    tool_job: ResearchToolJob | None = None,
    wait_event: ResearchWaitEvent | None = None,
) -> dict[str, Any]:
    return {
        **action.as_dict(),
        "tool_job": tool_job.as_dict() if tool_job else None,
        "wait_event": wait_event.as_dict() if wait_event else None,
    }


@router.get("/research-tools")
async def list_research_tools(
    current_user: CurrentUser,
    db_session: DBSession,
    task_id: UUID | None = None,
):
    # Authentication is intentional even though definitions are instance-wide:
    # availability can reveal private deployment integrations.
    if task_id is None:
        return {
            "tools": [item.payload() for item in research_tool_catalog().values()]
        }
    _task, _project, _lab, run = await _active_task_context(
        db_session, current_user, task_id, capability="research.read"
    )
    catalog = research_tool_catalog()
    tools = []
    for pinned in list((run.environment_snapshot or {}).get("tools") or []):
        definition = catalog.get(str(pinned.get("key") or ""))
        if definition is None:
            tools.append(
                {
                    **pinned,
                    "available": False,
                    "unavailable_reason": "Pinned Research Tool is no longer registered",
                }
            )
            continue
        payload = definition.payload()
        if definition.version != str(pinned.get("version") or ""):
            payload["available"] = False
            payload["unavailable_reason"] = (
                "Pinned Research Tool version is unavailable"
            )
        tools.append(payload)
    return {"tools": tools}


@router.post("/research-tasks/{task_id}/tool-actions/preview")
async def preview_tool_action(
    task_id: UUID,
    params: ToolActionDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, project, lab, run = await _active_task_context(
        db_session, current_user, task_id, enforce_limits=True
    )
    try:
        command = _tool_command(task=task, run=run, params=params)
        definition = pinned_tool_definition(
            run.environment_snapshot or {}, params.tool_key
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": _destination(task=task, project=project, lab=lab, run=run),
        "tool": definition.payload(),
        "effects": [
            "Create a version-pinned Tool Job Action",
            "Execute it through the retryable Platform job worker",
            "Persist output and provenance without importing formal Knowledge automatically",
        ],
    }


@router.post("/research-tasks/{task_id}/tool-actions")
async def create_tool_action(
    task_id: UUID,
    params: ToolActionCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, _project, _lab, run = await _active_task_context(
        db_session, current_user, task_id, enforce_limits=True
    )
    try:
        command = _tool_command(task=task, run=run, params=params)
        definition = pinned_tool_definition(
            run.environment_snapshot or {}, params.tool_key
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    digest = canonical_digest(command)
    if digest != params.preview_digest:
        raise HTTPException(status_code=409, detail="Tool Action preview has changed")
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
            or existing.kind != ResearchActionKind.TOOL_JOB.value
        ):
            raise HTTPException(
                status_code=409, detail="Action idempotency key is already in use"
            )
        existing_job = await ResearchToolJob.find_by(
            db_session, [ResearchToolJob.action_id == existing.id]
        )
        if existing_job is None:
            raise HTTPException(status_code=409, detail="Tool Action is incomplete")
        return _digital_action_payload(existing, tool_job=existing_job)

    await create_plan_version(
        db_session,
        task=task,
        run=run,
        kind="manual",
        plan={"action": command, "previous_plan_version": run.plan_version},
        summary=f"Run {definition.name}",
    )
    action = ResearchAction(
        run_id=run.id,
        sequence=await _next_sequence(db_session, run.id),
        plan_version=run.plan_version,
        kind=ResearchActionKind.TOOL_JOB.value,
        status=ResearchActionStatus.PROPOSED.value,
        title=command["title"],
        description=command["description"],
        executor_type=definition.executor_type,
        input_data={
            "tool_key": definition.key,
            "tool_version": definition.version,
            "arguments": params.arguments,
            "source": "manual",
            "resume_run": True,
        },
        requirements={"risk": definition.risk, "read_only": True},
        policy_decision="allow",
        preview_digest=digest,
        idempotency_key=params.idempotency_key,
    )
    db_session.add(action)
    await db_session.flush()
    tool_job = ResearchToolJob(
        action_id=action.id,
        tool_key=definition.key,
        tool_version=definition.version,
        arguments=params.arguments,
        status=ResearchToolJobStatus.QUEUED.value,
    )
    db_session.add(tool_job)
    await db_session.flush()
    # Supersede any in-flight planner job before introducing a new boundary.
    run.advance_generation += 1
    await activate_tool_action(
        db_session,
        task=task,
        run=run,
        action=action,
        actor_user_id=current_user.id,
    )
    await db_session.commit()
    return _digital_action_payload(action, tool_job=tool_job)


@router.post("/research-tasks/{task_id}/wait-actions/preview")
async def preview_wait_action(
    task_id: UUID,
    params: WaitEventDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, project, lab, run = await _active_task_context(
        db_session, current_user, task_id, enforce_limits=True
    )
    command = _wait_command(task=task, run=run, params=params)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": _destination(task=task, project=project, lab=lab, run=run),
        "effects": [
            "Create a typed Wait Event Action",
            "Pause this Run at an explicit external boundary",
            "Resume only after a schema-valid, confirmed signal",
        ],
    }


@router.post("/research-tasks/{task_id}/wait-actions")
async def create_wait_action(
    task_id: UUID,
    params: WaitEventCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, _project, _lab, run = await _active_task_context(
        db_session, current_user, task_id, enforce_limits=True
    )
    command = _wait_command(task=task, run=run, params=params)
    digest = canonical_digest(command)
    if digest != params.preview_digest:
        raise HTTPException(status_code=409, detail="Wait Event preview has changed")
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
            or existing.kind != ResearchActionKind.WAIT_EVENT.value
        ):
            raise HTTPException(
                status_code=409, detail="Action idempotency key is already in use"
            )
        existing_wait = await ResearchWaitEvent.find_by(
            db_session, [ResearchWaitEvent.action_id == existing.id]
        )
        if existing_wait is None:
            raise HTTPException(
                status_code=409, detail="Wait Event Action is incomplete"
            )
        return _digital_action_payload(existing, wait_event=existing_wait)
    event_key_in_use = await ResearchWaitEvent.exists(
        db_session, [ResearchWaitEvent.event_key == params.event_key]
    )
    if event_key_in_use:
        raise HTTPException(status_code=409, detail="Wait Event key is already in use")
    active_wait = await db_session.scalar(
        select(func.count())
        .select_from(ResearchWaitEvent)
        .join(ResearchAction, ResearchAction.id == ResearchWaitEvent.action_id)
        .where(
            ResearchAction.run_id == run.id,
            ResearchWaitEvent.status == ResearchWaitEventStatus.WAITING.value,
        )
    )
    if active_wait:
        raise HTTPException(
            status_code=409,
            detail="This Research Run is already waiting for an external event",
        )

    await create_plan_version(
        db_session,
        task=task,
        run=run,
        kind="manual",
        plan={"action": command, "previous_plan_version": run.plan_version},
        summary=f"Wait for {params.expected_event_type}",
    )
    action = ResearchAction(
        run_id=run.id,
        sequence=await _next_sequence(db_session, run.id),
        plan_version=run.plan_version,
        kind=ResearchActionKind.WAIT_EVENT.value,
        status=ResearchActionStatus.PROPOSED.value,
        title=params.title,
        description=params.description,
        executor_type="external_event",
        input_data={
            "event_key": params.event_key,
            "expected_event_type": params.expected_event_type,
            "source": "manual",
        },
        requirements={"payload_schema": params.payload_schema},
        policy_decision="allow",
        preview_digest=digest,
        idempotency_key=params.idempotency_key,
        due_at=params.due_at,
    )
    db_session.add(action)
    await db_session.flush()
    wait_event = ResearchWaitEvent(
        action_id=action.id,
        event_key=params.event_key,
        expected_event_type=params.expected_event_type,
        payload_schema=params.payload_schema,
        status=ResearchWaitEventStatus.WAITING.value,
        due_at=params.due_at,
    )
    db_session.add(wait_event)
    await db_session.flush()
    # Supersede any in-flight planner job before introducing a new boundary.
    run.advance_generation += 1
    await activate_wait_event_action(
        db_session,
        task=task,
        run=run,
        action=action,
        actor_user_id=current_user.id,
    )
    await db_session.commit()
    return _digital_action_payload(action, wait_event=wait_event)


async def _wait_event_context(
    db_session: DBSession,
    current_user: User,
    wait_event_id: UUID,
) -> tuple[ResearchWaitEvent, ResearchAction, ResearchRun, ResearchTask, Project, Lab]:
    wait_event = await db_session.get(ResearchWaitEvent, wait_event_id)
    if wait_event is None:
        raise HTTPException(status_code=404, detail="Wait Event not found")
    action = await db_session.get(ResearchAction, wait_event.action_id)
    run = await db_session.get(ResearchRun, action.run_id) if action else None
    task = await db_session.get(ResearchTask, run.task_id) if run else None
    if action is None or run is None or task is None:
        raise HTTPException(status_code=404, detail="Wait Event context not found")
    if task.status in {
        ResearchTaskStatus.COMPLETED.value,
        ResearchTaskStatus.CANCELLED.value,
        ResearchTaskStatus.ARCHIVED.value,
    } or action.status != ResearchActionStatus.WAITING.value:
        raise HTTPException(status_code=409, detail="Wait Event can no longer be received")
    project = await _project(db_session, task.project_id)
    await require_research_capability(
        db_session, user=current_user, project=project, capability="research.run"
    )
    lab = await db_session.get(Lab, task.lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    return wait_event, action, run, task, project, lab


def _signal_command(
    wait_event: ResearchWaitEvent,
    params: WaitEventSignalDraft,
) -> dict[str, Any]:
    return {
        "wait_event_id": str(wait_event.id),
        "event_key": wait_event.event_key,
        "expected_revision": params.expected_revision,
        "event_type": params.event_type.strip(),
        "payload": params.payload,
    }


def _validate_wait_signal(
    wait_event: ResearchWaitEvent,
    params: WaitEventSignalDraft,
) -> None:
    if wait_event.status != ResearchWaitEventStatus.WAITING.value:
        raise HTTPException(status_code=409, detail="Wait Event is already final")
    if wait_event.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Wait Event has changed")
    if params.event_type.strip() != wait_event.expected_event_type:
        raise HTTPException(status_code=422, detail="Unexpected event type")
    issues = sorted(
        Draft202012Validator(wait_event.payload_schema).iter_errors(params.payload),
        key=lambda item: list(item.absolute_path),
    )
    if issues:
        issue = issues[0]
        path = ".".join(str(item) for item in issue.absolute_path)
        raise HTTPException(
            status_code=422,
            detail=f"Invalid event payload{f' at {path}' if path else ''}: {issue.message}",
        )


@router.post("/research-wait-events/{wait_event_id}/signal/preview")
async def preview_wait_event_signal(
    wait_event_id: UUID,
    params: WaitEventSignalDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    wait_event, action, run, task, project, lab = await _wait_event_context(
        db_session, current_user, wait_event_id
    )
    _validate_wait_signal(wait_event, params)
    command = _signal_command(wait_event, params)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": _destination(task=task, project=project, lab=lab, run=run),
        "action": {"id": str(action.id), "title": action.title},
        "effect": "Complete this Wait Event and resume the Research Run",
    }


@router.post("/research-wait-events/{wait_event_id}/signal")
async def signal_wait_event(
    wait_event_id: UUID,
    params: WaitEventSignal,
    current_user: CurrentUser,
    db_session: DBSession,
):
    wait_event, action, run, task, _project_context, _lab = await _wait_event_context(
        db_session, current_user, wait_event_id
    )
    _validate_wait_signal(wait_event, params)
    command = _signal_command(wait_event, params)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(
            status_code=409, detail="Wait Event signal preview has changed"
        )
    now = utcnow()
    wait_event.status = ResearchWaitEventStatus.RECEIVED.value
    wait_event.received_payload = params.payload
    wait_event.received_at = now
    wait_event.received_by_user_id = current_user.id
    wait_event.revision += 1
    action.status = ResearchActionStatus.COMPLETED.value
    action.output_data = {
        "event_type": params.event_type,
        "payload": params.payload,
        "received_at": now.isoformat(),
    }
    action.completed_at = now
    action.revision += 1
    previous_results = list((run.aira_state or {}).get("event_results") or [])
    run.aira_state = {
        **(run.aira_state or {}),
        "event_results": [
            *previous_results[-49:],
            {
                "action_id": str(action.id),
                "event_key": wait_event.event_key,
                "event_type": params.event_type,
                "payload": params.payload,
                "received_at": now.isoformat(),
            },
        ],
    }
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
        kind="wait_event.received",
        actor_user_id=current_user.id,
        payload={"event_type": params.event_type, "event_key": wait_event.event_key},
        idempotency_key=f"wait-event:{wait_event.id}:received",
    )
    if task.status == ResearchTaskStatus.ACTIVE.value and config.effective_ai_enabled:
        await enqueue_research_advance(db_session, task=task, run=run)
    elif task.status == ResearchTaskStatus.ACTIVE.value:
        run.last_error = "AI is disabled; continue this Research Task manually."
        await emit_research_event(
            db_session,
            task_id=task.id,
            run_id=run.id,
            action_id=action.id,
            kind="run.manual_control_required",
            actor_user_id=None,
            payload={"reason": "ai_disabled"},
            idempotency_key=f"run:{run.id}:manual:wait-event:{wait_event.id}",
        )
    await db_session.commit()
    return _digital_action_payload(action, wait_event=wait_event)
