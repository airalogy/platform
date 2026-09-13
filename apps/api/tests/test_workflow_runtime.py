"""Fixed Workflow execution reuses the governed Action lifecycle without AI."""

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.models.research import (
    ResearchAction,
    ResearchActionDependency,
    ResearchProtocolRun,
    ResearchRun,
    ResearchTask,
)
from app.services import research_runtime as runtime
from app.services.research_action_contracts import ProtocolActionDraft
from app.services.workflow_contracts import (
    validate_workflow_graph,
    workflow_revision_digest,
)


@pytest.fixture(autouse=True)
def isolated_graph_integrity(monkeypatch):
    # These tests isolate scheduling. The real PostgreSQL suite exercises the
    # immutable Workflow/Plan/Run/Protocol integrity verifier with actual rows.
    monkeypatch.setattr(runtime, "verify_manual_workflow_execution", AsyncMock())


def context():
    task = ResearchTask(
        id=uuid4(),
        project_id=uuid4(),
        owner_user_id=uuid4(),
        status="active",
        revision=1,
    )
    run = ResearchRun(
        id=uuid4(),
        task_id=task.id,
        status="running",
        requested_by_user_id=task.owner_user_id,
        environment_snapshot={
            "manual_workflow": {"revision_id": str(uuid4()), "digest": "a" * 64}
        },
    )
    return task, run


def node(run, name, size, edges, parents=0, status="blocked"):
    return ResearchAction(
        id=uuid4(),
        run_id=run.id,
        sequence=1,
        plan_version=1,
        kind="protocol_run",
        status=status,
        revision=1,
        policy_decision="allow",
        title=name,
        description="",
        executor_type="human",
        assignee_user_id=run.requested_by_user_id,
        requirements={},
        preview_digest="a" * 64,
        input_data={
            "source": "manual_workflow",
            "initial_values": {},
            "action_graph": {
                "id": "workflow:test",
                "type": "manual_workflow",
                "node_id": name,
                "size": size,
                "dependency_count": edges,
                "depends_on_count": parents,
            },
        },
    )


