"""Deterministic orchestration for bounded Instrument Control Sessions."""

from __future__ import annotations

import json
import math
import re
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import (
    ResearchAction,
    ResearchActionKind,
    ResearchActionStatus,
    ResearchRun,
    ResearchRunStatus,
    ResearchTask,
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
    ResourceStatus,
)
from app.services.access_control import resolve_resource_access
from app.services.research_executor_bindings import (
    enforce_environment_binding_action_limit,
)
from app.services.research_instruments import (
    ACTIVE_INSTRUMENT_JOB_STATUSES,
    command_snapshot,
    normalized_safety_contract,
    resolve_instrument_executor_binding,
    validate_schema_payload,
)
from app.services.research_runtime import canonical_digest, emit_research_event, utcnow

STEP_KEY_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
RESULT_PATH_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_-]*(\.[A-Za-z_][A-Za-z0-9_-]*){0,7}$"
)
TERMINAL_TARGETS = {"complete", "pause"}
CONDITION_OPERATORS = {"eq", "ne", "lt", "lte", "gt", "gte", "in", "exists"}


def instrument_control_snapshot(
    session: ResearchInstrumentControlSession,
    *,
    jobs: list[ResearchInstrumentJob] | None = None,
) -> dict[str, Any]:
    data = session.as_dict()
    if jobs is not None:
        data["jobs"] = [job.as_dict() for job in jobs]
    return data


def validate_control_structure(program: dict[str, Any]) -> dict[str, Any]:
    """Validate a pinned state machine without executing user supplied code."""

    if not isinstance(program, dict):
        raise TypeError("Instrument Control program must be an object")
    allowed = {
        "schema",
        "mode",
        "entry_step_key",
        "max_steps",
        "max_duration_seconds",
        "steps",
    }
    unknown = set(program) - allowed
    if unknown:
        raise ValueError(
            f"Unsupported Instrument Control fields: {', '.join(sorted(unknown))}"
        )
    if program.get("schema") != "airalogy.instrument-control.v1":
        raise ValueError("Unsupported Instrument Control schema")
    mode = program.get("mode")
    if mode not in {"bounded_sequence", "feedback_loop"}:
        raise ValueError("Unsupported Instrument Control mode")
    max_steps = program.get("max_steps")
    max_duration = program.get("max_duration_seconds")
    if (
        isinstance(max_steps, bool)
        or not isinstance(max_steps, int)
        or not 1 <= max_steps <= 50
    ):
        raise ValueError("Instrument Control max_steps must be between 1 and 50")
    if (
        isinstance(max_duration, bool)
        or not isinstance(max_duration, int)
        or not 1 <= max_duration <= 86_400
    ):
        raise ValueError(
            "Instrument Control max_duration_seconds must be between 1 and 86400"
        )
    steps = program.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 20:
        raise ValueError("Instrument Control requires between 1 and 20 step templates")
    keys: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            raise TypeError("Instrument Control steps must be objects")
        if set(step) != {"key", "command", "arguments", "transition"}:
            raise ValueError("Instrument Control step fields are invalid")
        key = step.get("key")
        if not isinstance(key, str) or not STEP_KEY_RE.fullmatch(key):
            raise ValueError("Instrument Control step key is invalid")
        if key in keys:
            raise ValueError("Instrument Control step keys must be unique")
        keys.append(key)
        if not isinstance(step.get("command"), dict):
            raise TypeError("Instrument Control command pin is missing")
        if not isinstance(step.get("arguments"), dict):
            raise TypeError("Instrument Control arguments must be an object")
        _validate_transition(step.get("transition"), mode=mode)
    entry = program.get("entry_step_key")
    if entry not in keys:
        raise ValueError("Instrument Control entry step does not exist")
    for step in steps:
        transition = step["transition"]
        targets = [transition["on_true"]]
        if transition.get("condition") is not None:
            targets.append(transition["on_false"])
        for target in targets:
            if target not in TERMINAL_TARGETS and target not in keys:
                raise ValueError(f"Instrument Control target {target!r} does not exist")
    if _reachable_keys(program) != set(keys):
        raise ValueError("Instrument Control cannot contain unreachable steps")
    if mode == "bounded_sequence":
        _validate_acyclic_sequence(program)
        if max_steps < len(steps):
            raise ValueError("A bounded sequence must allow every declared step")
    return program


