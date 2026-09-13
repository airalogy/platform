"""Focused lifecycle adapter tests; real SQL/ACL/worker flow is covered in PG."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.models.analysis import AnalysisRun
from app.models.research import ResearchAction, ResearchRun, ResearchTask
from app.models.workflow_analysis import ResearchAnalysisAction
from app.services import research_runtime
from app.services import workflow_analysis_runtime as adapter
from app.services.persistent_jobs import JobDeferred
from app.services.workflow_contracts import validate_workflow_graph


def context():
    owner = uuid4()
    task = ResearchTask(
        id=uuid4(), project_id=uuid4(), owner_user_id=owner, status="active", revision=1
    )
    run = ResearchRun(
        id=uuid4(),
        task_id=task.id,
        requested_by_user_id=owner,
        status="waiting_for_compute",
        plan_version=1,
    )
    action = ResearchAction(
        id=uuid4(),
        run_id=run.id,
        kind="analysis_run",
        assignee_user_id=owner,
        status="queued",
        revision=1,
    )
    bridge = ResearchAnalysisAction(
        action_id=action.id,
        method_publication_id=uuid4(),
        analysis_run_id=uuid4(),
        source_digest="a" * 64,
        input_snapshot={},
    )
    analysis = AnalysisRun(id=bridge.analysis_run_id, status="pending")
    return task, run, action, bridge, analysis


def test_analysis_card_only_materializes_governed_action_before_actual_input_approval(
    monkeypatch,
):
    task, run, _, bridge, _ = context()
    graph = validate_workflow_graph(
        {
            "schema_version": 2,
            "nodes": [
                {
                    "node_id": "source",
                    "kind": "protocol",
                    "protocol_id": str(uuid4()),
                    "protocol_version_id": str(uuid4()),
                },
                {
                    "node_id": "analysis",
                    "kind": "analysis",
                    "method_publication_id": str(bridge.method_publication_id),
                    "record_sources": [
                        {"source_node_id": "source", "cardinality": "one"}
                    ],
                    "input_policy": "all_declared",
                    "analysis_outputs": [],
                },
            ],
            "edges": [
                {
                    "edge_id": "source_analysis",
                    "source_node_id": "source",
                    "target_node_id": "analysis",
                }
            ],
        }
    )
    node = graph.nodes[1]
    method = SimpleNamespace(
        id=bridge.method_publication_id,
        title="Exact method",
        digest="b" * 64,
        engine_version=adapter.ENGINE_VERSION,
        recipe={"kind": "builtin"},
    )
    monkeypatch.setattr(adapter, "method_for_node", AsyncMock(return_value=method))
    monkeypatch.setattr(
        research_runtime, "_next_action_sequence", AsyncMock(return_value=2)
    )
    db = AsyncMock()
    db.add = Mock()
    result = asyncio.run(
        adapter.materialize_analysis_card(
            db,
            task=task,
            run=run,
            node=node,
            graph_meta={"id": "fixed", "node_id": "analysis"},
            idempotency_key="fixed:analysis",
        )
    )
    assert result.kind == "analysis_run" and result.executor_type == "internal"
    assert result.status == "blocked" and result.policy_decision == "ask"
    assert result.requirements["approval_policy"] == "always_ask"
    assert len(result.preview_digest) == 64
    added = [call.args[0] for call in db.add.call_args_list]
    assert [type(item) for item in added] == [ResearchAction, ResearchAnalysisAction]
    assert added[1].analysis_run_id is None and added[1].analysis_preview_id is None


def test_analysis_all_declared_policy_never_shrinks_inactive_inputs():
    task, run, action, _, _ = context()
    node = SimpleNamespace(
        record_sources=[
            SimpleNamespace(source_node_id="a"),
            SimpleNamespace(source_node_id="b"),
        ]
    )
    db = AsyncMock()
    with pytest.raises(ValueError, match="partial samples are forbidden"):
        asyncio.run(
            adapter.prepare_analysis_inputs(
                db,
                task=task,
                run=run,
                graph=None,
                node=node,
                action=action,
                parents_by_node={},
                active_nodes={"a"},
            )
        )
    db.get.assert_not_awaited()


def test_paused_analysis_keeps_same_pending_job_without_running(monkeypatch):
    task, run, action, bridge, analysis = context()
    task.status = "paused"
    monkeypatch.setattr(
        adapter,
        "workflow_analysis_context",
        AsyncMock(return_value=(task, run, action, bridge)),
    )
    verify = AsyncMock()
    monkeypatch.setattr(adapter, "verify_analysis_execution", verify)
    db = AsyncMock()
    db.get.return_value = analysis
    with pytest.raises(JobDeferred, match="paused"):
        asyncio.run(adapter.before_workflow_analysis_execution(db, analysis.id))
    assert action.status == "queued" and analysis.status == "pending"
    verify.assert_not_awaited()


def test_cancelled_task_discards_late_analysis_without_resurrecting_action(monkeypatch):
    task, run, action, bridge, analysis = context()
    task.status = run.status = action.status = "cancelled"
    analysis.status = "running"
    monkeypatch.setattr(
        adapter,
        "workflow_analysis_context",
        AsyncMock(return_value=(task, run, action, bridge)),
    )
    cancel = AsyncMock()
    monkeypatch.setattr(adapter, "cancel_analysis", cancel)
    db = AsyncMock()
    db.get.return_value = analysis
    assert (
        asyncio.run(
            adapter.before_workflow_analysis_execution(db, analysis.id, finishing=True)
        )
        is False
    )
    cancel.assert_awaited_once_with(db, analysis)
    assert action.status == "cancelled"


def test_terminal_analysis_retry_does_not_reset_completed_action(monkeypatch):
    task, run, action, bridge, analysis = context()
    task.status = "completed"
    analysis.status = "succeeded"
    action.status = "completed"
    monkeypatch.setattr(
        adapter,
        "workflow_analysis_context",
        AsyncMock(return_value=(task, run, action, bridge)),
    )
    db = AsyncMock()
    db.get.return_value = analysis
    assert (
        asyncio.run(adapter.before_workflow_analysis_execution(db, analysis.id)) is True
    )
    assert action.status == "completed" and action.revision == 1


def test_completed_analysis_recovery_reconciles_existing_barrier(monkeypatch):
    task, run, action, bridge, analysis = context()
    analysis.status = "succeeded"
    action.status = "completed"
    monkeypatch.setattr(
        adapter,
        "workflow_analysis_context",
        AsyncMock(return_value=(task, run, action, bridge)),
    )
    barrier = AsyncMock()
    monkeypatch.setattr(research_runtime, "hold_or_release_aira_action_group", barrier)
    db = AsyncMock()
    asyncio.run(adapter.sync_workflow_analysis(db, analysis))
    barrier.assert_awaited_once_with(db, task=task, run=run, action=action)
    assert action.revision == 1


def test_ordinary_private_analysis_does_not_acquire_workflow_semantics(monkeypatch):
    monkeypatch.setattr(
        adapter, "workflow_analysis_context", AsyncMock(return_value=None)
    )
    db = AsyncMock()
    assert asyncio.run(adapter.before_workflow_analysis_execution(db, uuid4())) is True
    db.get.assert_not_awaited()


@pytest.mark.parametrize("exists", [False, True])
def test_recovery_distinguishes_missing_analysis_from_a_locked_row(monkeypatch, exists):
    from app.services.resource_job_worker import _lock_record_analysis_job_context

    monkeypatch.setattr(
        adapter, "workflow_analysis_context", AsyncMock(return_value=None)
    )
    identity = uuid4()
    job = SimpleNamespace(id=uuid4(), payload={"analysis_id": str(identity)})
    db = AsyncMock()
    db.scalar.side_effect = [None, identity if exists else None]
    if exists:
        with pytest.raises(JobDeferred, match="locked"):
            asyncio.run(_lock_record_analysis_job_context(db, job, skip_locked=True))
    else:
        assert (
            asyncio.run(_lock_record_analysis_job_context(db, job, skip_locked=True))
            is None
        )
