"""Focused Project Workflow adaptation; no database or alternate worker required."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.models.analysis import AnalysisRun
from app.models.project import Project
from app.models.protocol_version import ProtocolVersion
from app.models.user import User
from app.models.workflow_analysis import ResearchAnalysisAction
from app.services import workflow_analysis_runtime as runtime
from app.services import workflow_project_analysis as project_runtime
from app.services.analysis_engine import canonical_digest
from app.services.project_analysis_engine import ENGINE_VERSION
from app.services.workflow_contracts import validate_workflow_graph
from tests.test_project_analysis_engine import project_fixture
from tests.test_workflow_project_analysis_contracts import graph, method_contract


def inputs():
    recipe, snapshot = project_fixture()
    contract = method_contract(recipe, snapshot)
    workflow = validate_workflow_graph(graph())
    node = workflow.nodes[-1]
    project = SimpleNamespace(id=UUID(snapshot["project_id"]), name="Synthetic Project")
    user = SimpleNamespace(id=uuid4())
    task = SimpleNamespace(id=uuid4(), project_id=project.id, owner_user_id=user.id)
    run = SimpleNamespace(id=uuid4(), requested_by_user_id=user.id)
    action = SimpleNamespace(id=uuid4(), assignee_user_id=user.id, input_data={})
    bridge = SimpleNamespace(source_digest=None, input_snapshot={})
    method = SimpleNamespace(
        id=node.method_publication_id,
        protocol_id=None,
        recipe=recipe.model_dump(mode="json"),
        project_contract=contract,
        digest="a" * 64,
        engine_version=ENGINE_VERSION,
    )
    versions = {
        UUID(version["id"]): SimpleNamespace(
            id=UUID(version["id"]),
            protocol_id=UUID(slot["protocol_id"]),
            **{key: deepcopy(value) for key, value in version.items() if key != "id"},
        )
        for slot in contract["slots"]
        for version in slot["versions"]
    }
    slots = {item["slot_id"]: item["snapshot"] for item in snapshot["inputs"]}
    slots["treatment"]["records"][1]["record_version"] = 2
    assignments = {
        "treatment_first": slots["treatment"]["records"][0],
        "treatment_second": slots["treatment"]["records"][1],
        "assay": slots["assay"]["records"][0],
    }
    parents = {
        node_id: SimpleNamespace(
            id=uuid4(),
            kind="protocol_run",
            status="completed",
            output_data={
                "record": {
                    "record_id": record["record_id"],
                    "record_version": record["record_version"],
                }
            },
        )
        for node_id, record in assignments.items()
    }
    db = AsyncMock()

    async def get(model, identity, **_kwargs):
        if model is ProtocolVersion:
            return versions.get(identity)
        if model is User:
            return user if identity == user.id else None
        if model is Project:
            return project if identity == project.id else None
        if model is ResearchAnalysisAction:
            return bridge if identity == action.id else None
        raise AssertionError(f"Unexpected model read: {model}")

    db.get.side_effect = get
    return SimpleNamespace(
        recipe=recipe,
        snapshot=snapshot,
        method=method,
        graph=workflow,
        node=node,
        project=project,
        user=user,
        task=task,
        run=run,
        action=action,
        bridge=bridge,
        versions=versions,
        slots=slots,
        parents=parents,
        db=db,
    )


def capture_mock(monkeypatch, scope, *, mutate=None):
    async def capture(db, *, project_id, selection, user):
        assert db is scope.db and project_id == scope.project.id and user is scope.user
        selected = []
        for item in sorted(selection.inputs, key=lambda item: item.slot_id):
            source = deepcopy(scope.slots[item.slot_id])
            assert str(item.protocol_id) == source["protocol_id"]
            assert item.selection.mode == "selected"
            assert not item.selection.filters.model_dump(exclude_none=True)
            wanted = {
                (str(record.id), record.version) for record in item.selection.records
            }
            source["records"] = [
                row
                for row in source["records"]
                if (row["record_id"], row["record_version"]) in wanted
            ]
            assert len(source["records"]) == len(wanted)
            selected.append(
                {"slot_id": item.slot_id, "label": item.slot_id, "snapshot": source}
            )
        snapshot = {
            "schema": project_runtime.PROJECT_SNAPSHOT_SCHEMA,
            "project_id": str(project_id),
            "inputs": selected,
        }
        if mutate:
            mutate(snapshot)
        return snapshot, scope.project

    stub = AsyncMock(side_effect=capture)
    monkeypatch.setattr(project_runtime, "capture_project_sources", stub)
    return stub


def capture(scope):
    return asyncio.run(
        project_runtime.capture_project_node_inputs(
            scope.db,
            task=scope.task,
            method=scope.method,
            node=scope.node,
            graph=scope.graph,
            parents_by_node=scope.parents,
            user=scope.user,
        )
    )


def test_project_snapshot_enumeration_preserves_all_sources_without_flattening():
    scope = inputs()
    sources = project_runtime.analysis_source_snapshots(scope.snapshot)
    assert sources == [item["snapshot"] for item in scope.snapshot["inputs"]]
    assert sources[0] is scope.snapshot["inputs"][0]["snapshot"]
    assert sources[0]["protocol_id"] != sources[1]["protocol_id"]
    assert (
        sources[0]["schemas"][0]["json_schema"]
        != sources[1]["schemas"][0]["json_schema"]
    )


@pytest.mark.parametrize(
    "change",
    [
        "unknown_schema",
        "missing_schema",
        "missing_project",
        "empty_inputs",
        "duplicate_slot",
        "duplicate_protocol",
        "missing_records",
        "empty_records",
        "invalid_protocol",
    ],
)
def test_project_snapshot_enumeration_rejects_missing_or_ambiguous_envelopes(change):
    snapshot = inputs().snapshot
    if change == "unknown_schema":
        snapshot["schema"] = "airalogy.project-snapshot.v999"
    elif change == "missing_schema":
        del snapshot["schema"]
    elif change == "missing_project":
        del snapshot["project_id"]
    elif change == "empty_inputs":
        snapshot["inputs"] = []
    elif change == "duplicate_slot":
        snapshot["inputs"][1]["slot_id"] = snapshot["inputs"][0]["slot_id"]
    elif change == "duplicate_protocol":
        snapshot["inputs"][1]["snapshot"]["protocol_id"] = snapshot["inputs"][0][
            "snapshot"
        ]["protocol_id"]
    elif change == "missing_records":
        del snapshot["inputs"][1]["snapshot"]["records"]
    elif change == "empty_records":
        snapshot["inputs"][1]["snapshot"]["records"] = []
    else:
        snapshot["inputs"][1]["snapshot"]["protocol_id"] = "not-a-uuid"
    with pytest.raises(HTTPException) as denied:
        project_runtime.analysis_source_snapshots(snapshot)
    assert denied.value.status_code == 409


def test_legacy_single_protocol_snapshots_and_node_serialization_remain_unchanged():
    from tests.test_workflow_analysis_contracts import graph as builtin_graph

    snapshot = inputs().slots["treatment"]
    assert project_runtime.analysis_source_snapshots(snapshot) == [snapshot]
    with pytest.raises(HTTPException, match="Expected a Project"):
        project_runtime.project_selection_from_snapshot(snapshot)
    legacy = validate_workflow_graph(builtin_graph(schema_version=2)).model_dump(
        mode="json"
    )
    assert "project_outputs" not in legacy["nodes"][1]
    assert legacy["nodes"][1]["record_sources"] == [
        {"source_node_id": "measure", "cardinality": "one"}
    ]


def test_snapshot_selection_always_preserves_exact_revisions_and_never_latest():
    scope = inputs()
    selection = project_runtime.project_selection_from_snapshot(scope.snapshot)
    for item in selection.inputs:
        source = scope.slots[item.slot_id]
        assert str(item.protocol_id) == source["protocol_id"]
        assert item.selection.mode == "selected"
        assert [
            (str(record.id), record.version) for record in item.selection.records
        ] == [(row["record_id"], row["record_version"]) for row in source["records"]]
        assert not item.selection.filters.model_dump(exclude_none=True)


@pytest.mark.parametrize("revision", [0, True, "2"])
def test_snapshot_selection_rejects_nonexact_record_revisions(revision):
    snapshot = inputs().snapshot
    snapshot["inputs"][0]["snapshot"]["records"][0]["record_version"] = revision
    with pytest.raises(ValueError):
        project_runtime.project_selection_from_snapshot(snapshot)


def test_capture_maps_repeated_protocol_nodes_into_one_slot_without_history(
    monkeypatch,
):
    scope = inputs()
    selected = capture_mock(monkeypatch, scope)
    selection, snapshot, summary, receipts = capture(scope)
    selected.assert_awaited_once()
    assert {item.slot_id: len(item.selection.records) for item in selection.inputs} == {
        "treatment": 2,
        "assay": 1,
    }
    assert summary["counts"] == {"protocols": 2, "records": 3}
    assert len(receipts) == 3
    assert [(item["slot_id"], item["source_node_id"]) for item in receipts] == [
        ("assay", "assay"),
        ("treatment", "treatment_first"),
        ("treatment", "treatment_second"),
    ]
    assert (
        next(item for item in receipts if item["source_node_id"] == "treatment_second")[
            "record_version"
        ]
        == 2
    )
    captured_ids = {
        row["record_id"]
        for item in snapshot["inputs"]
        for row in item["snapshot"]["records"]
    }
    assert captured_ids == {item["record_id"] for item in receipts}
    assert scope.slots["treatment"]["records"][2]["record_id"] not in captured_ids
    for item in receipts:
        node = next(
            node for node in scope.graph.nodes if node.node_id == item["source_node_id"]
        )
        assert item["protocol_id"] == str(node.protocol_id)
        assert item["protocol_version_id"] == str(node.protocol_version_id)


@pytest.mark.parametrize("revision", [1, 2])
def test_same_record_is_never_counted_twice_even_at_different_revisions(
    monkeypatch, revision
):
    scope = inputs()
    selected = capture_mock(monkeypatch, scope)
    first = scope.parents["treatment_first"].output_data["record"]
    scope.parents["treatment_second"].output_data["record"] = {
        "record_id": first["record_id"],
        "record_version": revision,
    }
    with pytest.raises(ValueError, match="same Record"):
        capture(scope)
    selected.assert_not_awaited()


@pytest.mark.parametrize(
    "status", ["queued", "running", "failed", "cancelled", "skipped"]
)
def test_incomplete_or_inactive_parent_never_becomes_a_partial_sample(
    monkeypatch, status
):
    scope = inputs()
    selected = capture_mock(monkeypatch, scope)
    scope.parents["assay"].status = status
    with pytest.raises(ValueError, match="completed Protocol occurrence"):
        capture(scope)
    selected.assert_not_awaited()


@pytest.mark.parametrize(
    "change",
    [
        "missing_version",
        "different_version",
        "wrong_slot",
        "duplicate_node",
        "empty_slot",
    ],
)
def test_runtime_node_bindings_revalidate_exact_slots_and_versions(monkeypatch, change):
    scope = inputs()
    selected = capture_mock(monkeypatch, scope)
    if change == "missing_version":
        del scope.versions[scope.graph.nodes[0].protocol_version_id]
    elif change == "different_version":
        scope.versions[scope.graph.nodes[0].protocol_version_id].version = "2.0.0"
    elif change == "wrong_slot":
        scope.node.record_sources[0].__dict__["slot_id"] = "assay"
    elif change == "duplicate_node":
        scope.node.record_sources.append(scope.node.record_sources[0])
    else:
        scope.node.record_sources[:] = [
            source for source in scope.node.record_sources if source.slot_id != "assay"
        ]
    with pytest.raises(ValueError):
        capture(scope)
    selected.assert_not_awaited()


@pytest.mark.parametrize("change", ["record_version", "protocol_version"])
def test_capture_rechecks_exact_record_and_protocol_revisions_after_source_loading(
    monkeypatch, change
):
    scope = inputs()

    def changed(snapshot):
        row = snapshot["inputs"][0]["snapshot"]["records"][0]
        row[change] = 99 if change == "record_version" else "99.0.0"

    capture_mock(monkeypatch, scope, mutate=changed)
    with pytest.raises(HTTPException) as denied:
        capture(scope)
    assert denied.value.status_code == 409


def test_prepare_project_inputs_uses_one_sealed_bridge_and_existing_capture(
    monkeypatch,
):
    scope = inputs()
    capture_mock(monkeypatch, scope)
    monkeypatch.setattr(
        runtime, "method_for_node", AsyncMock(return_value=scope.method)
    )
    authorized = AsyncMock()
    monkeypatch.setattr(runtime, "authorize_analysis_sources", authorized)
    result = asyncio.run(
        runtime.prepare_analysis_inputs(
            scope.db,
            task=scope.task,
            run=scope.run,
            graph=scope.graph,
            node=scope.node,
            action=scope.action,
            parents_by_node=scope.parents,
            active_nodes=set(scope.parents),
        )
    )
    authorized.assert_awaited_once()
    assert result["engine_version"] == ENGINE_VERSION
    assert result["source_digest"] == canonical_digest(scope.bridge.input_snapshot)
    assert result["method_digest"] == scope.method.digest
    assert len(result["source_nodes"]) == 3
    assert result["selection"]["schema"] == "airalogy.project-selection.v1"
    assert all(
        item["selection"]["mode"] == "selected"
        for item in result["selection"]["inputs"]
    )
    # This stage does not create an AnalysisRun or enqueue a second scheduler.
    scope.db.add.assert_not_called()
    result["summary"]["counts"]["records"] = 999
    assert (
        sum(
            len(item["snapshot"]["records"])
            for item in scope.bridge.input_snapshot["inputs"]
        )
        == 3
    )


def test_all_declared_gate_runs_before_project_capture_or_database_queries(monkeypatch):
    scope = inputs()
    selected = capture_mock(monkeypatch, scope)
    with pytest.raises(ValueError, match="partial samples are forbidden"):
        asyncio.run(
            runtime.prepare_analysis_inputs(
                scope.db,
                task=scope.task,
                run=scope.run,
                graph=scope.graph,
                node=scope.node,
                action=scope.action,
                parents_by_node=scope.parents,
                active_nodes={"assay", "treatment_first"},
            )
        )
    scope.db.get.assert_not_awaited()
    selected.assert_not_awaited()


def test_sealed_project_input_cannot_be_replaced(monkeypatch):
    scope = inputs()
    capture_mock(monkeypatch, scope)
    scope.bridge.source_digest = "b" * 64
    scope.bridge.input_snapshot = {"existing": "immutable"}
    monkeypatch.setattr(
        runtime, "method_for_node", AsyncMock(return_value=scope.method)
    )
    monkeypatch.setattr(runtime, "authorize_analysis_sources", AsyncMock())
    with pytest.raises(HTTPException) as denied:
        asyncio.run(
            runtime.prepare_analysis_inputs(
                scope.db,
                task=scope.task,
                run=scope.run,
                graph=scope.graph,
                node=scope.node,
                action=scope.action,
                parents_by_node=scope.parents,
                active_nodes=set(scope.parents),
            )
        )
    assert denied.value.status_code == 409
    assert scope.bridge.input_snapshot == {"existing": "immutable"}


def authorization(monkeypatch, scope, *, denied_protocol=None, wrong_project=False):
    users = {
        identity: SimpleNamespace(id=identity)
        for identity in {
            scope.task.owner_user_id,
            scope.run.requested_by_user_id,
            scope.action.assignee_user_id,
        }
    }

    async def get(model, identity, **_kwargs):
        assert model is User
        return users.get(identity)

    scope.db.get.side_effect = get

    async def permitted(_db, protocol_id, user):
        assert protocol_id in {
            UUID(source["protocol_id"]) for source in scope.slots.values()
        }
        assert user.id in users
        return (
            None,
            SimpleNamespace(id=uuid4()) if wrong_project else scope.project,
            protocol_id == UUID(scope.slots["assay"]["protocol_id"]),
        )

    async def manifest(_db, protocol_id, user, records, *, own_only):
        if protocol_id == denied_protocol:
            raise HTTPException(403, "Synthetic exact-source permission revoked")

    scope_check = AsyncMock(side_effect=permitted)
    manifest_check = AsyncMock(side_effect=manifest)
    monkeypatch.setattr(runtime, "analysis_scope", scope_check)
    monkeypatch.setattr(runtime, "authorize_source_manifest", manifest_check)
    return users, scope_check, manifest_check


def test_every_recipient_and_approver_is_authorized_for_every_project_source(
    monkeypatch,
):
    scope = inputs()
    scope.run.requested_by_user_id = uuid4()
    scope.action.assignee_user_id = uuid4()
    approver = SimpleNamespace(id=uuid4())
    users, scoped, manifests = authorization(monkeypatch, scope)
    users[approver.id] = approver
    asyncio.run(
        runtime.authorize_analysis_sources(
            scope.db,
            task=scope.task,
            run=scope.run,
            action=scope.action,
            snapshot=scope.snapshot,
            extra_user=approver,
        )
    )
    expected = {
        (user_id, UUID(source["protocol_id"]))
        for user_id in users
        for source in scope.slots.values()
    }
    assert {
        (call.args[2].id, call.args[1]) for call in scoped.await_args_list
    } == expected
    assert {
        (call.args[2].id, call.args[1]) for call in manifests.await_args_list
    } == expected
    assert scoped.await_count == manifests.await_count == 8
    for call in manifests.await_args_list:
        source = next(
            source
            for source in scope.slots.values()
            if UUID(source["protocol_id"]) == call.args[1]
        )
        assert call.args[3] is source["records"]
        assert call.kwargs["own_only"] is (source is scope.slots["assay"])


def test_shared_recipient_identity_is_checked_once_per_source(monkeypatch):
    scope = inputs()
    _, scoped, manifests = authorization(monkeypatch, scope)
    asyncio.run(
        runtime.authorize_analysis_sources(
            scope.db,
            task=scope.task,
            run=scope.run,
            action=scope.action,
            snapshot=scope.snapshot,
            extra_user=scope.user,
        )
    )
    assert scoped.await_count == manifests.await_count == 2


def test_any_revoked_source_stops_project_authorization(monkeypatch):
    scope = inputs()
    denied = UUID(scope.slots["assay"]["protocol_id"])
    _, _, manifests = authorization(monkeypatch, scope, denied_protocol=denied)
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            runtime.authorize_analysis_sources(
                scope.db,
                task=scope.task,
                run=scope.run,
                action=scope.action,
                snapshot=scope.snapshot,
            )
        )
    assert error.value.status_code == 403
    assert manifests.await_args.args[1] == denied


@pytest.mark.parametrize(
    "change",
    ["envelope_project", "source_project", "missing_user", "single_source_files"],
)
def test_project_authorization_fails_closed_for_wrong_scope_or_identity(
    monkeypatch, change
):
    scope = inputs()
    users, _, _ = authorization(
        monkeypatch, scope, wrong_project=change == "source_project"
    )
    kwargs = {}
    if change == "envelope_project":
        scope.snapshot["project_id"] = str(uuid4())
    elif change == "missing_user":
        users.clear()
    elif change == "single_source_files":
        kwargs["input_files"] = [{"input_id": "not-a-Project-file-contract"}]
    with pytest.raises(HTTPException) as denied:
        asyncio.run(
            runtime.authorize_analysis_sources(
                scope.db,
                task=scope.task,
                run=scope.run,
                action=scope.action,
                snapshot=scope.snapshot,
                **kwargs,
            )
        )
    assert denied.value.status_code == (403 if change == "missing_user" else 409)


def test_legacy_authorization_still_uses_the_original_single_protocol_manifest(
    monkeypatch,
):
    scope = inputs()
    _, scoped, manifests = authorization(monkeypatch, scope)
    snapshot = scope.slots["treatment"]
    asyncio.run(
        runtime.authorize_analysis_sources(
            scope.db,
            task=scope.task,
            run=scope.run,
            action=scope.action,
            snapshot=snapshot,
        )
    )
    assert scoped.await_count == manifests.await_count == 1
    assert manifests.await_args.args[3] is snapshot["records"]


@pytest.mark.parametrize("stale", [False, True])
def test_project_approval_uses_existing_private_analysis_lifecycle_with_fresh_seal(
    monkeypatch, stale
):
    from app.services import (
        project_analyses,
        research_runtime,
        workflow_analysis_methods,
    )

    scope = inputs()
    scope.action.title = "Review actual Project inputs"
    scope.action.revision = 1
    scope.action.preview_digest = "b" * 64
    scope.bridge.method_publication_id = scope.method.id
    scope.bridge.preview_digest = scope.action.preview_digest
    scope.bridge.input_snapshot = deepcopy(scope.snapshot)
    scope.bridge.source_digest = canonical_digest(scope.snapshot)
    scope.bridge.analysis_run_id = None
    approved_by = SimpleNamespace(id=uuid4())
    analysis = SimpleNamespace(id=uuid4(), status="pending")
    preview = SimpleNamespace(
        id=uuid4(),
        source_digest="c" * 64 if stale else scope.bridge.source_digest,
        recipe_digest=canonical_digest(scope.method.recipe),
        preview_digest="d" * 64,
    )
    get = scope.db.get.side_effect

    async def get_with_analysis(model, identity, **kwargs):
        if model is AnalysisRun:
            assert identity == analysis.id
            return analysis
        return await get(model, identity, **kwargs)

    scope.db.get.side_effect = get_with_analysis
    monkeypatch.setattr(
        runtime, "verify_analysis_execution", AsyncMock(return_value=scope.bridge)
    )
    authorized = AsyncMock()
    monkeypatch.setattr(runtime, "authorize_analysis_sources", authorized)
    monkeypatch.setattr(
        workflow_analysis_methods, "get_method", AsyncMock(return_value=scope.method)
    )
    prepare = AsyncMock(return_value=preview)
    confirm = AsyncMock(return_value=analysis)
    emitted = AsyncMock()
    monkeypatch.setattr(project_analyses, "create_project_preview", prepare)
    monkeypatch.setattr(project_analyses, "confirm_project_analysis", confirm)
    monkeypatch.setattr(research_runtime, "emit_research_event", emitted)

    async def approve():
        return await runtime.approve_workflow_analysis(
            scope.db,
            task=scope.task,
            run=scope.run,
            action=scope.action,
            current_user=approved_by,
        )

    if stale:
        with pytest.raises(HTTPException) as error:
            asyncio.run(approve())
        assert error.value.status_code == 409
        confirm.assert_not_awaited()
        emitted.assert_not_awaited()
        assert scope.bridge.analysis_run_id is None
    else:
        assert asyncio.run(approve()) is analysis
        assert asyncio.run(approve()) is analysis
        confirm.assert_awaited_once_with(
            scope.db,
            preview_id=preview.id,
            preview_digest=preview.preview_digest,
            key=f"workflow-analysis:{scope.action.id}",
            user=scope.user,
        )
        assert scope.bridge.analysis_run_id == analysis.id
        assert scope.bridge.analysis_preview_id == preview.id
        assert (
            scope.action.status == "queued"
            and scope.run.status == "waiting_for_compute"
        )
        assert scope.action.revision == 2
        emitted.assert_awaited_once()
    prepare.assert_awaited_once()
    request = prepare.await_args.args[1]
    assert request.project_id == scope.task.project_id
    assert request.pipeline_revision_id is None and request.rerun_of_id is None
    assert request.recipe.model_dump(mode="json") == scope.method.recipe
    assert all(item.selection.mode == "selected" for item in request.selection.inputs)
    assert authorized.await_args.kwargs["extra_user"] is approved_by
    scope.db.add.assert_not_called()
