import asyncio
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from app.models.research import (
    ResearchAction,
    ResearchActionDependency,
    ResearchActionStatus,
    ResearchRun,
    ResearchRunStatus,
    ResearchTask,
    ResearchTaskStatus,
)
from app.models.research_execution import ResearchToolJob, ResearchToolJobStatus
from app.services import research_runtime
from app.services.research_frontiers import (
    frontier_run_status,
    hold_or_release_parallel_frontier,
    parallel_group,
)
from app.services.research_planner import AiraActionProposal
from app.services.research_tools import research_tool_catalog
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable


def test_action_dependency_schema_rejects_self_edges_and_migration_is_linear():
    ddl = str(
        CreateTable(ResearchActionDependency.__table__).compile(
            dialect=postgresql.dialect()
        )
    )
    assert "ck_research_action_dependency_not_self" in ddl
    assert "action_id <> depends_on_action_id" in ddl

    migration = import_module(
        "migrations.versions.0039_research_action_dependency_guard"
    )
    assert migration.down_revision == "0038_research_resource_consumptions"


def test_action_dependency_guard_migration_handles_fresh_and_upgraded_databases(
    monkeypatch,
):
    migration = import_module(
        "migrations.versions.0039_research_action_dependency_guard"
    )
    calls: list[tuple[str, str]] = []
    constraints: set[str] = set()

    class Inspector:
        def get_check_constraints(self, _table: str):
            return [{"name": name} for name in constraints]

    monkeypatch.setattr(migration.op, "get_bind", lambda: object())
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: Inspector())
    monkeypatch.setattr(
        migration.op,
        "create_check_constraint",
        lambda name, *_args, **_kwargs: calls.append(("create", name)),
    )
    monkeypatch.setattr(
        migration.op,
        "drop_constraint",
        lambda name, *_args, **_kwargs: calls.append(("drop", name)),
    )

    migration.upgrade()
    assert calls == [("create", migration.CONSTRAINT_NAME)]

    calls.clear()
    constraints.add(migration.CONSTRAINT_NAME)
    migration.upgrade()
    assert calls == []

    migration.downgrade()
    assert calls == [("drop", migration.CONSTRAINT_NAME)]

    calls.clear()
    constraints.clear()
    migration.downgrade()
    assert calls == []


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
    assert (
        frontier_run_status([first, second]) == ResearchRunStatus.WAITING_FOR_APPROVAL
    )

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


def _graph_action(
    *,
    run_id,
    node_id: str,
    position: int,
    size: int,
    status: str = ResearchActionStatus.BLOCKED.value,
    depends_on_count: int = 0,
    dependency_count: int | None = None,
) -> ResearchAction:
    action = _action(status=status, position=position, size=size)
    action.run_id = run_id
    action.input_data = {
        "action_graph": {
            "id": "aira-tool-graph:5:abc",
            "node_id": node_id,
            "position": position,
            "size": size,
            "depends_on_count": depends_on_count,
            "dependency_count": (
                dependency_count if dependency_count is not None else size - 1
            ),
        }
    }
    action.revision = 1
    action.idempotency_key = f"graph:{node_id}"
    return action


def test_tool_graph_releases_only_ready_nodes(monkeypatch):
    run_id = uuid4()
    root = _graph_action(run_id=run_id, node_id="root", position=1, size=2)
    child = _graph_action(
        run_id=run_id,
        node_id="child",
        position=2,
        size=2,
        depends_on_count=1,
    )
    dependency = ResearchActionDependency(
        action_id=child.id,
        depends_on_action_id=root.id,
        condition={"required_status": "completed", "on_unsatisfied": "skipped"},
    )
    task = ResearchTask(id=uuid4(), status=ResearchTaskStatus.ACTIVE.value)
    run = ResearchRun(id=run_id, status=ResearchRunStatus.RUNNING.value)
    db_session = AsyncMock()
    db_session.add = Mock()
    db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [root, child]),
        SimpleNamespace(all=lambda: [dependency]),
        SimpleNamespace(all=lambda: [root, child]),
        SimpleNamespace(all=lambda: [dependency]),
    ]

    async def activate(*_args, action, **_kwargs):
        action.status = ResearchActionStatus.QUEUED.value

    monkeypatch.setattr(research_runtime, "activate_tool_action", activate)
    monkeypatch.setattr(research_runtime, "emit_research_event", AsyncMock())

    settled = asyncio.run(
        research_runtime.hold_or_release_aira_action_group(
            db_session, task=task, run=run, action=root
        )
    )
    assert settled is False
    assert root.status == ResearchActionStatus.QUEUED.value
    assert child.status == ResearchActionStatus.BLOCKED.value
    assert run.status == ResearchRunStatus.WAITING_FOR_TOOL.value

    root.status = ResearchActionStatus.COMPLETED.value
    settled = asyncio.run(
        research_runtime.hold_or_release_aira_action_group(
            db_session, task=task, run=run, action=root
        )
    )
    assert settled is False
    assert child.status == ResearchActionStatus.QUEUED.value


