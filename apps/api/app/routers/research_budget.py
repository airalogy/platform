"""Immutable Research Task budget ledger APIs."""

from __future__ import annotations

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
    }