def _validate_transition(value: Any, *, mode: str) -> None:
    if not isinstance(value, dict):
        raise TypeError("Instrument Control transition must be an object")
    allowed = {"condition", "on_true", "on_false"}
    if set(value) - allowed:
        raise ValueError("Instrument Control transition fields are invalid")
    condition = value.get("condition")
    on_true = value.get("on_true")
    if not isinstance(on_true, str) or not on_true:
        raise ValueError("Instrument Control transition requires on_true")
    if condition is None:
        if value.get("on_false") not in {None, ""}:
            raise ValueError("Unconditional transitions cannot define on_false")
        return
    if mode != "feedback_loop":
        raise ValueError("Only feedback loops can branch on a result")
    if not isinstance(condition, dict) or set(condition) != {
        "path",
        "operator",
        "value",
    }:
        raise ValueError("Instrument Control condition fields are invalid")
    path = condition.get("path")
    operator = condition.get("operator")
    if not isinstance(path, str) or not RESULT_PATH_RE.fullmatch(path):
        raise ValueError("Instrument Control result path is invalid")
    if operator not in CONDITION_OPERATORS:
        raise ValueError("Instrument Control condition operator is invalid")
    if not isinstance(value.get("on_false"), str) or not value["on_false"]:
        raise ValueError("Conditional transitions require on_false")
    if operator == "exists" and not isinstance(condition.get("value"), bool):
        raise ValueError("The exists operator requires a boolean value")
    if operator == "in" and not isinstance(condition.get("value"), list):
        raise ValueError("The in operator requires an array value")
    _validate_condition_value(condition.get("value"), operator=operator)


def _validate_condition_value(value: Any, *, operator: str) -> None:
    scalar = (str, int, float, bool, type(None))
    if operator == "in":
        if len(value) > 50 or any(not isinstance(item, scalar) for item in value):
            raise ValueError("The in operator supports at most 50 scalar values")
        values = value
    else:
        if not isinstance(value, scalar):
            raise ValueError("Instrument Control comparisons require a scalar value")
        values = [value]
    if any(isinstance(item, float) and not math.isfinite(item) for item in values):
        raise ValueError("Instrument Control comparison numbers must be finite")
    if len(json.dumps(value, ensure_ascii=False, separators=(",", ":"))) > 4_096:
        raise ValueError("Instrument Control comparison value is too large")


def _validate_acyclic_sequence(program: dict[str, Any]) -> None:
    steps = {step["key"]: step for step in program["steps"]}
    visited: set[str] = set()
    active: set[str] = set()

    def visit(key: str) -> None:
        if key in active:
            raise ValueError("A bounded sequence cannot contain a cycle")
        if key in visited:
            return
        active.add(key)
        target = steps[key]["transition"]["on_true"]
        if target not in TERMINAL_TARGETS:
            visit(target)
        active.remove(key)
        visited.add(key)

    visit(program["entry_step_key"])


def _reachable_keys(program: dict[str, Any]) -> set[str]:
    steps = {step["key"]: step for step in program["steps"]}
    reached: set[str] = set()
    pending = [program["entry_step_key"]]
    while pending:
        key = pending.pop()
        if key in reached:
            continue
        reached.add(key)
        transition = steps[key]["transition"]
        targets = [transition["on_true"]]
        if transition.get("condition") is not None:
            targets.append(transition["on_false"])
        pending.extend(target for target in targets if target not in TERMINAL_TARGETS)
    return reached


def control_program_step(program: dict[str, Any], step_key: str) -> dict[str, Any]:
    for step in program.get("steps") or []:
        if step.get("key") == step_key:
            return step
    raise ValueError("Instrument Control step no longer exists")


def evaluate_control_transition(step: dict[str, Any], result: dict[str, Any]) -> str:
    transition = step["transition"]
    condition = transition.get("condition")
    if condition is None:
        return transition["on_true"]
    exists, actual = _result_path(result, condition["path"])
    operator = condition["operator"]
    expected = condition["value"]
    if operator == "exists":
        matched = exists is expected
    elif not exists:
        matched = False
    elif operator == "eq":
        matched = actual == expected
    elif operator == "ne":
        matched = actual != expected
    elif operator == "in":
        matched = actual in expected
    else:
        if (
            isinstance(actual, bool)
            or isinstance(expected, bool)
            or not isinstance(actual, (int, float))
            or not isinstance(expected, (int, float))
        ):
            raise ValueError("Ordered Instrument Control comparisons require numbers")
        matched = {
            "lt": actual < expected,
            "lte": actual <= expected,
            "gt": actual > expected,
            "gte": actual >= expected,
        }[operator]
    return transition["on_true"] if matched else transition["on_false"]


