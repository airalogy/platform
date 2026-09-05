import asyncio
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.research import (
    ResearchAction,
    ResearchActionDependency,
    ResearchActionKind,
    ResearchActionStatus,
    ResearchArtifactLink,
    ResearchProtocolRun,
    ResearchRun,
    ResearchRunStatus,
    ResearchTask,
    ResearchTaskStatus,
)
from app.models.research_execution import (
    ResearchInstrumentJob,
    ResearchInstrumentJobStatus,
    ResearchResourceReservation,
    ResearchResourceReservationStatus,
    ResearchServiceJob,
    ResearchServiceJobStatus,
    ResearchToolJob,
    ResearchToolJobStatus,
)
from app.services import research_executor_bindings, research_runtime
from app.services.research_autonomy_evaluations import (
    policy_snapshot_with_grants,
    tool_autonomy_target,
)
from app.services.research_autonomy_policy import autonomy_policy_snapshot
from app.services.research_frontiers import (
    frontier_run_status,
    hold_or_release_parallel_frontier,
    parallel_group,
)
from app.services.research_planner import AiraActionProposal
from app.services.research_tools import research_tool_catalog


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
    kind: str = "tool_job",
    graph_type: str | None = None,
) -> ResearchAction:
    action = _action(status=status, position=position, size=size)
    action.run_id = run_id
    action.input_data = {
        "action_graph": {
            "id": "aira-tool-graph:5:abc",
            **({"type": graph_type} if graph_type else {}),
            "node_id": node_id,
            "position": position,
            "size": size,
            "depends_on_count": depends_on_count,
            "dependency_count": (
                dependency_count if dependency_count is not None else size - 1
            ),
        }
    }
    action.kind = kind
    action.revision = 1
    action.idempotency_key = f"graph:{node_id}"
    return action


def test_paused_graph_defers_dependency_release_until_explicit_resume(monkeypatch):
    run_id = uuid4()
    root = _graph_action(
        run_id=run_id, node_id="root", position=1, size=2, status="completed"
    )
    child = _graph_action(
        run_id=run_id, node_id="child", position=2, size=2, depends_on_count=1
    )
    dependency = ResearchActionDependency(
        action_id=child.id,
        depends_on_action_id=root.id,
        condition={"required_status": "completed", "on_unsatisfied": "skipped"},
    )
    task = ResearchTask(id=uuid4(), status="paused")
    run = ResearchRun(id=run_id, status="paused")
    db = AsyncMock()
    db.scalars.side_effect = [
        SimpleNamespace(all=lambda: [root, child]),
        SimpleNamespace(all=lambda: [dependency]),
        SimpleNamespace(all=lambda: [child]),
        SimpleNamespace(all=lambda: [root, child]),
        SimpleNamespace(all=lambda: [dependency]),
        SimpleNamespace(all=list),
    ]

    async def activate(*args, action, **kwargs):
        action.status = "queued"

    activation = AsyncMock(side_effect=activate)
    monkeypatch.setattr(research_runtime, "_activate_released_graph_action", activation)
    monkeypatch.setattr(research_runtime, "emit_research_event", AsyncMock())
    asyncio.run(
        research_runtime.hold_or_release_aira_action_group(
            db, task=task, run=run, action=root
        )
    )
    activation.assert_not_awaited()
    assert child.status == "blocked" and run.status == "paused"
    task.status = "active"
    assert (
        asyncio.run(
            research_runtime.restore_pending_action_boundary(db, task=task, run=run)
        )
        is True
    )
    assert child.status == "queued" and run.status == "waiting_for_tool"
    activation.assert_awaited_once()


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