def test_tool_graph_resolves_parent_output_into_child_arguments(monkeypatch):
    run_id = uuid4()
    root = _graph_action(
        run_id=run_id,
        node_id="root",
        position=1,
        size=2,
        status=ResearchActionStatus.COMPLETED.value,
    )
    root.output_data = {
        "tool_key": "knowledge.search",
        "tool_version": "1",
        "result": {"items": [{"title": "RNA binding proteins"}]},
    }
    root.revision = 3
    child = _graph_action(
        run_id=run_id,
        node_id="child",
        position=2,
        size=2,
        depends_on_count=1,
    )
    child.input_data["action_graph"]["result_bindings"] = [
        {
            "source_node_id": "root",
            "source_path": ["result", "items", "0", "title"],
            "target_argument": "query",
        }
    ]
    dependency = ResearchActionDependency(
        action_id=child.id,
        depends_on_action_id=root.id,
        condition={"required_status": "completed", "on_unsatisfied": "skipped"},
    )
    child_job = ResearchToolJob(
        action_id=child.id,
        tool_key="knowledge.search",
        tool_version="1",
        arguments={"limit": 5},
    )
    task = ResearchTask(id=uuid4(), status=ResearchTaskStatus.ACTIVE.value)
    run = ResearchRun(
        id=run_id,
        status=ResearchRunStatus.WAITING_FOR_TOOL.value,
        environment_snapshot={
            "tools": [research_tool_catalog()["knowledge.search"].payload()]
        },
    )
    db_session = AsyncMock()
    db_session.add = Mock()
    db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [root, child]),
        SimpleNamespace(all=lambda: [dependency]),
    ]

    async def find_job(_session, _filters):
        return child_job

    activated_arguments = {}

    async def activate(*_args, action, **_kwargs):
        action.status = ResearchActionStatus.QUEUED.value
        activated_arguments.update(child_job.arguments)

    monkeypatch.setattr(ResearchToolJob, "find_by", find_job)
    monkeypatch.setattr(research_runtime, "activate_tool_action", activate)
    monkeypatch.setattr(research_runtime, "emit_research_event", AsyncMock())

    settled = asyncio.run(
        research_runtime.hold_or_release_aira_action_group(
            db_session, task=task, run=run, action=root
        )
    )

    assert settled is False
    assert activated_arguments == {"limit": 5, "query": "RNA binding proteins"}
    receipt = child.input_data["action_graph"]["result_binding_receipts"][0]
    assert receipt["source_action_id"] == str(root.id)
    assert receipt["source_action_revision"] == 3
    assert len(receipt["source_output_digest"]) == 64
    assert len(receipt["bound_value_digest"]) == 64
    assert len(receipt["resolved_arguments_digest"]) == 64
    assert child.preview_digest != "a" * 64


def test_tool_graph_fails_closed_when_bound_output_is_missing(monkeypatch):
    run_id = uuid4()
    root = _graph_action(
        run_id=run_id,
        node_id="root",
        position=1,
        size=2,
        status=ResearchActionStatus.COMPLETED.value,
    )
    root.output_data = {
        "tool_key": "knowledge.search",
        "tool_version": "1",
        "result": {"items": []},
    }
    child = _graph_action(
        run_id=run_id,
        node_id="child",
        position=2,
        size=2,
        depends_on_count=1,
    )
    child.input_data["action_graph"]["result_bindings"] = [
        {
            "source_node_id": "root",
            "source_path": ["result", "items", "0", "title"],
            "target_argument": "query",
        }
    ]
    dependency = ResearchActionDependency(
        action_id=child.id,
        depends_on_action_id=root.id,
        condition={"required_status": "completed", "on_unsatisfied": "skipped"},
    )
    child_job = ResearchToolJob(
        action_id=child.id,
        tool_key="knowledge.search",
        tool_version="1",
        arguments={"limit": 5},
    )
    task = ResearchTask(id=uuid4(), status=ResearchTaskStatus.ACTIVE.value)
    run = ResearchRun(
        id=run_id,
        status=ResearchRunStatus.WAITING_FOR_TOOL.value,
        environment_snapshot={
            "tools": [research_tool_catalog()["knowledge.search"].payload()]
        },
    )
    db_session = AsyncMock()
    db_session.add = Mock()
    db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [root, child]),
        SimpleNamespace(all=lambda: [dependency]),
    ]

    async def find_job(_session, _filters):
        return child_job

    monkeypatch.setattr(ResearchToolJob, "find_by", find_job)
    monkeypatch.setattr(research_runtime, "emit_research_event", AsyncMock())

    settled = asyncio.run(
        research_runtime.hold_or_release_aira_action_group(
            db_session, task=task, run=run, action=root
        )
    )

    assert settled is True
    assert child.status == ResearchActionStatus.FAILED.value
    assert child_job.status == ResearchToolJobStatus.FAILED.value
    assert "out of range" in child.error
    assert run.last_error == child.error