def _result_path(result: dict[str, Any], path: str) -> tuple[bool, Any]:
    current: Any = result
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def control_command_pin(command: ResearchInstrumentCommand) -> dict[str, Any]:
    snapshot = command_snapshot(command)
    return {
        key: snapshot[key]
        for key in (
            "id",
            "gateway_id",
            "lab_id",
            "resource_id",
            "resource_revision_id",
            "resource_revision",
            "command_key",
            "command_version",
            "name",
            "description",
            "input_schema",
            "output_schema",
            "risk",
            "device_confirmation_required",
            "safety_contract",
            "timeout_seconds",
            "revision",
        )
    }


async def queue_control_step(
    db_session: AsyncSession,
    *,
    session: ResearchInstrumentControlSession,
    task: ResearchTask,
    run: ResearchRun,
    step_key: str,
    actor_user_id: UUID | None,
) -> tuple[ResearchAction, ResearchInstrumentJob]:
    """Revalidate one exact step and expose it through the normal Gateway queue."""

    step = control_program_step(session.program, step_key)
    pinned = step["command"]
    command = await db_session.get(ResearchInstrumentCommand, UUID(pinned["id"]))
    gateway = await db_session.get(ResearchInstrumentGateway, session.gateway_id)
    resource = await db_session.get(Resource, session.resource_id)
    booking = await db_session.get(EquipmentBooking, session.equipment_booking_id)
    if command is None or gateway is None or resource is None or booking is None:
        raise ValueError(
            "Instrument Control command, Gateway, device, or booking is missing"
        )
    if not command.enabled or command.archived_at is not None:
        raise ValueError("Instrument Control command is disabled")
    if not gateway.enabled or gateway.revoked_at is not None:
        raise ValueError("Instrument Control Gateway is disabled")
    if (
        resource.archived_at is not None
        or resource.status != ResourceStatus.ACTIVE.value
        or resource.current_revision_id != command.resource_revision_id
    ):
        raise ValueError("Instrument Control equipment revision changed")
    if booking.status != BookingStatus.APPROVED.value or booking.ends_at <= utcnow():
        raise ValueError("Instrument Control booking is no longer approved and active")
    if (
        booking.resource_id != resource.id
        or booking.user_id != session.created_by_user_id
    ):
        raise ValueError("Instrument Control booking ownership changed")
    pinned_command = {key: pinned.get(key) for key in control_command_pin(command)}
    if not same_json(control_command_pin(command), pinned_command):
        raise ValueError("Instrument Control command changed after confirmation")
    access = await resolve_resource_access(
        db_session,
        session.created_by_user_id,
        task.lab_id,
        resource_type_id=resource.resource_type_id,
        resource_id=resource.id,
    )
    if not access.allows("equipment.book"):
        raise ValueError("Instrument Control execution access was revoked")
    current_binding = await resolve_instrument_executor_binding(
        db_session,
        task=task,
        command=command,
        gateway=gateway,
        resource=resource,
    )
    if not same_json(current_binding, pinned.get("executor_binding") or {}):
        raise ValueError("Instrument Executor Binding changed after confirmation")
    await enforce_environment_binding_action_limit(
        db_session, run=run, binding=current_binding
    )
    validate_schema_payload(command.input_schema, step["arguments"], "command input")
    active = await db_session.scalar(
        select(func.count())
        .select_from(ResearchInstrumentJob)
        .where(
            ResearchInstrumentJob.equipment_booking_id == booking.id,
            ResearchInstrumentJob.status.in_(ACTIVE_INSTRUMENT_JOB_STATUSES),
        )
    )
    if active:
        raise ValueError("This equipment booking already has an active Instrument Job")
    execution_index = session.issued_steps + 1
    action_sequence = (
        await db_session.scalar(
            select(func.max(ResearchAction.sequence)).where(
                ResearchAction.run_id == run.id
            )
        )
        or 0
    ) + 1
    binding = current_binding
    action_payload = {
        "control_session_id": str(session.id),
        "control_execution_index": execution_index,
        "control_step_key": step_key,
        "command_id": pinned["id"],
        "command_revision": pinned["revision"],
        "arguments": step["arguments"],
        "program_digest": session.program_digest,
    }
    action = ResearchAction(
        run_id=run.id,
        sequence=action_sequence,
        plan_version=run.plan_version,
        kind=ResearchActionKind.INSTRUMENT_JOB.value,
        status=ResearchActionStatus.QUEUED.value,
        title=f"{session.title} · {pinned['name']}",
        description=session.description,
        executor_type=binding.get("executor_type", "instrument_gateway"),
        input_data={
            **action_payload,
            "resource_id": str(resource.id),
            "equipment_booking_id": str(booking.id),
            "source": "instrument_control",
            "resume_run": True,
        },
        requirements={
            "risk": pinned["risk"],
            "device_confirmation_required": pinned["device_confirmation_required"],
            "safety_contract": normalized_safety_contract(pinned["safety_contract"]),
            "input_schema": pinned["input_schema"],
            "output_schema": pinned["output_schema"],
            "control_mode": session.mode,
            "control_max_steps": session.max_steps,
            "executor_binding": binding,
        },
        policy_decision="allow",
        policy_reason="Human-confirmed bounded Instrument Control Session",
        preview_digest=canonical_digest(action_payload),
        idempotency_key=f"instrument-control:{session.id}:{execution_index}",
    )
    db_session.add(action)
    await db_session.flush()
    job = ResearchInstrumentJob(
        action_id=action.id,
        gateway_id=command.gateway_id,
        command_id=command.id,
        resource_id=command.resource_id,
        resource_revision_id=command.resource_revision_id,
        resource_revision=command.resource_revision,
        equipment_booking_id=booking.id,
        control_session_id=session.id,
        control_step_key=step_key,
        control_execution_index=execution_index,
        command_key=command.command_key,
        command_version=command.command_version,
        command_revision=command.revision,
        arguments=step["arguments"],
        input_schema=command.input_schema,
        output_schema=command.output_schema,
        risk=command.risk,
        device_confirmation_required=command.device_confirmation_required,
        safety_contract=normalized_safety_contract(command.safety_contract),
        timeout_seconds=command.timeout_seconds,
        status=ResearchInstrumentJobStatus.QUEUED.value,
    )
    db_session.add(job)
    session.current_step_key = step_key
    session.issued_steps = execution_index
    session.pending_step_key = None
    session.pause_reason = ""
    session.status = (
        ResearchInstrumentControlStatus.QUEUED.value
        if session.executed_steps == 0
        else ResearchInstrumentControlStatus.RUNNING.value
    )
    session.revision += 1
    run.status = ResearchRunStatus.WAITING_FOR_INSTRUMENT.value
    run.last_error = None
    run.advance_generation += 1
    await db_session.flush()
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="instrument_control.step_queued",
        actor_user_id=actor_user_id,
        payload={
            "control_session_id": str(session.id),
            "instrument_job_id": str(job.id),
            "step_key": step_key,
            "execution_index": execution_index,
            "program_digest": session.program_digest,
        },
        idempotency_key=f"instrument-control:{session.id}:step:{execution_index}:queued",
    )
    return action, job