def test_mixed_action_graph_releases_each_typed_boundary_in_order(monkeypatch):
    run_id = uuid4()
    root = _graph_action(
        run_id=run_id,
        node_id="search",
        position=1,
        size=2,
        graph_type="mixed_digital",
    )
    child = _graph_action(
        run_id=run_id,
        node_id="await_data",
        position=2,
        size=2,
        depends_on_count=1,
        kind="wait_event",
        graph_type="mixed_digital",
    )
    for action in (root, child):
        action.input_data["action_graph"]["id"] = "aira-action-graph:5:abc"
    dependency = ResearchActionDependency(
        action_id=child.id,
        depends_on_action_id=root.id,
        condition={"required_status": "completed", "on_unsatisfied": "skipped"},
    )
    task = ResearchTask(id=uuid4(), status=ResearchTaskStatus.ACTIVE.value)
    run = ResearchRun(id=run_id, status=ResearchRunStatus.RUNNING.value)
    db_session = AsyncMock()
    db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [root, child]),
        SimpleNamespace(all=lambda: [dependency]),
        SimpleNamespace(all=lambda: [root, child]),
        SimpleNamespace(all=lambda: [dependency]),
    ]

    async def activate(*_args, action, **_kwargs):
        action.status = (
            ResearchActionStatus.WAITING.value
            if action.kind == "wait_event"
            else ResearchActionStatus.QUEUED.value
        )

    monkeypatch.setattr(research_runtime, "_activate_released_graph_action", activate)
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
    assert child.status == ResearchActionStatus.WAITING.value
    assert run.status == ResearchRunStatus.WAITING_FOR_EVENT.value


