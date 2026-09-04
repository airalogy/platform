"""Immutable Research Task budget ledger APIs."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.database import DBSession
from app.models.lab import Lab
from app.models.project import Project
from app.models.research import (
    ResearchEvent,
    ResearchRun,
    ResearchRunStatus,
    ResearchTask,
    ResearchTaskOutcome,
    ResearchTaskStatus,
)
from app.models.research_execution import ResearchBudgetEntry
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.research_budget import (
    ResearchBudgetError,
    normalize_currency,
    project_budget_change,
    project_operational_limit_amendment,
    research_budget_snapshot,
)
from app.services.research_runtime import (
    canonical_digest,
    emit_research_event,
    require_research_capability,
)

router = APIRouter(prefix="/research-tasks", tags=["research-budget"])


class BudgetEntryDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_task_revision: int = Field(ge=1)
    kind: Literal["reserve", "release", "expense", "credit"]
    amount: Decimal = Field(gt=0, max_digits=38, decimal_places=18)
    currency: str = Field(min_length=1, max_length=16)
    description: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=8, max_length=160)

    @model_validator(mode="after")
    def normalize(self):
        self.currency = normalize_currency(self.currency)
        self.description = self.description.strip()
        self.idempotency_key = self.idempotency_key.strip()
        if not self.description:
            raise ValueError("Budget entry description cannot be empty")
        if len(self.idempotency_key) < 8:
            raise ValueError("Budget entry idempotency key is too short")
        return self


class BudgetEntryCreate(BudgetEntryDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class OperationalLimitsDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_task_revision: int = Field(ge=1)
    deadline_at: datetime | None
    budget_limit: Decimal | None = Field(gt=0, max_digits=38, decimal_places=18)
    budget_currency: str | None = Field(min_length=1, max_length=16)
    reason: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=8, max_length=160)

    @model_validator(mode="after")
    def normalize(self):
        self.reason = self.reason.strip()
        self.idempotency_key = self.idempotency_key.strip()
        if not self.reason:
            raise ValueError("Operational-limit amendment reason cannot be empty")
        if len(self.idempotency_key) < 8:
            raise ValueError("Operational-limit idempotency key is too short")
        if self.deadline_at is not None and self.deadline_at.tzinfo is None:
            self.deadline_at = self.deadline_at.replace(tzinfo=UTC)
        if (self.budget_limit is None) != (self.budget_currency is None):
            raise ValueError("Budget limit and currency must be provided together")
        if self.budget_currency is not None:
            self.budget_currency = normalize_currency(self.budget_currency)
        return self


class OperationalLimitsCreate(OperationalLimitsDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


async def _context(
    db_session: DBSession,
    *,
    task_id: UUID,
    current_user: User,
    capability: str = "research.read",
    lock: bool = False,
) -> tuple[ResearchTask, Project, Lab]:
    statement = select(ResearchTask).where(ResearchTask.id == task_id)
    if lock:
        statement = statement.with_for_update()
    task = (await db_session.scalars(statement)).first()
    if task is None or task.archived_at is not None:
        raise HTTPException(status_code=404, detail="Research Task not found")
    project = await Project.find_by(
        db_session, [Project.id == task.project_id, Project.deleted_at.is_(None)]
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await require_research_capability(
        db_session, user=current_user, project=project, capability=capability
    )
    lab = await db_session.get(Lab, task.lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    return task, project, lab


def _command(
    *,
    task: ResearchTask,
    params: BudgetEntryDraft,
    current: dict,
) -> dict:
    return {
        "task_id": str(task.id),
        "task_revision": task.revision,
        "kind": params.kind,
        "amount": str(params.amount),
        "currency": params.currency,
        "description": params.description,
        "idempotency_key": params.idempotency_key,
        "current": {
            "limit": current["limit"],
            "reserved": current["reserved"],
            "actual": current["actual"],
            "committed": current["committed"],
        },
    }


def _entry_data(entry: ResearchBudgetEntry) -> dict:
    return {**entry.as_dict(), "amount": str(entry.amount)}


def _limit_command(
    *,
    task: ResearchTask,
    params: OperationalLimitsDraft,
    current: dict,
    projected: dict,
) -> dict:
    stable_projection = {
        key: value for key, value in projected.items() if key != "checked_at"
    }
    return {
        "task_id": str(task.id),
        "task_revision": task.revision,
        "current": current,
        "projected": stable_projection,
        "reason": params.reason,
        "idempotency_key": params.idempotency_key,
    }


async def _limit_amendments(
    db_session: DBSession,
    *,
    task_id: UUID,
) -> list[dict]:
    events = list(
        (
            await db_session.scalars(
                select(ResearchEvent)
                .where(
                    ResearchEvent.task_id == task_id,
                    ResearchEvent.kind == "task.operational_limits_amended",
                )
                .order_by(ResearchEvent.created_at.desc(), ResearchEvent.id.desc())
            )
        ).all()
    )
    return [event.as_dict() for event in events]


async def _operational_limits_data(
    db_session: DBSession,
    *,
    task: ResearchTask,
) -> dict:
    return {
        "task_revision": task.revision,
        "deadline_at": task.deadline_at.isoformat() if task.deadline_at else None,
        "budget": await research_budget_snapshot(db_session, task=task),
        "amendments": await _limit_amendments(db_session, task_id=task.id),
    }


async def _limit_preview(
    db_session: DBSession,
    *,
    task: ResearchTask,
    project: Project,
    lab: Lab,
    params: OperationalLimitsDraft,
) -> dict:
    if task.revision != params.expected_task_revision:
        raise HTTPException(status_code=409, detail="Research Task has changed")
    if task.status in {
        ResearchTaskStatus.COMPLETED.value,
        ResearchTaskStatus.CANCELLED.value,
        ResearchTaskStatus.ARCHIVED.value,
    }:
        raise HTTPException(
            status_code=409,
            detail="A terminal Research Task cannot amend operational limits",
        )
    budget = await research_budget_snapshot(db_session, task=task)
    current = {
        "deadline_at": task.deadline_at.isoformat() if task.deadline_at else None,
        "budget_limit": budget["limit"],
        "budget_currency": task.budget_currency,
        "budget_committed": budget["committed"],
        "budget_remaining": budget["remaining"],
    }
    try:
        projected = project_operational_limit_amendment(
            task=task,
            snapshot=budget,
            deadline_at=params.deadline_at,
            budget_limit=params.budget_limit,
            budget_currency=params.budget_currency,
        )
    except ResearchBudgetError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    command = _limit_command(
        task=task,
        params=params,
        current=current,
        projected=projected,
    )
    resume_required = bool(
        task.status == ResearchTaskStatus.PAUSED.value
        and task.outcome
        in {
            ResearchTaskOutcome.STOPPED_BUDGET.value,
            ResearchTaskOutcome.STOPPED_TIME.value,
        }
        and projected["resume_eligible"]
    )
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": {
            "lab": {"id": str(lab.id), "uid": lab.uid, "name": lab.name},
            "project": {
                "id": str(project.id),
                "uid": project.uid,
                "name": project.name,
            },
            "task": {"id": str(task.id), "title": task.title},
        },
        "current": current,
        "projected": projected,
        "resume_required": resume_required,
        "effect": (
            "Replace the Research Task operational limits and append an immutable "
            "audit event; a paused Run is not resumed automatically"
        ),
    }


async def _preview(
    db_session: DBSession,
    *,
    task: ResearchTask,
    project: Project,
    lab: Lab,
    params: BudgetEntryDraft,
) -> dict:
    if task.revision != params.expected_task_revision:
        raise HTTPException(status_code=409, detail="Research Task has changed")
    current = await research_budget_snapshot(db_session, task=task)
    try:
        projected = project_budget_change(
            task=task,
            snapshot=current,
            kind=params.kind,
            amount=params.amount,
            currency=params.currency,
        )
    except ResearchBudgetError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    command = _command(task=task, params=params, current=current)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": {
            "lab": {"id": str(lab.id), "uid": lab.uid, "name": lab.name},
            "project": {
                "id": str(project.id),
                "uid": project.uid,
                "name": project.name,
            },
            "task": {"id": str(task.id), "title": task.title},
        },
        "current": current,
        "projected": projected,
        "effect": "Append an immutable entry to the Research Task budget ledger",
    }


@router.get("/{task_id}/operational-limits")
async def get_operational_limits(
    task_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, _project, _lab = await _context(
        db_session, task_id=task_id, current_user=current_user
    )
    return await _operational_limits_data(db_session, task=task)


@router.post("/{task_id}/operational-limits/preview")
async def preview_operational_limits(
    task_id: UUID,
    params: OperationalLimitsDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, project, lab = await _context(
        db_session,
        task_id=task_id,
        current_user=current_user,
        capability="research.approve",
    )
    return await _limit_preview(
        db_session,
        task=task,
        project=project,
        lab=lab,
        params=params,
    )


@router.post("/{task_id}/operational-limits")
async def amend_operational_limits(
    task_id: UUID,
    params: OperationalLimitsCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, project, lab = await _context(
        db_session,
        task_id=task_id,
        current_user=current_user,
        capability="research.approve",
        lock=True,
    )
    event_key = f"research-limits:{task.id}:{current_user.id}:{params.idempotency_key}"
    existing = await ResearchEvent.find_by(
        db_session, [ResearchEvent.idempotency_key == event_key]
    )
    if existing is not None:
        if existing.payload.get("preview_digest") != params.preview_digest:
            raise HTTPException(
                status_code=409,
                detail="Operational-limit idempotency key is already in use",
            )
        return {
            "amendment": existing.as_dict(),
            "operational_limits": await _operational_limits_data(db_session, task=task),
        }

    preview = await _limit_preview(
        db_session,
        task=task,
        project=project,
        lab=lab,
        params=params,
    )
    if preview["preview_digest"] != params.preview_digest:
        raise HTTPException(
            status_code=409, detail="Operational-limit preview has changed"
        )
    previous_revision = task.revision
    task.deadline_at = params.deadline_at
    task.budget_limit = params.budget_limit
    task.budget_currency = params.budget_currency
    task.revision += 1
    await db_session.flush()
    event = await emit_research_event(
        db_session,
        task_id=task.id,
        kind="task.operational_limits_amended",
        actor_user_id=current_user.id,
        payload={
            "preview_digest": params.preview_digest,
            "reason": params.reason,
            "previous_revision": previous_revision,
            "task_revision": task.revision,
            "current": preview["current"],
            "projected": preview["projected"],
            "resume_required": preview["resume_required"],
        },
        idempotency_key=event_key,
    )
    await db_session.commit()
    return {
        "amendment": event.as_dict(),
        "operational_limits": await _operational_limits_data(db_session, task=task),
    }


@router.get("/{task_id}/budget")
async def get_research_budget(
    task_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, _project, _lab = await _context(
        db_session, task_id=task_id, current_user=current_user
    )
    return await research_budget_snapshot(db_session, task=task)


@router.post("/{task_id}/budget/entries/preview")
async def preview_budget_entry(
    task_id: UUID,
    params: BudgetEntryDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, project, lab = await _context(
        db_session,
        task_id=task_id,
        current_user=current_user,
        capability="research.approve",
    )
    return await _preview(
        db_session,
        task=task,
        project=project,
        lab=lab,
        params=params,
    )


@router.post("/{task_id}/budget/entries")
async def create_budget_entry(
    task_id: UUID,
    params: BudgetEntryCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, project, lab = await _context(
        db_session,
        task_id=task_id,
        current_user=current_user,
        capability="research.approve",
        lock=True,
    )
    existing = await ResearchBudgetEntry.find_by(
        db_session,
        [
            ResearchBudgetEntry.task_id == task.id,
            ResearchBudgetEntry.idempotency_key == params.idempotency_key,
        ],
    )
    if existing is not None:
        if existing.command_digest != params.preview_digest:
            raise HTTPException(
                status_code=409, detail="Budget idempotency key is already in use"
            )
        return {
            "entry": _entry_data(existing),
            "budget": await research_budget_snapshot(db_session, task=task),
            "task_revision": task.revision,
        }
    preview = await _preview(
        db_session,
        task=task,
        project=project,
        lab=lab,
        params=params,
    )
    if preview["preview_digest"] != params.preview_digest:
        raise HTTPException(status_code=409, detail="Budget preview has changed")
    entry = ResearchBudgetEntry(
        task_id=task.id,
        run_id=None,
        action_id=None,
        kind=params.kind,
        amount=params.amount,
        currency=params.currency,
        source_type="manual",
        description=params.description,
        created_by_user_id=current_user.id,
        idempotency_key=params.idempotency_key,
        command_digest=params.preview_digest,
    )
    db_session.add(entry)
    task.revision += 1
    await db_session.flush()
    await emit_research_event(
        db_session,
        task_id=task.id,
        kind="budget.entry_recorded",
        actor_user_id=current_user.id,
        payload={
            "entry_id": str(entry.id),
            "kind": entry.kind,
            "amount": str(entry.amount),
            "currency": entry.currency,
        },
        idempotency_key=f"research-budget:{entry.id}:recorded",
    )
    budget = await research_budget_snapshot(db_session, task=task)
    if (
        task.status == ResearchTaskStatus.ACTIVE.value
        and budget["remaining"] is not None
        and Decimal(budget["remaining"]) <= 0
    ):
        run = (
            await db_session.scalars(
                select(ResearchRun)
                .where(ResearchRun.task_id == task.id)
                .order_by(ResearchRun.run_number.desc())
                .limit(1)
            )
        ).first()
        if run is not None and run.status not in {
            ResearchRunStatus.COMPLETED.value,
            ResearchRunStatus.FAILED.value,
            ResearchRunStatus.CANCELLED.value,
        }:
            run.status = ResearchRunStatus.PAUSED.value
            run.last_error = "Research Task budget limit reached"
            task.status = ResearchTaskStatus.PAUSED.value
            task.outcome = ResearchTaskOutcome.STOPPED_BUDGET.value
            await emit_research_event(
                db_session,
                task_id=task.id,
                run_id=run.id,
                kind="run.operational_limit_reached",
                actor_user_id=current_user.id,
                payload={"limit": "budget", "snapshot": budget},
                idempotency_key=f"run:{run.id}:limit:budget",
            )
    await db_session.commit()
    return {
        "entry": _entry_data(entry),
        "budget": budget,
        "task_revision": task.revision,
    }