async def mark_control_session_running(
    db_session: AsyncSession,
    *,
    job: ResearchInstrumentJob,
) -> None:
    if job.control_session_id is None:
        return
    session = await db_session.get(
        ResearchInstrumentControlSession, job.control_session_id
    )
    if session is None:
        raise ValueError("Instrument Control Session is missing")
    if session.status not in {
        ResearchInstrumentControlStatus.QUEUED.value,
        ResearchInstrumentControlStatus.RUNNING.value,
    }:
        raise ValueError("Instrument Control Session is not executable")
    if session.started_at is not None and utcnow() >= session.started_at + timedelta(
        seconds=session.max_duration_seconds
    ):
        raise ValueError("Instrument Control duration limit was reached")
    session.status = ResearchInstrumentControlStatus.RUNNING.value
    session.started_at = session.started_at or utcnow()
    session.revision += 1


async def pause_control_session_before_start(
    db_session: AsyncSession,
    *,
    job: ResearchInstrumentJob,
    action: ResearchAction,
    task: ResearchTask,
    run: ResearchRun,
    reason: str,
) -> None:
    """Withdraw an unstarted step and retain it as a reviewable pending step."""

    if job.control_session_id is None:
        raise ValueError("Instrument Job is not part of a Control Session")
    session = await db_session.get(
        ResearchInstrumentControlSession, job.control_session_id
    )
    if session is None:
        raise ValueError("Instrument Control Session is missing")
    now = utcnow()
    job.status = ResearchInstrumentJobStatus.CANCELLED.value
    job.error = reason
    job.completed_at = now
    job.lease_token_digest = None
    job.lease_expires_at = None
    job.revision += 1
    action.status = ResearchActionStatus.CANCELLED.value
    action.error = reason
    action.completed_at = now
    action.revision += 1
    session.current_step_key = job.control_step_key
    session.status = ResearchInstrumentControlStatus.PAUSED_FOR_REVIEW.value
    session.pending_step_key = job.control_step_key
    session.pause_reason = reason
    session.revision += 1
    run.status = ResearchRunStatus.WAITING_FOR_INSTRUMENT.value
    run.last_error = reason
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="instrument_control.paused_for_review",
        actor_user_id=None,
        payload={
            "control_session_id": str(session.id),
            "pending_step_key": job.control_step_key,
            "reason": reason,
        },
        idempotency_key=(
            f"instrument-control:{session.id}:before-start:{job.control_execution_index}"
        ),
    )