@pytest.mark.parametrize("size", [1, 2, 4])
def test_single_and_independent_protocol_roots_use_existing_barrier(monkeypatch, size):
    task, run = context()
    actions = [node(run, f"node_{i}", size, 0) for i in range(size)]
    db = AsyncMock()
    db.scalars.side_effect = [
        SimpleNamespace(all=lambda: actions),
        SimpleNamespace(all=list),
    ]
    monkeypatch.setattr(
        runtime, "manual_workflow_dispatch_allowed", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(runtime, "emit_research_event", AsyncMock())

    async def activate(*args, action, **kwargs):
        action.status = "waiting"

    activation = AsyncMock(side_effect=activate)
    monkeypatch.setattr(runtime, "_activate_released_graph_action", activation)
    assert not asyncio.run(
        runtime.hold_or_release_aira_action_group(
            db, task=task, run=run, action=actions[0]
        )
    )
    assert activation.await_count == size
    assert run.status == "waiting_for_human"


def test_sequence_releases_only_after_real_parent_completion(monkeypatch):
    task, run = context()
    parent = node(run, "first", 2, 1, status="waiting")
    child = node(run, "second", 2, 1, parents=1)
    dependency = ResearchActionDependency(
        action_id=child.id,
        depends_on_action_id=parent.id,
        condition={"required_status": "completed", "on_unsatisfied": "skipped"},
    )
    db = AsyncMock()
    db.scalars.side_effect = [
        SimpleNamespace(all=lambda: [parent, child]),
        SimpleNamespace(all=lambda: [dependency]),
    ] * 2
    monkeypatch.setattr(
        runtime, "manual_workflow_dispatch_allowed", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(runtime, "emit_research_event", AsyncMock())

    async def activate(*args, action, **kwargs):
        action.status = "waiting"

    activation = AsyncMock(side_effect=activate)
    monkeypatch.setattr(runtime, "_activate_released_graph_action", activation)
    asyncio.run(
        runtime.hold_or_release_aira_action_group(db, task=task, run=run, action=parent)
    )
    activation.assert_not_awaited()
    parent.status = "completed"
    asyncio.run(
        runtime.hold_or_release_aira_action_group(db, task=task, run=run, action=parent)
    )
    assert activation.await_count == 1
    assert child.status == "waiting"


def test_fixed_graph_completion_never_requests_planner_continuation(monkeypatch):
    task, run = context()
    action = node(run, "only", 1, 0, status="completed")
    db = AsyncMock()
    db.scalars.side_effect = [
        SimpleNamespace(all=lambda: [action]),
        SimpleNamespace(all=list),
    ]
    monkeypatch.setattr(
        runtime, "manual_workflow_dispatch_allowed", AsyncMock(return_value=True)
    )
    finish = AsyncMock()
    monkeypatch.setattr(runtime, "finish_manual_workflow", finish)
    assert not asyncio.run(
        runtime.hold_or_release_aira_action_group(db, task=task, run=run, action=action)
    )
    finish.assert_awaited_once()


@pytest.mark.parametrize("status", ["paused", "cancelled"])
def test_paused_cancelled_workflow_never_releases_cards(monkeypatch, status):
    task, run = context()
    task.status = status
    run.status = status
    action = node(run, "only", 1, 0)
    db = AsyncMock()
    db.scalars.return_value = SimpleNamespace(all=lambda: [action])
    activation = AsyncMock()
    monkeypatch.setattr(runtime, "_activate_released_graph_action", activation)
    assert not asyncio.run(
        runtime.hold_or_release_aira_action_group(db, task=task, run=run, action=action)
    )
    activation.assert_not_awaited()


def test_revoked_requester_pauses_before_downstream_dispatch(monkeypatch):
    task, run = context()
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=task.owner_user_id)
    monkeypatch.setattr(
        runtime, "has_research_capability", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        runtime, "reached_operational_limit", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(runtime, "emit_research_event", AsyncMock())
    assert not asyncio.run(
        runtime.manual_workflow_dispatch_allowed(db, task=task, run=run)
    )
    assert task.status == run.status == "paused"


def test_pinned_workflow_cannot_enqueue_or_call_ai(monkeypatch):
    task, run = context()
    db = AsyncMock()
    with pytest.raises(ValueError, match="cannot enqueue"):
        asyncio.run(runtime.enqueue_research_advance(db, task=task, run=run))
    db.flush.assert_not_awaited()
    monkeypatch.setattr(
        runtime,
        "_load_run_context",
        AsyncMock(return_value=(run, task, None, None, [])),
    )
    planner = AsyncMock(side_effect=AssertionError("No model transport may run"))
    monkeypatch.setattr(runtime, "plan_next_research_action", planner)
    assert asyncio.run(
        runtime.process_research_run_advance(db, run_id=run.id, generation=0)
    )["fixed_workflow"]
    planner.assert_not_awaited()


def test_repeated_protocol_cards_materialize_distinct_non_ai_occurrences(monkeypatch):
    task, run = context()
    protocol_id, version_id, revision_id = uuid4(), uuid4(), uuid4()
    graph = validate_workflow_graph(
        {
            "nodes": [
                {
                    "node_id": name,
                    "kind": "protocol",
                    "protocol_id": str(protocol_id),
                    "protocol_version_id": str(version_id),
                }
                for name in ["first", "second"]
            ],
            "edges": [
                {
                    "edge_id": "next",
                    "source_node_id": "first",
                    "target_node_id": "second",
                }
            ],
        }
    )
    digest = workflow_revision_digest(graph)
    run.environment_snapshot = {
        "manual_workflow": {"revision_id": str(revision_id), "digest": digest}
    }
    db = AsyncMock()
    db.add = Mock()
    db.scalars.return_value = SimpleNamespace(all=list)
    drafts = []

    async def materialize(*args, **kwargs):
        drafts.append(kwargs)
        return ResearchAction(id=uuid4(), sequence=len(drafts))

    monkeypatch.setattr(runtime, "_materialize_governed_action", materialize)
    monkeypatch.setattr(runtime, "create_plan_version", AsyncMock())
    monkeypatch.setattr(runtime, "emit_research_event", AsyncMock())
    monkeypatch.setattr(
        runtime, "hold_or_release_aira_action_group", AsyncMock(return_value=False)
    )
    actions = asyncio.run(
        runtime.materialize_manual_workflow(
            db,
            task=task,
            run=run,
            graph=graph,
            workflow_revision_id=revision_id,
            workflow_digest=digest,
        )
    )
    assert actions[0].id != actions[1].id
    assert all(isinstance(item["proposal"], ProtocolActionDraft) for item in drafts)
    assert all(
        item["source"] == "manual_workflow" and item["defer_activation"]
        for item in drafts
    )
    assert (
        drafts[0]["idempotency_key_override"] != drafts[1]["idempotency_key_override"]
    )
    dependency = next(
        call.args[0]
        for call in db.add.call_args_list
        if isinstance(call.args[0], ResearchActionDependency)
    )
    assert dependency.action_id == actions[1].id
    assert dependency.depends_on_action_id == actions[0].id


@pytest.mark.parametrize(
    "approval,expected", [("deny", "deny"), ("always_ask", "ask"), ("allowed", "allow")]
)
def test_manual_workflow_keeps_explicit_executor_policy(approval, expected):
    assert (
        runtime.evaluate_research_action_policy(
            autonomy_level="assisted",
            source="manual_workflow",
            executor_type="human",
            requirements={"approval_policy": approval},
        )[0]
        == expected
    )


def test_protocol_record_receipt_is_json_safe_before_database_autoflush():
    from app.models.record import Record
    from app.routers.research_tasks import _record_payload

    created_at = datetime(2026, 9, 13, 10, 20, tzinfo=UTC)
    protocol_id = uuid4()
    record = Record(
        id=uuid4(),
        version=2,
        protocol_id=protocol_id,
        protocol_version="1.0.0",
        user_id=uuid4(),
        number=3,
        created_at=created_at,
        hash="record-hash",
        data={"var": {"reading": 4.5}},
        report="Validated result",
    )
    payload = _record_payload(
        record=record,
        protocol=SimpleNamespace(id=protocol_id, uid="method"),
        protocol_version=SimpleNamespace(protocol_version="1.0.0"),
        project=SimpleNamespace(uid="project"),
        lab=SimpleNamespace(uid="lab"),
        user=SimpleNamespace(username="researcher"),
    )
    # Exercise the same serializer as SQLAlchemy JSON instead of FastAPI's
    # response conversion, which happens too late for persisted receipts.
    assert json.loads(json.dumps(payload)) == payload
    assert (
        payload["metadata"]["record_current_version_submission_time"]
        == created_at.isoformat()
    )
    assert payload["data"] == record.data
    assert record.created_at == created_at


def test_shared_result_package_is_json_safe_before_completion_autoflush(monkeypatch):
    task, run = context()
    task.goal = "Preserve exact reproducible results"
    task.success_criteria = ["Validated evidence"]
    run.aira_state = {}
    run.plan_version = 2
    recorded_at = datetime(2026, 9, 13, 10, 20, tzinfo=UTC)
    asset_id = uuid4()
    exact = Decimal("123456789.123456789123456789")
    assets = {
        "claims": [],
        "evidence": [],
        "knowledge_items": [],
        "protocol_improvements": [],
        "data_assets": [
            {
                "id": asset_id,
                "created_at": recorded_at,
                "metadata": {"measurement": exact},
            }
        ],
    }
    db = AsyncMock()
    db.scalars.return_value = SimpleNamespace(all=list)
    monkeypatch.setattr(
        runtime, "research_asset_bundle", AsyncMock(return_value=assets)
    )
    monkeypatch.setattr(
        runtime, "research_budget_snapshot", AsyncMock(return_value={"actual": exact})
    )
    package = asyncio.run(runtime.build_research_result_package(db, task=task, run=run))
    assert json.loads(json.dumps(package)) == package
    assert package["data_assets"] == [
        {
            "id": str(asset_id),
            "created_at": recorded_at.isoformat(),
            "metadata": {"measurement": str(exact)},
        }
    ]
    assert package["budget"]["actual"] == str(exact)
    assert assets["data_assets"][0]["id"] == asset_id
    assert assets["data_assets"][0]["metadata"]["measurement"] == exact


def v2_graph(*, bound=False):
    protocol_id, version_id = uuid4(), uuid4()
    return validate_workflow_graph(
        {
            "nodes": [
                {
                    "node_id": name,
                    "kind": "protocol",
                    "protocol_id": str(protocol_id),
                    "protocol_version_id": str(version_id),
                }
                for name in ["source", "target"]
            ],
            "edges": [
                {
                    "edge_id": "next",
                    "source_node_id": "source",
                    "target_node_id": "target",
                }
            ],
            "bindings": [
                {
                    "binding_id": "reading",
                    "source_node_id": "source",
                    "source_path": ["var", "reading"],
                    "target_node_id": "target",
                    "target_path": ["var", "reading"],
                    "value_type": "number",
                    "cardinality": "one",
                }
            ]
            if bound
            else [],
        }
    )


def resolution_row(state="ready", values=None):
    return SimpleNamespace(
        id=uuid4(),
        state=state,
        digest="b" * 64,
        initial_values=values or {},
        receipt={"error": None},
    )


@pytest.mark.parametrize("bound", [False, True])
def test_v2_resolved_input_is_sealed_before_activation_and_binding_requires_approval(
    monkeypatch, bound
):
    from app.services import workflow_resolutions

    task, run = context()
    graph = v2_graph(bound=bound)
    action = node(run, "target", 2, 1, parents=1)
    typed_run = SimpleNamespace(initial_values={})
    result = resolution_row(values={"reading": 7.25} if bound else {})
    resolver = AsyncMock(return_value=result)
    monkeypatch.setattr(workflow_resolutions, "resolve_workflow_node", resolver)
    monkeypatch.setattr(
        ResearchProtocolRun, "find_by", AsyncMock(return_value=typed_run)
    )
    event = AsyncMock()
    monkeypatch.setattr(runtime, "emit_research_event", event)
    db = AsyncMock()

    async def apply():
        return await runtime._resolve_fixed_workflow_candidate(
            db,
            task=task,
            run=run,
            graph=graph,
            node=graph.nodes[1],
            action=action,
            parents_by_node={},
        )

    assert asyncio.run(apply())
    assert (
        action.input_data["initial_values"]
        == typed_run.initial_values
        == result.initial_values
    )
    assert action.input_data["workflow_resolution"]["digest"] == result.digest
    assert action.preview_digest != "a" * 64
    assert action.status == "blocked"  # Resolution itself cannot assign execution.
    if bound:
        assert action.policy_decision == "ask"
        assert action.requirements["approval_policy"] == "always_ask"
        assert action.requirements["workflow_bound_input_confirmation"] is True
    else:
        assert action.policy_decision == "allow"
    revision = action.revision
    assert asyncio.run(apply())
    assert action.revision == revision
    event.assert_awaited_once()  # Resume reuses the receipt, never re-applies it.


@pytest.mark.parametrize(
    "state,status,successful",
    [
        ("branch_not_selected", "skipped", True),
        ("blocked", "skipped", False),
        ("failed", "failed", False),
    ],
)
def test_v2_nonselected_branch_is_distinct_from_failed_dependency(
    monkeypatch, state, status, successful
):
    from app.services import workflow_resolutions

    task, run = context()
    run.environment_snapshot["manual_workflow"]["execution_contract_version"] = 2
    graph = v2_graph()
    action = node(run, "target", 2, 1, parents=1)
    result = resolution_row(state)
    monkeypatch.setattr(
        workflow_resolutions, "resolve_workflow_node", AsyncMock(return_value=result)
    )
    typed = SimpleNamespace(initial_values={})
    monkeypatch.setattr(ResearchProtocolRun, "find_by", AsyncMock(return_value=typed))
    monkeypatch.setattr(runtime, "emit_research_event", AsyncMock())
    monkeypatch.setattr(
        runtime,
        "build_research_result_package",
        AsyncMock(return_value={"schema": "test"}),
    )
    db = AsyncMock()
    assert not asyncio.run(
        runtime._resolve_fixed_workflow_candidate(
            db,
            task=task,
            run=run,
            graph=graph,
            node=graph.nodes[1],
            action=action,
            parents_by_node={},
        )
    )
    assert action.status == status
    assert typed.validation_status == state
    assert runtime._workflow_branch_not_selected(action) is successful
    parent = node(run, "source", 2, 1, status="completed")
    asyncio.run(
        runtime.finish_manual_workflow(db, task=task, run=run, actions=[parent, action])
    )
    assert run.status == ("completed" if successful else "failed")
    assert task.status == "review_required"


def test_v2_waits_for_all_incoming_parents_before_any_resolution(monkeypatch):
    task, run = context()
    run.environment_snapshot["manual_workflow"]["execution_contract_version"] = 2
    parents = [
        node(run, "failed", 3, 2, status="failed"),
        node(run, "pending", 3, 2, status="waiting"),
    ]
    target = node(run, "target", 3, 2, parents=2)
    actions = [*parents, target]
    dependencies = [
        ResearchActionDependency(
            action_id=target.id, depends_on_action_id=parent.id, condition={}
        )
        for parent in parents
    ]
    db = AsyncMock()
    db.scalars.side_effect = [
        SimpleNamespace(all=lambda: actions),
        SimpleNamespace(all=lambda: dependencies),
    ]
    monkeypatch.setattr(
        runtime,
        "verify_manual_workflow_execution",
        AsyncMock(
            return_value=SimpleNamespace(nodes=[SimpleNamespace(node_id="target")])
        ),
    )
    monkeypatch.setattr(
        runtime, "manual_workflow_dispatch_allowed", AsyncMock(return_value=True)
    )
    resolve = AsyncMock()
    monkeypatch.setattr(runtime, "_resolve_fixed_workflow_candidate", resolve)
    asyncio.run(
        runtime.hold_or_release_aira_action_group(db, task=task, run=run, action=target)
    )
    resolve.assert_not_awaited()
    assert target.status == "blocked"
    assert run.status == "waiting_for_human"


def test_v2_active_join_releases_despite_an_unselected_branch(monkeypatch):
    task, run = context()
    run.environment_snapshot["manual_workflow"]["execution_contract_version"] = 2
    parents = [
        node(run, "selected", 3, 2, status="completed"),
        node(run, "unselected", 3, 2, status="skipped"),
    ]
    target = node(run, "target", 3, 2, parents=2)
    actions = [*parents, target]
    dependencies = [
        ResearchActionDependency(
            action_id=target.id, depends_on_action_id=parent.id, condition={}
        )
        for parent in parents
    ]
    db = AsyncMock()
    db.scalars.side_effect = [
        SimpleNamespace(all=lambda: actions),
        SimpleNamespace(all=lambda: dependencies),
    ]
    monkeypatch.setattr(
        runtime,
        "verify_manual_workflow_execution",
        AsyncMock(
            return_value=SimpleNamespace(nodes=[SimpleNamespace(node_id="target")])
        ),
    )
    monkeypatch.setattr(
        runtime, "manual_workflow_dispatch_allowed", AsyncMock(return_value=True)
    )
    resolve = AsyncMock(return_value=True)
    monkeypatch.setattr(runtime, "_resolve_fixed_workflow_candidate", resolve)
    monkeypatch.setattr(runtime, "emit_research_event", AsyncMock())

    async def activate(*args, action, **kwargs):
        action.status = "waiting"

    activation = AsyncMock(side_effect=activate)
    monkeypatch.setattr(runtime, "_activate_released_graph_action", activation)
    asyncio.run(
        runtime.hold_or_release_aira_action_group(db, task=task, run=run, action=target)
    )
    resolve.assert_awaited_once()
    activation.assert_awaited_once()
    assert target.status == "waiting"


def test_v2_resolution_permission_failure_pauses_without_scientific_failure(
    monkeypatch,
):
    from fastapi import HTTPException

    task, run = context()
    run.environment_snapshot["manual_workflow"]["execution_contract_version"] = 2
    source = node(run, "source", 2, 1, status="completed")
    target = node(run, "target", 2, 1, parents=1)
    dependency = ResearchActionDependency(
        action_id=target.id, depends_on_action_id=source.id, condition={}
    )
    db = AsyncMock()
    db.scalars.side_effect = [
        SimpleNamespace(all=lambda: [source, target]),
        SimpleNamespace(all=lambda: [dependency]),
    ]
    monkeypatch.setattr(
        runtime, "verify_manual_workflow_execution", AsyncMock(return_value=v2_graph())
    )
    monkeypatch.setattr(
        runtime, "manual_workflow_dispatch_allowed", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        runtime,
        "_resolve_fixed_workflow_candidate",
        AsyncMock(side_effect=HTTPException(403, "Source revoked")),
    )
    monkeypatch.setattr(runtime, "emit_research_event", AsyncMock())
    assert not asyncio.run(
        runtime.hold_or_release_aira_action_group(db, task=task, run=run, action=source)
    )
    assert task.status == run.status == "paused"
    assert target.status == "blocked"
    assert source.status == "completed"
    assert target.error is None
