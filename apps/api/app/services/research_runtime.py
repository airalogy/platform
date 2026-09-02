"""Durable orchestration services for Research Tasks and AIRA runs."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.libs.masterbrain import aira_workflow_step
from app.models.lab import Lab, LabRole, LabUser
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.research import (
    HumanWorkItemStatus,
    ResearchAction,
    ResearchActionKind,
    ResearchActionStatus,
    ResearchArtifactLink,
    ResearchEvent,
    ResearchHumanWorkItem,
    ResearchPlanVersion,
    ResearchProtocolRun,
    ResearchRun,
    ResearchRunStatus,
    ResearchTask,
    ResearchTaskOutcome,
    ResearchTaskProtocol,
    ResearchTaskStatus,
)
from app.models.user import User
from app.services.access_control import resolve_structured_access
from app.services.model_usage import create_usage_context
from app.services.persistent_jobs import enqueue_job


AIRA_AI_STATUSES = {
    "waiting_for_research_strategy",
    "waiting_for_next_protocol",
    "waiting_for_initial_values_for_fields_in_next_protocol",
    "waiting_for_phased_research_conclusion",
    "waiting_for_final_research_conclusion",
}

EXPECTED_AIRA_STEPS = {
    "waiting_for_research_strategy": "add_research_strategy",
    "waiting_for_next_protocol": "add_next_protocol",
    "waiting_for_initial_values_for_fields_in_next_protocol": (
        "add_initial_values_for_fields_in_next_protocol"
    ),
    "waiting_for_phased_research_conclusion": "add_phased_research_conclusion",
    "waiting_for_final_research_conclusion": "add_final_research_conclusion",
}

TERMINAL_RUN_STATUSES = {
    ResearchRunStatus.COMPLETED.value,
    ResearchRunStatus.FAILED.value,
    ResearchRunStatus.CANCELLED.value,
}

ACTIVE_WORK_ITEM_STATUSES = {
    HumanWorkItemStatus.OPEN.value,
    HumanWorkItemStatus.IN_PROGRESS.value,
    HumanWorkItemStatus.CHANGES_REQUESTED.value,
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def canonical_digest(value: Any) -> str:
    payload = json.dumps(
        jsonable_encoder(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def research_task_command(
    *,
    project_id: UUID,
    title: str,
    goal: str,
    success_criteria: list[str],
    stop_conditions: list[str],
    autonomy_level: str,
    protocol_ids: list[UUID],
    owner_user_id: UUID,
    ai_model: str | None,
) -> dict[str, Any]:
    return {
        "project_id": str(project_id),
        "title": title.strip(),
        "goal": goal.strip(),
        "success_criteria": [item.strip() for item in success_criteria if item.strip()],
        "stop_conditions": [item.strip() for item in stop_conditions if item.strip()],
        "autonomy_level": autonomy_level,
        "protocol_ids": [str(item) for item in protocol_ids],
        "owner_user_id": str(owner_user_id),
        "ai_model": ai_model.strip() if ai_model else None,
    }


async def require_research_capability(
    db_session: AsyncSession,
    *,
    user: User,
    project: Project,
    capability: str,
) -> None:
    """Require real project membership and an API-side research capability.

    Public project visibility is intentionally insufficient: unpublished Tasks,
    work items, Records, and conclusions remain member-only.
    """

    membership = await LabUser.find_by(
        db_session,
        [LabUser.lab_id == project.lab_id, LabUser.user_id == user.id],
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="Research Task access denied")
    if membership.role <= LabRole.MANAGER:
        return

    decision = await resolve_structured_access(
        db_session,
        user.id,
        project.lab_id,
        project,
        include_legacy=True,
    )
    if not decision.allows(capability):
        raise HTTPException(status_code=403, detail="Research Task access denied")


async def task_protocol_rows(
    db_session: AsyncSession,
    task_id: UUID,
) -> list[tuple[ResearchTaskProtocol, Protocol, ProtocolVersion]]:
    return list(
        (
            await db_session.execute(
                select(ResearchTaskProtocol, Protocol, ProtocolVersion)
                .join(Protocol, Protocol.id == ResearchTaskProtocol.protocol_id)
                .join(
                    ProtocolVersion,
                    ProtocolVersion.id == ResearchTaskProtocol.protocol_version_id,
                )
                .where(ResearchTaskProtocol.task_id == task_id)
                .order_by(ResearchTaskProtocol.position)
            )
        ).all()
    )


def workflow_info_for_task(
    task: ResearchTask,
    project: Project,
    lab: Lab,
    rows: list[tuple[ResearchTaskProtocol, Protocol, ProtocolVersion]],
) -> dict[str, Any]:
    protocols: list[dict[str, Any]] = []
    for task_protocol, protocol, version in rows:
        protocols.append(
            {
                "protocol_index": task_protocol.position,
                "protocol_name": protocol.name,
                "airalogy_protocol_id": (
                    f"airalogy.id.lab.{lab.uid}.project.{project.uid}.protocol."
                    f"{protocol.uid}.v.{version.version}"
                ),
            }
        )
    return {
        "id": str(task.id),
        "title": task.title,
        "protocols": protocols,
        "edges": [
            f"{index} -> {index + 1}" for index in range(1, len(protocols))
        ],
        "logic": "\n".join(
            [
                *(f"Success: {item}" for item in task.success_criteria),
                *(f"Stop: {item}" for item in task.stop_conditions),
            ]
        ),
        "default_initial_protocol_index": protocols[0]["protocol_index"]
        if protocols
        else None,
        "default_research_goal": task.goal,
        "default_research_strategy": None,
    }


def protocol_info_for_task(
    project: Project,
    lab: Lab,
    rows: list[tuple[ResearchTaskProtocol, Protocol, ProtocolVersion]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for _task_protocol, protocol, version in rows:
        schema = version.json_schema or {}
        field_schema = schema.get("vars") or schema.get("research_variable") or schema
        assigners = version.assigners or None
        assigner = (
            json.dumps(assigners, ensure_ascii=False)
            if isinstance(assigners, dict) and assigners
            else assigners
            if isinstance(assigners, str)
            else None
        )
        result.append(
            {
                "airalogy_protocol_id": (
                    f"airalogy.id.lab.{lab.uid}.project.{project.uid}.protocol."
                    f"{protocol.uid}.v.{version.version}"
                ),
                "markdown": version.aimd or "",
                "model": None,
                "assigner": assigner,
                "field_json_schema": field_schema,
            }
        )
    return result


def initial_aira_state(goal: str) -> dict[str, Any]:
    return {
        "path_status": "waiting_for_research_strategy",
        "researchable": False,
        "final_research_conclusion": "",
        "steps": [
            {
                "step": "add_research_goal",
                "path_index": 0,
                "mode": "user",
                "data": {"thought": "", "goal": goal},
            }
        ],
    }


def path_status_after_step(current_status: str, step: dict[str, Any]) -> str:
    data = step.get("data") or {}
    if current_status == "waiting_for_research_strategy":
        return (
            "waiting_for_next_protocol"
            if data.get("researchable", True)
            else "waiting_for_final_research_conclusion"
        )
    if current_status == "waiting_for_next_protocol":
        return (
            "waiting_for_final_research_conclusion"
            if data.get("end_path")
            else "waiting_for_initial_values_for_fields_in_next_protocol"
        )
    if current_status == "waiting_for_initial_values_for_fields_in_next_protocol":
        return "waiting_for_record"
    if current_status == "waiting_for_phased_research_conclusion":
        return "waiting_for_next_protocol"
    if current_status == "waiting_for_final_research_conclusion":
        return "completed"
    return current_status


async def emit_research_event(
    db_session: AsyncSession,
    *,
    task_id: UUID,
    kind: str,
    actor_user_id: UUID | None,
    run_id: UUID | None = None,
    action_id: UUID | None = None,
    work_item_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> ResearchEvent:
    if idempotency_key:
        existing = await ResearchEvent.find_by(
            db_session,
            [ResearchEvent.idempotency_key == idempotency_key],
        )
        if existing is not None:
            return existing
    event = ResearchEvent(
        task_id=task_id,
        run_id=run_id,
        action_id=action_id,
        work_item_id=work_item_id,
        kind=kind,
        actor_user_id=actor_user_id,
        payload=payload or {},
        idempotency_key=idempotency_key,
    )
    db_session.add(event)
    await db_session.flush()
    return event


async def enqueue_research_advance(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
) -> None:
    run.advance_generation += 1
    await db_session.flush()
    await enqueue_job(
        db_session,
        kind="research_run_advance",
        lab_id=task.lab_id,
        payload={
            "task_id": str(task.id),
            "run_id": str(run.id),
            "generation": run.advance_generation,
        },
        idempotency_key=(
            f"research-run:{run.id}:advance:{run.advance_generation}"
        ),
        max_attempts=5,
    )


async def create_plan_version(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
    kind: str,
    plan: dict[str, Any],
    summary: str,
) -> ResearchPlanVersion:
    run.plan_version += 1
    item = ResearchPlanVersion(
        run_id=run.id,
        version=run.plan_version,
        kind=kind,
        plan=plan,
        digest=canonical_digest(plan),
        summary=summary,
        created_by_user_id=run.requested_by_user_id,
    )
    db_session.add(item)
    await db_session.flush()
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        kind="plan.version_created",
        actor_user_id=None if kind == "aira" else run.requested_by_user_id,
        payload={"version": item.version, "kind": kind, "digest": item.digest},
        idempotency_key=f"run:{run.id}:plan:{item.version}",
    )
    return item


async def _load_run_context(
    db_session: AsyncSession,
    run_id: UUID,
) -> tuple[
    ResearchRun,
    ResearchTask,
    Project,
    Lab,
    list[tuple[ResearchTaskProtocol, Protocol, ProtocolVersion]],
]:
    run = await db_session.get(ResearchRun, run_id)
    if run is None:
        raise ValueError("Research Run was not found")
    task = await db_session.get(ResearchTask, run.task_id)
    if task is None:
        raise ValueError("Research Task was not found")
    project = await db_session.get(Project, task.project_id)
    lab = await db_session.get(Lab, task.lab_id)
    if project is None or lab is None:
        raise ValueError("Research Task context was not found")
    rows = await task_protocol_rows(db_session, task.id)
    return run, task, project, lab, rows


def _latest_step(state: dict[str, Any], kind: str) -> dict[str, Any] | None:
    return next(
        (step for step in reversed(state.get("steps") or []) if step.get("step") == kind),
        None,
    )


async def _materialize_human_protocol_action(
    db_session: AsyncSession,
    *,
    run: ResearchRun,
    task: ResearchTask,
    rows: list[tuple[ResearchTaskProtocol, Protocol, ProtocolVersion]],
) -> ResearchAction:
    state = run.aira_state
    next_step = _latest_step(state, "add_next_protocol")
    values_step = _latest_step(
        state, "add_initial_values_for_fields_in_next_protocol"
    )
    if next_step is None:
        raise ValueError("AIRA requested a Record without selecting a Protocol")

    raw_index = (next_step.get("data") or {}).get("protocol_index")
    try:
        protocol_index = int(raw_index)
    except (TypeError, ValueError) as error:
        raise ValueError("AIRA selected an invalid Protocol index") from error
    selected = next((row for row in rows if row[0].position == protocol_index), None)
    if selected is None:
        raise ValueError("AIRA selected a Protocol outside this Research Environment")
    task_protocol, protocol, version = selected

    selection_position = (state.get("steps") or []).index(next_step)
    idempotency_key = f"aira-step:{selection_position}:protocol:{protocol_index}"
    existing = await ResearchAction.find_by(
        db_session,
        [
            ResearchAction.run_id == run.id,
            ResearchAction.idempotency_key == idempotency_key,
        ],
    )
    if existing is not None:
        return existing

    initial_values = dict((values_step or {}).get("data", {}).get("values") or {})
    sequence = (
        await db_session.scalar(
            select(func.max(ResearchAction.sequence)).where(
                ResearchAction.run_id == run.id
            )
        )
        or 0
    ) + 1
    input_data = {
        "protocol_id": str(protocol.id),
        "protocol_version": version.version,
        "initial_values": initial_values,
        "source": "aira",
    }
    preview_digest = canonical_digest(input_data)
    action = ResearchAction(
        run_id=run.id,
        sequence=sequence,
        plan_version=run.plan_version,
        kind=ResearchActionKind.PROTOCOL_RUN.value,
        status=ResearchActionStatus.WAITING.value,
        title=protocol.name,
        description=(next_step.get("data") or {}).get("thought") or "",
        executor_type="human",
        assignee_user_id=task.owner_user_id,
        input_data=input_data,
        requirements={"record_required": True},
        policy_decision="ask",
        preview_digest=preview_digest,
        idempotency_key=idempotency_key,
    )
    db_session.add(action)
    await db_session.flush()
    protocol_run = ResearchProtocolRun(
        action_id=action.id,
        protocol_id=protocol.id,
        protocol_version_id=version.id,
        protocol_version=version.version,
        initial_values=initial_values,
    )
    db_session.add(protocol_run)
    work_item = ResearchHumanWorkItem(
        action_id=action.id,
        assignee_user_id=task.owner_user_id,
        instructions=action.description or f"Execute {protocol.name} and submit its Record.",
        submission_contract={
            "type": "protocol_record",
            "protocol_id": str(protocol.id),
            "protocol_version": version.version,
        },
    )
    db_session.add(work_item)
    db_session.add(
        ResearchArtifactLink(
            task_id=task.id,
            run_id=run.id,
            action_id=action.id,
            artifact_type="protocol",
            artifact_id=str(protocol.id),
            artifact_version=version.version,
            relation="method",
            link_metadata={"position": task_protocol.position},
        )
    )
    await db_session.flush()
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        work_item_id=work_item.id,
        kind="work_item.assigned",
        actor_user_id=None,
        payload={
            "assignee_user_id": str(work_item.assignee_user_id),
            "protocol_id": str(protocol.id),
            "protocol_version": version.version,
        },
        idempotency_key=f"action:{action.id}:assigned:1",
    )
    return action


def _apply_aira_step(state: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
    result = {**state, "steps": [*(state.get("steps") or []), step]}
    data = step.get("data") or {}
    if step.get("step") == "add_research_strategy" and "researchable" in data:
        result["researchable"] = bool(data["researchable"])
    if step.get("step") == "add_final_research_conclusion":
        result["final_research_conclusion"] = data.get("conclusion") or ""
    result["path_status"] = path_status_after_step(state["path_status"], step)
    return result


async def _result_package(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
) -> dict[str, Any]:
    actions = list(
        (
            await db_session.scalars(
                select(ResearchAction)
                .where(ResearchAction.run_id == run.id)
                .order_by(ResearchAction.sequence)
            )
        ).all()
    )
    artifacts = list(
        (
            await db_session.scalars(
                select(ResearchArtifactLink).where(
                    ResearchArtifactLink.run_id == run.id
                )
            )
        ).all()
    )
    return {
        "schema": "airalogy.research-result-package.v1",
        "task_id": str(task.id),
        "run_id": str(run.id),
        "goal": task.goal,
        "success_criteria": task.success_criteria,
        "goal_assessment": "requires_human_review",
        "narrative_conclusion": run.aira_state.get("final_research_conclusion") or "",
        "claims": [],
        "evidence": [
            {
                "artifact_type": item.artifact_type,
                "artifact_id": item.artifact_id,
                "artifact_version": item.artifact_version,
                "relation": item.relation,
            }
            for item in artifacts
            if item.relation in {"produced", "evidence"}
        ],
        "actions": [
            {
                "id": str(item.id),
                "sequence": item.sequence,
                "kind": item.kind,
                "status": item.status,
                "title": item.title,
                "error": item.error,
            }
            for item in actions
        ],
        "failed_attempts": [
            str(item.id)
            for item in actions
            if item.status == ResearchActionStatus.FAILED.value
        ],
        "unresolved_questions": [],
        "reproducibility": {
            "environment_snapshot": run.environment_snapshot,
            "plan_version": run.plan_version,
        },
        "generated_at": utcnow().isoformat(),
    }


async def _finish_aira_run(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
) -> dict[str, Any]:
    package = await _result_package(db_session, task=task, run=run)
    now = utcnow()
    run.status = ResearchRunStatus.COMPLETED.value
    run.completed_at = now
    run.result_package = package
    task.status = ResearchTaskStatus.REVIEW_REQUIRED.value
    task.result_package = package
    task.conclusion = package["narrative_conclusion"]
    task.revision += 1
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        kind="run.completed",
        actor_user_id=None,
        payload={"human_review_required": True},
        idempotency_key=f"run:{run.id}:completed",
    )
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        kind="task.review_requested",
        actor_user_id=None,
        payload={"result_package_schema": package["schema"]},
        idempotency_key=f"task:{task.id}:review:{run.id}",
    )
    await db_session.commit()
    return {"status": run.status, "human_review_required": True}


async def process_research_run_advance(
    db_session: AsyncSession,
    *,
    run_id: UUID,
    generation: int,
    max_steps: int = 8,
) -> dict[str, Any]:
    """Advance one Run until it reaches an external boundary.

    Every AI response is committed independently. Retries compare generation and
    persisted path length so a duplicate job cannot append the same step twice.
    """

    for _ in range(max_steps):
        run, task, project, lab, rows = await _load_run_context(db_session, run_id)
        if generation != run.advance_generation:
            return {"status": "superseded", "generation": generation}
        if run.status in TERMINAL_RUN_STATUSES or run.status == ResearchRunStatus.PAUSED.value:
            return {"status": run.status}
        if run.aira_state.get("path_status") == "waiting_for_record":
            action = await _materialize_human_protocol_action(
                db_session, run=run, task=task, rows=rows
            )
            run.status = ResearchRunStatus.WAITING_FOR_HUMAN.value
            task.status = ResearchTaskStatus.ACTIVE.value
            await db_session.commit()
            return {"status": run.status, "action_id": str(action.id)}
        if run.aira_state.get("path_status") == "completed":
            return await _finish_aira_run(db_session, task=task, run=run)
        if not config.effective_ai_enabled:
            run.status = ResearchRunStatus.RUNNING.value
            run.last_error = "AI is disabled; continue this Research Task manually."
            await emit_research_event(
                db_session,
                task_id=task.id,
                run_id=run.id,
                kind="run.manual_control_required",
                actor_user_id=None,
                payload={"reason": "ai_disabled"},
                idempotency_key=f"run:{run.id}:manual:{generation}",
            )
            await db_session.commit()
            return {"status": run.status, "manual": True}

        path_status = run.aira_state.get("path_status")
        if path_status not in AIRA_AI_STATUSES:
            raise ValueError(f"Unsupported AIRA path status: {path_status}")
        state_digest = canonical_digest(run.aira_state)
        step_index = len(run.aira_state.get("steps") or [])
        workflow_data = {
            "workflow_info": workflow_info_for_task(task, project, lab, rows),
            "protocols_info": protocol_info_for_task(project, lab, rows),
            "path_data": run.aira_state,
        }
        usage_context = create_usage_context(
            feature="research.run.advance",
            user_id=run.requested_by_user_id,
            lab_id=task.lab_id,
            project_id=task.project_id,
            attributes={
                "task_id": str(task.id),
                "run_id": str(run.id),
                "generation": generation,
            },
        )
        # Do not keep a database transaction open while waiting for a model
        # provider. The persisted state digest is checked again under a row lock
        # before the returned step is accepted.
        await db_session.commit()
        try:
            step = await aira_workflow_step(
                workflow_data,
                task.ai_model or config.CHAT_MODEL_FAST,
                usage_context=usage_context,
            )
        except Exception as error:
            await db_session.rollback()
            failed_run = await db_session.get(ResearchRun, run_id)
            if failed_run is not None:
                failed_run.last_error = str(error)[:8000]
                await db_session.commit()
            raise

        expected_step = EXPECTED_AIRA_STEPS[path_status]
        if not isinstance(step, dict) or step.get("step") != expected_step:
            raise ValueError(
                f"AIRA returned an invalid step for {path_status}; "
                f"expected {expected_step}"
            )

        current_run = (
            await db_session.execute(
                select(ResearchRun)
                .where(ResearchRun.id == run_id)
                .with_for_update()
            )
        ).scalar_one()
        if generation != current_run.advance_generation:
            await db_session.rollback()
            return {"status": "superseded", "generation": generation}
        if canonical_digest(current_run.aira_state) != state_digest:
            await db_session.rollback()
            continue

        normalized_step = {
            **step,
            "path_index": step.get("path_index", step_index),
            "mode": step.get("mode") or "ai",
            "data": dict(step.get("data") or {}),
        }
        current_run.aira_state = _apply_aira_step(
            current_run.aira_state, normalized_step
        )
        current_run.status = ResearchRunStatus.RUNNING.value
        current_run.last_error = None
        current_task = await db_session.get(ResearchTask, current_run.task_id)
        await emit_research_event(
            db_session,
            task_id=current_task.id,
            run_id=current_run.id,
            kind="aira.step_completed",
            actor_user_id=None,
            payload={
                "step": normalized_step.get("step"),
                "path_status": current_run.aira_state["path_status"],
                "path_index": normalized_step["path_index"],
            },
            idempotency_key=f"run:{current_run.id}:aira-step:{step_index}",
        )
        if normalized_step.get("step") in {
            "add_research_strategy",
            "add_next_protocol",
        }:
            await create_plan_version(
                db_session,
                task=current_task,
                run=current_run,
                kind="aira",
                plan={
                    "workflow": workflow_info_for_task(
                        current_task, project, lab, rows
                    ),
                    "aira_state": current_run.aira_state,
                },
                summary=(normalized_step.get("data") or {}).get("thought")
                or normalized_step.get("step", "AIRA plan update"),
            )
        await db_session.commit()

    run = await db_session.get(ResearchRun, run_id)
    if run is not None:
        run.last_error = "AIRA step limit reached; resume to continue safely."
        await db_session.commit()
    return {"status": "step_limit", "max_steps": max_steps}


async def mark_research_run_job_failure(
    db_session: AsyncSession,
    *,
    run_id: UUID,
    error: str,
    terminal: bool,
) -> None:
    run = await db_session.get(ResearchRun, run_id)
    if run is None:
        return
    task = await db_session.get(ResearchTask, run.task_id)
    run.last_error = error[:8000]
    if terminal and run.status not in TERMINAL_RUN_STATUSES:
        run.status = ResearchRunStatus.FAILED.value
        run.completed_at = utcnow()
        if task is not None:
            task.status = ResearchTaskStatus.FAILED.value
            task.outcome = ResearchTaskOutcome.EXECUTION_FAILED.value
            task.revision += 1
            await emit_research_event(
                db_session,
                task_id=task.id,
                run_id=run.id,
                kind="run.failed",
                actor_user_id=None,
                payload={"error": error[:2000]},
                idempotency_key=f"run:{run.id}:failed",
            )
    await db_session.flush()