def test_aira_mixed_action_graph_persists_dependencies_before_release(monkeypatch):
    task = ResearchTask(id=uuid4(), status=ResearchTaskStatus.ACTIVE.value)
    run = ResearchRun(id=uuid4(), plan_version=4)
    proposal = AiraActionProposal.model_validate(
        {
            "decision": "action_graph",
            "thought": "Search, then wait for a Data Asset",
            "action_graph": [
                {
                    "node_id": "search",
                    "decision": "tool",
                    "tool_key": "knowledge.search",
                    "arguments": {"query": "RNA"},
                },
                {
                    "node_id": "await_data",
                    "decision": "wait",
                    "wait_template_key": "data_asset.ready",
                    "depends_on": ["search"],
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
        metadata = kwargs["action_graph"]
        node = proposal.action_graph[len(materialized)]
        action = _graph_action(
            run_id=run.id,
            node_id=node.node_id,
            position=len(materialized) + 1,
            size=2,
            kind=("tool_job" if node.decision == "tool" else "wait_event"),
            graph_type="mixed_digital",
        )
        action.input_data["action_graph"] = metadata
        action.plan_version = run.plan_version
        materialized.append((action, kwargs))
        return action

    release = AsyncMock(return_value=False)
    monkeypatch.setattr(research_runtime, "create_plan_version", create_plan)
    monkeypatch.setattr(research_runtime, "_materialize_aira_action", materialize)
    monkeypatch.setattr(research_runtime, "hold_or_release_aira_action_group", release)
    monkeypatch.setattr(research_runtime, "emit_research_event", AsyncMock())

    actions = asyncio.run(
        research_runtime._materialize_aira_action_graph(
            db_session,
            task=task,
            run=run,
            proposal=proposal,
            step_index=5,
        )
    )

    assert [item.kind for item in actions] == ["tool_job", "wait_event"]
    assert all(item[1]["defer_activation"] is True for item in materialized)
    assert all(
        item[1]["action_graph"]["type"] == "mixed_governed" for item in materialized
    )
    dependency = next(
        call.args[0]
        for call in db_session.add.call_args_list
        if isinstance(call.args[0], ResearchActionDependency)
    )
    assert dependency.action_id == actions[1].id
    assert dependency.depends_on_action_id == actions[0].id
    release.assert_awaited_once()


def test_protocol_graph_node_materializes_without_assigning_human_work(monkeypatch):
    protocol_id = uuid4()
    protocol_version_id = uuid4()
    assignee_id = uuid4()
    task = ResearchTask(
        id=uuid4(),
        project_id=uuid4(),
        owner_user_id=uuid4(),
        autonomy_level="assisted",
        status=ResearchTaskStatus.ACTIVE.value,
    )
    run = ResearchRun(
        id=uuid4(),
        plan_version=3,
        requested_by_user_id=uuid4(),
        environment_snapshot={
            "protocols": [
                {
                    "id": str(protocol_id),
                    "version_id": str(protocol_version_id),
                    "version": "1.0.0",
                }
            ],
            "executor_bindings": [
                {
                    "capability_key": f"protocol:{protocol_id}",
                    "capability_version": "1.0.0",
                    "approval_policy": "always_ask",
                    "executor_type": "human",
                    "resolved_executor_ref": {
                        "type": "user",
                        "id": str(assignee_id),
                    },
                }
            ],
        },
    )
    task_protocol = SimpleNamespace(
        protocol_id=protocol_id,
        protocol_version_id=protocol_version_id,
        position=1,
    )
    protocol = SimpleNamespace(id=protocol_id, name="RNA extraction")
    version = SimpleNamespace(
        id=protocol_version_id,
        protocol_id=protocol_id,
        version="1.0.0",
    )
    proposal = AiraActionProposal.model_validate(
        {
            "decision": "protocol",
            "protocol_id": str(protocol_id),
            "protocol_initial_values": {"sample_count": 4},
            "thought": "Run the pinned method after context collection",
        }
    )
    added = []
    db_session = AsyncMock()
    db_session.add = added.append
    db_session.scalar.side_effect = [0, 0]

    async def get_model(model, _item_id):
        if model is research_runtime.Protocol:
            return protocol
        if model is research_runtime.ProtocolVersion:
            return version
        return None

    db_session.get.side_effect = get_model
    monkeypatch.setattr(ResearchAction, "find_by", AsyncMock(return_value=None))
    monkeypatch.setattr(
        research_runtime.ResearchTaskProtocol,
        "find_by",
        AsyncMock(return_value=task_protocol),
    )
    monkeypatch.setattr(
        research_executor_bindings,
        "enforce_environment_binding_action_limit",
        AsyncMock(),
    )
    monkeypatch.setattr(research_runtime, "emit_research_event", AsyncMock())

    action = asyncio.run(
        research_runtime._materialize_aira_action(
            db_session,
            task=task,
            run=run,
            proposal=proposal,
            step_index=6,
            create_plan=False,
            action_graph={
                "id": "aira-action-graph:6:protocol",
                "type": "mixed_governed",
                "node_id": "assay",
                "position": 2,
                "size": 2,
                "depends_on_count": 1,
                "dependency_count": 1,
                "result_bindings": [],
            },
            defer_activation=True,
        )
    )

    assert action.kind == "protocol_run"
    assert action.status == ResearchActionStatus.BLOCKED.value
    assert action.assignee_user_id == assignee_id
    assert action.input_data["initial_values"] == {"sample_count": 4}
    assert any(isinstance(item, ResearchProtocolRun) for item in added)
    assert any(isinstance(item, ResearchArtifactLink) for item in added)
    assert not any(
        isinstance(item, research_runtime.ResearchHumanWorkItem) for item in added
    )


def test_generic_human_graph_node_waits_for_dependencies_before_assignment(
    monkeypatch,
):
    assignee_id = uuid4()
    task = ResearchTask(
        id=uuid4(),
        project_id=uuid4(),
        owner_user_id=uuid4(),
        autonomy_level="assisted",
        status=ResearchTaskStatus.ACTIVE.value,
    )
    run = ResearchRun(
        id=uuid4(),
        plan_version=4,
        requested_by_user_id=uuid4(),
        environment_snapshot={
            "human_work": [
                {
                    "key": "human:structured-work",
                    "version": "1",
                    "kind": "human",
                    "available": True,
                }
            ],
            "executor_bindings": [
                {
                    "capability_key": "human:structured-work",
                    "capability_version": "1",
                    "approval_policy": "always_ask",
                    "executor_type": "human",
                    "mode": "structured_submission",
                    "resolved_executor_ref": {
                        "type": "user",
                        "id": str(assignee_id),
                    },
                }
            ],
        },
    )
    proposal = AiraActionProposal.model_validate(
        {
            "decision": "human",
            "thought": "Collect the missing sample observation",
            "human_request": {
                "title": "Inspect sample label",
                "instructions": "Record whether the label is readable.",
                "completion_criteria": "The label state is recorded.",
                "evidence_kind": "observation",
                "fields": [
                    {
                        "key": "label_readable",
                        "label": "Label readable",
                        "value_type": "boolean",
                    }
                ],
            },
        }
    )
    added = []
    db_session = AsyncMock()
    db_session.add = added.append
    db_session.scalar.side_effect = [0, 0]
    monkeypatch.setattr(ResearchAction, "find_by", AsyncMock(return_value=None))
    monkeypatch.setattr(
        research_executor_bindings,
        "enforce_environment_binding_action_limit",
        AsyncMock(),
    )
    monkeypatch.setattr(research_runtime, "emit_research_event", AsyncMock())

    action = asyncio.run(
        research_runtime._materialize_aira_action(
            db_session,
            task=task,
            run=run,
            proposal=proposal,
            step_index=7,
            create_plan=False,
            action_graph={
                "id": "aira-action-graph:7:human",
                "type": "mixed_governed",
                "node_id": "inspect",
                "position": 2,
                "size": 2,
                "depends_on_count": 1,
                "dependency_count": 1,
                "result_bindings": [],
            },
            defer_activation=True,
        )
    )

    assert action.kind == "human_work_item"
    assert action.status == ResearchActionStatus.BLOCKED.value
    assert action.assignee_user_id == assignee_id
    assert action.requirements["human_review_required"] is True
    assert action.requirements["submission_contract"]["schema"] == (
        "airalogy.human-work-submission.v1"
    )
    assert not any(
        isinstance(item, research_runtime.ResearchHumanWorkItem) for item in added
    )


def test_governed_action_graph_releases_an_instrument_after_resource_completion(
    monkeypatch,
):
    run_id = uuid4()
    resource = _graph_action(
        run_id=run_id,
        node_id="reagent",
        position=1,
        size=2,
        status=ResearchActionStatus.COMPLETED.value,
        kind="resource_reservation",
        graph_type="mixed_governed",
    )
    instrument = _graph_action(
        run_id=run_id,
        node_id="incubator",
        position=2,
        size=2,
        depends_on_count=1,
        kind="instrument_job",
        graph_type="mixed_governed",
    )
    for action in (resource, instrument):
        action.input_data["action_graph"]["id"] = "aira-action-graph:8:physical"
    dependency = ResearchActionDependency(
        action_id=instrument.id,
        depends_on_action_id=resource.id,
        condition={"required_status": "completed", "on_unsatisfied": "skipped"},
    )
    task = ResearchTask(id=uuid4(), status=ResearchTaskStatus.ACTIVE.value)
    run = ResearchRun(id=run_id, status=ResearchRunStatus.WAITING_FOR_EVENT.value)
    db_session = AsyncMock()
    db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [resource, instrument]),
        SimpleNamespace(all=lambda: [dependency]),
    ]

    async def activate(*_args, action, **_kwargs):
        action.status = ResearchActionStatus.QUEUED.value

    monkeypatch.setattr(research_runtime, "_activate_released_graph_action", activate)
    monkeypatch.setattr(research_runtime, "emit_research_event", AsyncMock())

    settled = asyncio.run(
        research_runtime.hold_or_release_aira_action_group(
            db_session,
            task=task,
            run=run,
            action=resource,
        )
    )

    assert settled is False
    assert instrument.status == ResearchActionStatus.QUEUED.value
    assert run.status == ResearchRunStatus.WAITING_FOR_INSTRUMENT.value


def test_governed_action_graph_defers_service_quote_until_dependencies_complete(
    monkeypatch,
):
    run_id = uuid4()
    preparation = _graph_action(
        run_id=run_id,
        node_id="preparation",
        position=1,
        size=2,
        status=ResearchActionStatus.COMPLETED.value,
        kind="tool_job",
        graph_type="mixed_governed",
    )
    service = _graph_action(
        run_id=run_id,
        node_id="sequencing",
        position=2,
        size=2,
        depends_on_count=1,
        kind="external_service_job",
        graph_type="mixed_governed",
    )
    service.policy_decision = "ask"
    for action in (preparation, service):
        action.input_data["action_graph"]["id"] = "aira-action-graph:9:service"
    dependency = ResearchActionDependency(
        action_id=service.id,
        depends_on_action_id=preparation.id,
        condition={"required_status": "completed", "on_unsatisfied": "skipped"},
    )
    task = ResearchTask(id=uuid4(), status=ResearchTaskStatus.ACTIVE.value)
    run = ResearchRun(id=run_id, status=ResearchRunStatus.WAITING_FOR_TOOL.value)
    db_session = AsyncMock()
    db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [preparation, service]),
        SimpleNamespace(all=lambda: [dependency]),
    ]

    async def activate_service(*_args, action, **_kwargs):
        action.status = ResearchActionStatus.WAITING.value

    activate = AsyncMock(side_effect=activate_service)
    generic_approval = AsyncMock()
    monkeypatch.setattr(
        research_runtime,
        "_activate_aira_service_request",
        activate,
    )
    monkeypatch.setattr(
        research_runtime,
        "request_action_approval",
        generic_approval,
    )
    monkeypatch.setattr(research_runtime, "emit_research_event", AsyncMock())

    settled = asyncio.run(
        research_runtime.hold_or_release_aira_action_group(
            db_session,
            task=task,
            run=run,
            action=preparation,
        )
    )

    assert settled is False
    activate.assert_awaited_once()
    generic_approval.assert_not_awaited()
    assert service.status == ResearchActionStatus.WAITING.value
    assert run.status == ResearchRunStatus.WAITING_FOR_EVENT.value


