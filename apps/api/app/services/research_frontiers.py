"""Aggregate lifecycle rules for bounded parallel Research Action frontiers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import (
    ResearchAction,
    ResearchActionStatus,
    ResearchRun,
    ResearchRunStatus,
    ResearchTask,
    ResearchTaskStatus,
)

TERMINAL_ACTION_STATUSES = {
    ResearchActionStatus.COMPLETED.value,
    ResearchActionStatus.FAILED.value,
    ResearchActionStatus.SKIPPED.value,
    ResearchActionStatus.CANCELLED.value,
}


def parallel_group(action: ResearchAction) -> dict[str, Any] | None:
    value = (action.input_data or {}).get("parallel_group")
    if not isinstance(value, dict) or not str(value.get("id") or "").strip():
        return None
    return value


async def parallel_frontier_actions(
    db_session: AsyncSession,
    *,
    action: ResearchAction,
) -> list[ResearchAction]:
    group = parallel_group(action)
    if group is None:
        return [action]
    candidates = list(
        (
            await db_session.scalars(
                select(ResearchAction)
                .where(
                    ResearchAction.run_id == action.run_id,
                    ResearchAction.plan_version == action.plan_version,
                )
                .order_by(ResearchAction.sequence)
            )
        ).all()
    )
    group_id = str(group["id"])
    return [
        item
        for item in candidates
        if str((parallel_group(item) or {}).get("id") or "") == group_id
    ]


def frontier_run_status(actions: list[ResearchAction]) -> str | None:
    """Return the aggregate waiting state, or None when all branches settled."""

    remaining = [
        action for action in actions if action.status not in TERMINAL_ACTION_STATUSES
    ]
    if not remaining:
        return None
    if any(action.status == ResearchActionStatus.PROPOSED.value for action in remaining):
        return ResearchRunStatus.WAITING_FOR_APPROVAL.value
    return ResearchRunStatus.WAITING_FOR_TOOL.value


async def hold_or_release_parallel_frontier(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
    action: ResearchAction,
) -> bool:
    """Keep a Run at its parallel barrier; return True once every branch settles."""

    group = parallel_group(action)
    if group is None:
        return True
    actions = await parallel_frontier_actions(db_session, action=action)
    expected_size = int(group.get("size") or 0)
    if expected_size < 2 or len(actions) != expected_size:
        raise ValueError("Parallel Research Action frontier is incomplete")
    waiting_status = frontier_run_status(actions)
    if waiting_status is not None:
        run.status = (
            ResearchRunStatus.PAUSED.value
            if task.status == ResearchTaskStatus.PAUSED.value
            else waiting_status
        )
        return False
    run.status = (
        ResearchRunStatus.PAUSED.value
        if task.status == ResearchTaskStatus.PAUSED.value
        else ResearchRunStatus.RUNNING.value
    )
    return True