def test_tool_graph_skips_descendants_after_dependency_failure(monkeypatch):
    run_id = uuid4()
    root = _graph_action(
        run_id=run_id,
        node_id="root",
        position=1,
        size=3,
        status=ResearchActionStatus.FAILED.value,
    )
    child = _graph_action(
        run_id=run_id,
        node_id="child",
        position=2,
        size=3,
        depends_on_count=1,
        dependency_count=2,
    )
    root.input_data["action_graph"]["dependency_count"] = 2
    leaf = _graph_action(
        run_id=run_id,
        node_id="leaf",
        position=3,
        size=3,
        depends_on_count=1,
        dependency_count=2,
    )
    dependencies = [
        ResearchActionDependency(
            action_id=child.id,
            depends_on_action_id=root.id,
            condition={"required_status": "completed", "on_unsatisfied": "skipped"},
        ),
        ResearchActionDependency(
            action_id=leaf.id,
            depends_on_action_id=child.id,
            condition={"required_status": "completed", "on_unsatisfied": "skipped"},
        ),
    ]
    jobs = {
        child.id: ResearchToolJob(
            action_id=child.id,
            tool_key="knowledge.search",
            tool_version="1",
            arguments={"query": "child"},
        ),
        leaf.id: ResearchToolJob(
            action_id=leaf.id,
            tool_key="knowledge.search",
            tool_version="1",
            arguments={"query": "leaf"},
        ),
    }
    task = ResearchTask(id=uuid4(), status=ResearchTaskStatus.ACTIVE.value)
    run = ResearchRun(id=run_id, status=ResearchRunStatus.WAITING_FOR_TOOL.value)
    db_session = AsyncMock()
    db_session.add = Mock()
    db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [root, child, leaf]),
        SimpleNamespace(all=lambda: dependencies),
    ]

    async def find_job(_session, filters):
        action_id = filters[0].right.value
        return jobs[action_id]

    monkeypatch.setattr(ResearchToolJob, "find_by", find_job)
    monkeypatch.setattr(research_runtime, "emit_research_event", AsyncMock())

    settled = asyncio.run(
        research_runtime.hold_or_release_aira_action_group(
            db_session, task=task, run=run, action=root
        )
    )

    assert settled is True
    assert child.status == ResearchActionStatus.SKIPPED.value
    assert leaf.status == ResearchActionStatus.SKIPPED.value
    assert jobs[child.id].status == ResearchToolJobStatus.CANCELLED.value
    assert jobs[leaf.id].status == ResearchToolJobStatus.CANCELLED.value
    assert run.status == ResearchRunStatus.RUNNING.value


def test_aira_tool_graph_persists_dependencies_before_release(monkeypatch):
    task = ResearchTask(id=uuid4(), status=ResearchTaskStatus.ACTIVE.value)
    run = ResearchRun(id=uuid4(), plan_version=2)
    proposal = AiraActionProposal.model_validate(
        {
            "decision": "tool_graph",
            "thought": "Search, then refine",
            "tool_graph": [
                {
                    "node_id": "root",
                    "tool_key": "knowledge.search",
                    "arguments": {"query": "RNA"},
                    "purpose": "Broad search",
                },
                {
                    "node_id": "child",
                    "tool_key": "knowledge.search",
                    "arguments": {"query": "RNA binding"},
                    "purpose": "Refined search",
                    "depends_on": ["root"],
                },
            ],
        }
    )
    db_session = AsyncMock()
    db_session.add = Mock()
    db_session.scalars.return_value = SimpleNamespace(all=list)
    materialized = []

    async def create_plan(*_args, **_kwargs):
        run.plan_version += 1

    async def materialize(*_args, **kwargs):
        node_id = kwargs["action_graph"]["node_id"]
        action = _graph_action(
            run_id=run.id,
            node_id=node_id,
            position=len(materialized) + 1,
            size=2,
        )
        action.plan_version = run.plan_version
        materialized.append((action, kwargs))
        return action

    release = AsyncMock(return_value=False)
    monkeypatch.setattr(research_runtime, "create_plan_version", create_plan)
    monkeypatch.setattr(research_runtime, "_materialize_aira_action", materialize)
    monkeypatch.setattr(research_runtime, "hold_or_release_aira_action_group", release)
    monkeypatch.setattr(research_runtime, "emit_research_event", AsyncMock())

    actions = asyncio.run(
        research_runtime._materialize_aira_tool_graph(
            db_session,
            task=task,
            run=run,
            proposal=proposal,
            step_index=5,
        )
    )

    assert len(actions) == 2
    assert all(item[1]["defer_activation"] is True for item in materialized)
    dependency = next(
        call.args[0]
        for call in db_session.add.call_args_list
        if isinstance(call.args[0], ResearchActionDependency)
    )
    assert dependency.action_id == actions[1].id
    assert dependency.depends_on_action_id == actions[0].id
    release.assert_awaited_once()