def test_governed_action_graph_releases_protocol_assignment_only_after_dependencies(
    monkeypatch,
):
    run_id = uuid4()
    context = _graph_action(
        run_id=run_id,
        node_id="context",
        position=1,
        size=2,
        status=ResearchActionStatus.COMPLETED.value,
        kind="tool_job",
        graph_type="mixed_governed",
    )
    protocol = _graph_action(
        run_id=run_id,
        node_id="assay",
        position=2,
        size=2,
        depends_on_count=1,
        kind="protocol_run",
        graph_type="mixed_governed",
    )
    protocol.policy_decision = "ask"
    for action in (context, protocol):
        action.input_data["action_graph"]["id"] = "aira-action-graph:10:protocol"
    dependency = ResearchActionDependency(
        action_id=protocol.id,
        depends_on_action_id=context.id,
        condition={"required_status": "completed", "on_unsatisfied": "skipped"},
    )
    task = ResearchTask(
        id=uuid4(),
        owner_user_id=uuid4(),
        status=ResearchTaskStatus.ACTIVE.value,
        revision=1,
    )
    run = ResearchRun(
        id=run_id,
        requested_by_user_id=uuid4(),
        status=ResearchRunStatus.WAITING_FOR_TOOL.value,
    )
    db_session = AsyncMock()
    db_session.add = Mock()
    db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [context, protocol]),
        SimpleNamespace(all=lambda: [dependency]),
    ]
    approval = AsyncMock()
    activation = AsyncMock()
    monkeypatch.setattr(research_runtime, "request_action_approval", approval)
    monkeypatch.setattr(research_runtime, "activate_protocol_action", activation)
    monkeypatch.setattr(research_runtime, "emit_research_event", AsyncMock())

    settled = asyncio.run(
        research_runtime.hold_or_release_aira_action_group(
            db_session,
            task=task,
            run=run,
            action=context,
        )
    )

    assert settled is False
    assert protocol.status == ResearchActionStatus.PROPOSED.value
    approval.assert_awaited_once()
    activation.assert_not_awaited()
    assert run.status == ResearchRunStatus.WAITING_FOR_APPROVAL.value