async def advance_control_session_after_job(
    db_session: AsyncSession,
    *,
    job: ResearchInstrumentJob,
    task: ResearchTask,
    run: ResearchRun,
) -> dict[str, Any]:
    if job.control_session_id is None:
        return {"handled": False, "terminal": True}
    session = (
        await db_session.scalars(
            select(ResearchInstrumentControlSession)
            .where(ResearchInstrumentControlSession.id == job.control_session_id)
            .with_for_update()
        )
    ).first()
    if session is None:
        raise ValueError("Instrument Control Session is missing")
    if session.status in {
        ResearchInstrumentControlStatus.COMPLETED.value,
        ResearchInstrumentControlStatus.FAILED.value,
        ResearchInstrumentControlStatus.CANCELLED.value,
        ResearchInstrumentControlStatus.STOPPED.value,
    }:
        return {"handled": True, "terminal": True, "status": session.status}
    if job.control_execution_index != session.issued_steps:
        raise ValueError("Instrument Control execution order is inconsistent")
    session.executed_steps += 1
    session.current_step_key = job.control_step_key
    session.revision += 1
    step = control_program_step(session.program, job.control_step_key or "")
    try:
        target = evaluate_control_transition(step, job.result)
    except ValueError as error:
        return await _pause_control_session(
            db_session,
            session=session,
            task=task,
            run=run,
            reason=f"Feedback evaluation requires review: {error}",
            pending_step_key=None,
            actor_user_id=None,
        )
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=job.action_id,
        kind="instrument_control.transition_evaluated",
        actor_user_id=None,
        payload={
            "control_session_id": str(session.id),
            "step_key": job.control_step_key,
            "execution_index": job.control_execution_index,
            "target": target,
        },
        idempotency_key=(
            f"instrument-control:{session.id}:transition:{job.control_execution_index}"
        ),
    )
    if target == "complete":
        session.status = ResearchInstrumentControlStatus.COMPLETED.value
        session.pending_step_key = None
        session.pause_reason = ""
        session.completed_at = utcnow()
        session.revision += 1
        run.status = ResearchRunStatus.RUNNING.value
        run.last_error = None
        await emit_research_event(
            db_session,
            task_id=task.id,
            run_id=run.id,
            action_id=job.action_id,
            kind="instrument_control.completed",
            actor_user_id=None,
            payload={
                "control_session_id": str(session.id),
                "executed_steps": session.executed_steps,
                "program_digest": session.program_digest,
            },
            idempotency_key=f"instrument-control:{session.id}:completed",
        )
        return {"handled": True, "terminal": True, "status": session.status}
    if target == "pause":
        return await _pause_control_session(
            db_session,
            session=session,
            task=task,
            run=run,
            reason="The confirmed control program requested a human checkpoint.",
            pending_step_key=None,
            actor_user_id=None,
        )
    if session.executed_steps >= session.max_steps:
        return await _pause_control_session(
            db_session,
            session=session,
            task=task,
            run=run,
            reason="The confirmed maximum number of control steps was reached.",
            pending_step_key=target,
            actor_user_id=None,
        )
    deadline = (session.started_at or session.created_at) + timedelta(
        seconds=session.max_duration_seconds
    )
    if utcnow() >= deadline:
        return await _pause_control_session(
            db_session,
            session=session,
            task=task,
            run=run,
            reason="The confirmed Instrument Control duration limit was reached.",
            pending_step_key=target,
            actor_user_id=None,
        )
    next_step = control_program_step(session.program, target)
    if next_step["command"].get("risk") == "high":
        return await _pause_control_session(
            db_session,
            session=session,
            task=task,
            run=run,
            reason="A high-risk Instrument command requires a fresh human checkpoint.",
            pending_step_key=target,
            actor_user_id=None,
        )
    try:
        await queue_control_step(
            db_session,
            session=session,
            task=task,
            run=run,
            step_key=target,
            actor_user_id=None,
        )
    except ValueError as error:
        return await _pause_control_session(
            db_session,
            session=session,
            task=task,
            run=run,
            reason=f"The next Instrument Control step requires review: {error}",
            pending_step_key=target,
            actor_user_id=None,
        )
    return {"handled": True, "terminal": False, "status": session.status}


