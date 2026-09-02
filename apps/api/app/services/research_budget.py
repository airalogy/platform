"""Deterministic budget accounting and operational limit checks."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import ResearchTask
from app.models.research_execution import ResearchBudgetEntry, ResearchBudgetEntryKind


class ResearchBudgetError(ValueError):
    pass


def normalize_currency(value: str) -> str:
    currency = value.strip().upper()
    if len(currency) != 3 or not currency.isalpha() or not currency.isascii():
        raise ResearchBudgetError("Budget currency must be a three-letter ISO code")
    return currency


def _money(value: Decimal) -> str:
    return format(value.normalize(), "f") if value else "0"


async def research_budget_snapshot(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
) -> dict[str, Any]:
    entries = list(
        (
            await db_session.scalars(
                select(ResearchBudgetEntry)
                .where(ResearchBudgetEntry.task_id == task.id)
                .order_by(ResearchBudgetEntry.created_at, ResearchBudgetEntry.id)
            )
        ).all()
    )
    reserved = Decimal(0)
    actual = Decimal(0)
    for entry in entries:
        amount = Decimal(entry.amount)
        if entry.kind == ResearchBudgetEntryKind.RESERVE.value:
            reserved += amount
        elif entry.kind == ResearchBudgetEntryKind.RELEASE.value:
            reserved -= amount
        elif entry.kind == ResearchBudgetEntryKind.EXPENSE.value:
            actual += amount
        elif entry.kind == ResearchBudgetEntryKind.CREDIT.value:
            actual -= amount
    limit = Decimal(task.budget_limit) if task.budget_limit is not None else None
    committed = reserved + actual
    remaining = limit - committed if limit is not None else None
    return {
        "enabled": limit is not None,
        "currency": task.budget_currency,
        "limit": _money(limit) if limit is not None else None,
        "reserved": _money(reserved),
        "actual": _money(actual),
        "committed": _money(committed),
        "remaining": _money(remaining) if remaining is not None else None,
        "entries": [
            {**entry.as_dict(), "amount": _money(Decimal(entry.amount))}
            for entry in entries
        ],
    }


def project_budget_change(
    *,
    task: ResearchTask,
    snapshot: dict[str, Any],
    kind: str,
    amount: Decimal,
    currency: str,
) -> dict[str, Any]:
    if task.budget_limit is None or task.budget_currency is None:
        raise ResearchBudgetError("This Research Task has no budget limit")
    normalized_currency = normalize_currency(currency)
    if normalized_currency != task.budget_currency:
        raise ResearchBudgetError("Budget entry currency does not match the Task")
    reserved = Decimal(snapshot["reserved"])
    actual = Decimal(snapshot["actual"])
    if kind == ResearchBudgetEntryKind.RESERVE.value:
        reserved += amount
    elif kind == ResearchBudgetEntryKind.RELEASE.value:
        reserved -= amount
    elif kind == ResearchBudgetEntryKind.EXPENSE.value:
        actual += amount
    elif kind == ResearchBudgetEntryKind.CREDIT.value:
        actual -= amount
    else:
        raise ResearchBudgetError("Unsupported Research budget entry kind")
    if reserved < 0:
        raise ResearchBudgetError("A budget release exceeds the reserved amount")
    if actual < 0:
        raise ResearchBudgetError("A budget credit exceeds the recorded actual cost")
    limit = Decimal(task.budget_limit)
    committed = reserved + actual
    if committed > limit:
        raise ResearchBudgetError("This entry would exceed the Research Task budget")
    return {
        "enabled": True,
        "currency": task.budget_currency,
        "limit": _money(limit),
        "reserved": _money(reserved),
        "actual": _money(actual),
        "committed": _money(committed),
        "remaining": _money(limit - committed),
    }


async def reached_operational_limit(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
) -> tuple[str, dict[str, Any]] | None:
    now = datetime.now(UTC)
    if task.deadline_at is not None and task.deadline_at <= now:
        return "time", {
            "deadline_at": task.deadline_at.isoformat(),
            "checked_at": now.isoformat(),
        }
    if task.budget_limit is not None:
        snapshot = await research_budget_snapshot(db_session, task=task)
        if Decimal(snapshot["remaining"]) <= 0:
            return "budget", snapshot
    return None