def test_governed_graph_ignores_blocked_child_kind_for_waiting_state():
    run_id = uuid4()
    resource = _graph_action(
        run_id=run_id,
        node_id="reagent",
        position=1,
        size=2,
        status=ResearchActionStatus.WAITING.value,
        kind="resource_reservation",
        graph_type="mixed_governed",
    )
    protocol = _graph_action(
        run_id=run_id,
        node_id="assay",
        position=2,
        size=2,
        depends_on_count=1,
        kind="protocol_run",
        graph_type="mixed_governed",
    )
    for action in (resource, protocol):
        action.input_data["action_graph"]["id"] = "aira-action-graph:11:blocked"
    dependency = ResearchActionDependency(
        action_id=protocol.id,
        depends_on_action_id=resource.id,
        condition={"required_status": "completed", "on_unsatisfied": "skipped"},
    )
    task = ResearchTask(id=uuid4(), status=ResearchTaskStatus.ACTIVE.value)
    run = ResearchRun(id=run_id, status=ResearchRunStatus.RUNNING.value)
    db_session = AsyncMock()
    db_session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [resource, protocol]),
        SimpleNamespace(all=lambda: [dependency]),
    ]

    settled = asyncio.run(
        research_runtime.hold_or_release_aira_action_group(
            db_session,
            task=task,
            run=run,
            action=resource,
        )
    )

    assert settled is False
    assert protocol.status == ResearchActionStatus.BLOCKED.value
    assert run.status == ResearchRunStatus.WAITING_FOR_EVENT.value


