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


def project_operational_limit_amendment(
    *,
    task: ResearchTask,
    snapshot: dict[str, Any],
    deadline_at: datetime | None,
    budget_limit: Decimal | None,
    budget_currency: str | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate and project a whole operational-limit replacement.

    Budget entries are a single-currency ledger. Once that ledger has entries,
    the ceiling may move but its currency and enabled state must remain stable.
    """

    checked_at = now or datetime.now(UTC)
    if deadline_at is not None:
        if deadline_at.tzinfo is None:
            deadline_at = deadline_at.replace(tzinfo=UTC)
        if deadline_at <= checked_at:
            raise ResearchBudgetError("Research Task deadline must be in the future")
    if (budget_limit is None) != (budget_currency is None):
        raise ResearchBudgetError("Budget limit and currency must be provided together")
    normalized_currency = (
        normalize_currency(budget_currency) if budget_currency is not None else None
    )
    if budget_limit is not None and budget_limit <= 0:
        raise ResearchBudgetError("Budget limit must be greater than zero")

    current_limit = (
        Decimal(task.budget_limit) if task.budget_limit is not None else None
    )
    current_currency = task.budget_currency
    has_entries = bool(snapshot.get("entries"))
    if has_entries and (
        budget_limit is None or normalized_currency != current_currency
    ):
        raise ResearchBudgetError(
            "A budget with ledger entries cannot be removed or change currency"
        )

    committed = Decimal(snapshot["committed"])
    budget_changed = (
        budget_limit != current_limit or normalized_currency != current_currency
    )
    if budget_changed and budget_limit is not None and budget_limit <= committed:
        raise ResearchBudgetError(
            "The amended budget limit must exceed the committed amount"
        )

    current_deadline = task.deadline_at
    if current_deadline is not None and current_deadline.tzinfo is None:
        current_deadline = current_deadline.replace(tzinfo=UTC)
    if (
        deadline_at == current_deadline
        and budget_limit == current_limit
        and normalized_currency == current_currency
    ):
        raise ResearchBudgetError("The operational limits have not changed")

    remaining = budget_limit - committed if budget_limit is not None else None
    resume_eligible = (deadline_at is None or deadline_at > checked_at) and (
        remaining is None or remaining > 0
    )
    return {
        "deadline_at": deadline_at.isoformat() if deadline_at is not None else None,
        "budget_limit": _money(budget_limit) if budget_limit is not None else None,
        "budget_currency": normalized_currency,
        "budget_committed": _money(committed),
        "budget_remaining": _money(remaining) if remaining is not None else None,
        "resume_eligible": resume_eligible,
        "checked_at": checked_at.isoformat(),
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
