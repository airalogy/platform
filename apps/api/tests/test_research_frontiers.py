import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.models.research import (
    ResearchAction,
    ResearchActionStatus,
    ResearchRun,
    ResearchRunStatus,
    ResearchTask,
    ResearchTaskStatus,
)
from app.services import research_runtime
from app.services.research_frontiers import (
    frontier_run_status,
    hold_or_release_parallel_frontier,
    parallel_group,
)
from app.services.research_planner import AiraActionProposal


def _action(*, status: str, position: int, size: int = 2) -> ResearchAction:
    return ResearchAction(
        id=uuid4(),
        run_id=uuid4(),
        sequence=position,
        plan_version=3,
        kind="tool_job",
        status=status,
        title=f"Tool {position}",
        description="",
        executor_type="platform_tool",
        input_data={
            "parallel_group": {
                "id": "aira-frontier:4:abc",
                "position": position,
                "size": size,
            }
        },
        requirements={},
        policy_decision="allow",
        preview_digest="a" * 64,
        idempotency_key=f"parallel-{position}",
    )


def test_parallel_frontier_status_prefers_approval_and_waits_for_every_branch():
    first = _action(status=ResearchActionStatus.COMPLETED.value, position=1)
    second = _action(status=ResearchActionStatus.PROPOSED.value, position=2)

    assert parallel_group(first)["position"] == 1
    assert frontier_run_status([first, second]) == ResearchRunStatus.WAITING_FOR_APPROVAL

    second.status = ResearchActionStatus.RUNNING.value
    assert frontier_run_status([first, second]) == ResearchRunStatus.WAITING_FOR_TOOL

    second.status = ResearchActionStatus.FAILED.value
    assert frontier_run_status([first, second]) is None


def test_parallel_frontier_holds_then_releases_the_run():
    run_id = uuid4()
    first = _action(status=ResearchActionStatus.COMPLETED.value, position=1)
    second = _action(status=ResearchActionStatus.RUNNING.value, position=2)
    first.run_id = run_id
    second.run_id = run_id
    task = ResearchTask(status=ResearchTaskStatus.ACTIVE.value)
    run = ResearchRun(id=run_id, status=ResearchRunStatus.WAITING_FOR_TOOL.value)
    db_session = AsyncMock()
    db_session.scalars.return_value = SimpleNamespace(all=lambda: [first, second])

    settled = asyncio.run(
        hold_or_release_parallel_frontier(
            db_session,
            task=task,
            run=run,
            action=first,
        )
    )
    assert settled is False
    assert run.status == ResearchRunStatus.WAITING_FOR_TOOL.value

    second.status = ResearchActionStatus.CANCELLED.value
    settled = asyncio.run(
        hold_or_release_parallel_frontier(
            db_session,
            task=task,
            run=run,
            action=first,
        )
    )
    assert settled is True
    assert run.status == ResearchRunStatus.RUNNING.value


def test_parallel_frontier_fails_closed_when_group_is_partial():
    action = _action(status=ResearchActionStatus.COMPLETED.value, position=1, size=3)
    task = ResearchTask(status=ResearchTaskStatus.ACTIVE.value)
    run = ResearchRun(id=action.run_id, status=ResearchRunStatus.WAITING_FOR_TOOL.value)
    db_session = AsyncMock()
    db_session.scalars.return_value = SimpleNamespace(all=lambda: [action])

    with pytest.raises(ValueError, match="incomplete"):
        asyncio.run(
            hold_or_release_parallel_frontier(
                db_session,
                task=task,
                run=run,
                action=action,
            )
        )


def test_non_parallel_action_does_not_overwrite_typed_waiting_state():
    action = _action(status=ResearchActionStatus.QUEUED.value, position=1)
    action.input_data = {}
    task = ResearchTask(status=ResearchTaskStatus.ACTIVE.value)
    run = ResearchRun(
        id=action.run_id,
        status=ResearchRunStatus.WAITING_FOR_COMPUTE.value,
    )

    settled = asyncio.run(
        hold_or_release_parallel_frontier(
            AsyncMock(),
            task=task,
            run=run,
            action=action,
        )
    )

    assert settled is True
    assert run.status == ResearchRunStatus.WAITING_FOR_COMPUTE.value


def test_aira_parallel_tools_share_one_plan_frontier(monkeypatch):
    task = ResearchTask(id=uuid4(), status=ResearchTaskStatus.ACTIVE.value)
    run = ResearchRun(id=uuid4(), plan_version=2)
    proposal = AiraActionProposal.model_validate(
        {
            "decision": "parallel_tools",
            "thought": "Collect independent context",
            "parallel_tools": [
                {
                    "tool_key": "knowledge.search",
                    "arguments": {"query": "RNA"},
                    "purpose": "Internal context",
                },
                {
                    "tool_key": "literature.search",
                    "arguments": {"query": "RNA"},
                    "purpose": "External context",
                },
            ],
        }
    )
    db_session = AsyncMock()
    db_session.scalars.return_value = SimpleNamespace(all=list)
    materialized = []

    async def create_plan(*_args, **_kwargs):
        run.plan_version += 1

    async def materialize(*_args, **kwargs):
        action = _action(
            status=ResearchActionStatus.PROPOSED.value,
            position=len(materialized) + 1,
        )
        action.run_id = run.id
        action.plan_version = run.plan_version
        action.input_data = {"parallel_group": kwargs["parallel_group"]}
        materialized.append((action, kwargs))
        return action

    monkeypatch.setattr(research_runtime, "create_plan_version", create_plan)
    monkeypatch.setattr(research_runtime, "_materialize_aira_action", materialize)
    monkeypatch.setattr(research_runtime, "emit_research_event", AsyncMock())

    actions = asyncio.run(
        research_runtime._materialize_aira_parallel_tools(
            db_session,
            task=task,
            run=run,
            proposal=proposal,
            step_index=7,
        )
    )

    assert run.plan_version == 3
    assert len(actions) == 2
    assert {item.input_data["parallel_group"]["id"] for item in actions} == {
        materialized[0][1]["parallel_group"]["id"]
    }
    assert [item.input_data["parallel_group"]["position"] for item in actions] == [
        1,
        2,
    ]
    assert all(call[1]["create_plan"] is False for call in materialized)