def test_governed_service_release_failure_is_typed_and_auditable(monkeypatch):
    action = ResearchAction(
        id=uuid4(),
        kind="external_service_job",
        status=ResearchActionStatus.PROPOSED.value,
        input_data={"action_graph": {"id": "aira-action-graph:10:service"}},
        policy_decision="ask",
        revision=1,
    )
    job = ResearchServiceJob(
        id=uuid4(),
        action_id=action.id,
        status=ResearchServiceJobStatus.BLOCKED.value,
        revision=1,
    )
    task = ResearchTask(id=uuid4(), status=ResearchTaskStatus.ACTIVE.value)
    run = ResearchRun(id=uuid4(), aira_state={})
    event = AsyncMock()
    monkeypatch.setattr(
        research_runtime,
        "_activate_aira_service_request",
        AsyncMock(side_effect=ValueError("Pinned contract was revoked")),
    )
    monkeypatch.setattr(
        ResearchServiceJob,
        "find_by",
        AsyncMock(return_value=job),
    )
    monkeypatch.setattr(research_runtime, "emit_research_event", event)

    asyncio.run(
        research_runtime._activate_released_graph_action(
            AsyncMock(),
            task=task,
            run=run,
            action=action,
        )
    )

    assert action.status == ResearchActionStatus.FAILED.value
    assert job.status == ResearchServiceJobStatus.FAILED.value
    assert "revoked" in action.error
    assert run.aira_state["service_results"][0]["status"] == "failed"
    event.assert_awaited_once()
    assert event.await_args.kwargs["kind"] == "external_service.release_failed"


def test_delayed_graph_action_rechecks_expired_autonomy_grant(monkeypatch):
    target = tool_autonomy_target("project.summary", "1")
    policy_snapshot = policy_snapshot_with_grants(
        autonomy_policy_snapshot(None),
        [
            {
                "enabled": True,
                "target": target,
                "allowed_levels": ["bounded_autopilot"],
                "valid_until": "2020-01-01T00:00:00+00:00",
            }
        ],
    )
    action = ResearchAction(
        id=uuid4(),
        kind=ResearchActionKind.TOOL_JOB.value,
        status=ResearchActionStatus.PROPOSED.value,
        executor_type="platform_tool",
        input_data={"source": "aira"},
        requirements={
            "risk": "read_only",
            "approval_policy": "allow_read_only",
            "autonomy_target": target,
        },
        policy_decision="allow",
        policy_reason="Previously allowed",
        preview_digest="a" * 64,
        revision=1,
    )
    task = ResearchTask(
        id=uuid4(),
        owner_user_id=uuid4(),
        status=ResearchTaskStatus.ACTIVE.value,
        autonomy_level="bounded_autopilot",
        revision=1,
    )
    run = ResearchRun(
        id=uuid4(),
        requested_by_user_id=uuid4(),
        environment_snapshot={"autonomy_policy": policy_snapshot},
    )
    approval = AsyncMock()
    activation = AsyncMock()
    event = AsyncMock()
    monkeypatch.setattr(research_runtime, "request_action_approval", approval)
    monkeypatch.setattr(research_runtime, "activate_tool_action", activation)
    monkeypatch.setattr(research_runtime, "emit_research_event", event)

    asyncio.run(
        research_runtime._activate_released_graph_action(
            AsyncMock(),
            task=task,
            run=run,
            action=action,
        )
    )

    assert action.policy_decision == "ask"
    assert "expired" in action.policy_reason
    assert action.revision == 2
    approval.assert_awaited_once()
    assert approval.await_args.kwargs["reason"] == action.policy_reason
    activation.assert_not_awaited()
    event.assert_awaited_once()
    assert event.await_args.kwargs["kind"] == "action.policy_revalidated"
    assert event.await_args.kwargs["payload"]["boundary"] == "dependency_release"