async def _pause_control_session(
    db_session: AsyncSession,
    *,
    session: ResearchInstrumentControlSession,
    task: ResearchTask,
    run: ResearchRun,
    reason: str,
    pending_step_key: str | None,
    actor_user_id: UUID | None,
) -> dict[str, Any]:
    session.status = ResearchInstrumentControlStatus.PAUSED_FOR_REVIEW.value
    session.pending_step_key = pending_step_key
    session.pause_reason = reason
    session.revision += 1
    run.status = ResearchRunStatus.WAITING_FOR_INSTRUMENT.value
    run.last_error = reason
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=None,
        kind="instrument_control.paused_for_review",
        actor_user_id=actor_user_id,
        payload={
            "control_session_id": str(session.id),
            "pending_step_key": pending_step_key,
            "reason": reason,
        },
        idempotency_key=f"instrument-control:{session.id}:paused:{session.revision}",
    )
    return {"handled": True, "terminal": False, "status": session.status}


async def mark_control_session_failed(
    db_session: AsyncSession,
    *,
    job: ResearchInstrumentJob,
    task: ResearchTask,
    run: ResearchRun,
    error: str,
) -> None:
    if job.control_session_id is None:
        return
    session = await db_session.get(
        ResearchInstrumentControlSession, job.control_session_id
    )
    if session is None:
        return
    session.status = ResearchInstrumentControlStatus.FAILED.value
    session.error = error
    session.completed_at = utcnow()
    session.revision += 1
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=job.action_id,
        kind="instrument_control.failed",
        actor_user_id=None,
        payload={"control_session_id": str(session.id), "error": error},
        idempotency_key=f"instrument-control:{session.id}:failed",
    )


async def mark_control_session_stopping(
    db_session: AsyncSession,
    *,
    job: ResearchInstrumentJob,
    task: ResearchTask,
    run: ResearchRun,
    reason: str,
    stopped: bool,
) -> None:
    if job.control_session_id is None:
        return
    session = await db_session.get(
        ResearchInstrumentControlSession, job.control_session_id
    )
    if session is None:
        return
    session.status = (
        ResearchInstrumentControlStatus.STOPPED.value
        if stopped
        else ResearchInstrumentControlStatus.STOP_REQUESTED.value
    )
    session.stop_reason = reason
    session.completed_at = utcnow() if stopped else None
    session.revision += 1
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=job.action_id,
        kind=(
            "instrument_control.stopped"
            if stopped
            else "instrument_control.stop_requested"
        ),
        actor_user_id=None,
        payload={"control_session_id": str(session.id), "reason": reason},
        idempotency_key=(
            f"instrument-control:{session.id}:"
            f"{'stopped' if stopped else 'stop-requested'}"
        ),
    )


def same_json(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True, default=str) == json.dumps(
        right, sort_keys=True, default=str
    )