def test_dependency_skip_cancels_typed_governed_executions(monkeypatch):
    protocol_action = ResearchAction(id=uuid4(), kind="protocol_run", input_data={})
    resource_action = ResearchAction(
        id=uuid4(), kind="resource_reservation", input_data={}
    )
    instrument_action = ResearchAction(id=uuid4(), kind="instrument_job", input_data={})
    service_action = ResearchAction(
        id=uuid4(), kind="external_service_job", input_data={}
    )
    reservation = ResearchResourceReservation(
        action_id=resource_action.id,
        status=ResearchResourceReservationStatus.PROPOSED.value,
        revision=1,
    )
    instrument_job = ResearchInstrumentJob(
        action_id=instrument_action.id,
        status=ResearchInstrumentJobStatus.QUEUED.value,
        revision=1,
    )
    service_job = ResearchServiceJob(
        action_id=service_action.id,
        status=ResearchServiceJobStatus.BLOCKED.value,
        revision=1,
    )
    protocol_run = ResearchProtocolRun(
        action_id=protocol_action.id,
        protocol_id=uuid4(),
        protocol_version_id=uuid4(),
        protocol_version="1.0.0",
    )
    monkeypatch.setattr(
        ResearchProtocolRun,
        "find_by",
        AsyncMock(return_value=protocol_run),
    )
    monkeypatch.setattr(
        ResearchResourceReservation,
        "find_by",
        AsyncMock(return_value=reservation),
    )
    monkeypatch.setattr(
        ResearchInstrumentJob,
        "find_by",
        AsyncMock(return_value=instrument_job),
    )
    monkeypatch.setattr(
        ResearchServiceJob,
        "find_by",
        AsyncMock(return_value=service_job),
    )

    asyncio.run(
        research_runtime._cancel_blocked_graph_action(
            AsyncMock(),
            action=protocol_action,
            error="Dependency failed",
            completed_at=research_runtime.utcnow(),
        )
    )
    asyncio.run(
        research_runtime._cancel_blocked_graph_action(
            AsyncMock(),
            action=resource_action,
            error="Dependency failed",
            completed_at=research_runtime.utcnow(),
        )
    )
    asyncio.run(
        research_runtime._cancel_blocked_graph_action(
            AsyncMock(),
            action=service_action,
            error="Dependency failed",
            completed_at=research_runtime.utcnow(),
        )
    )
    asyncio.run(
        research_runtime._cancel_blocked_graph_action(
            AsyncMock(),
            action=instrument_action,
            error="Dependency failed",
            completed_at=research_runtime.utcnow(),
        )
    )

    assert reservation.status == ResearchResourceReservationStatus.CANCELLED.value
    assert reservation.revision == 2
    assert instrument_job.status == ResearchInstrumentJobStatus.CANCELLED.value
    assert instrument_job.error == "Dependency failed"
    assert instrument_job.completed_at is not None
    assert instrument_job.revision == 2
    assert service_job.status == ResearchServiceJobStatus.CANCELLED.value
    assert service_job.error == "Dependency failed"
    assert service_job.completed_at is not None
    assert service_job.revision == 2
