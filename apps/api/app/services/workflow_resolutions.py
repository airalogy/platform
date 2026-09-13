"""Resolve fixed Workflow edges/inputs from authorized immutable Record receipts.

No model, arbitrary expression, coercion or file permission propagation is used.
Callers hold the Task -> Run -> Action locks. A decision is sealed once before
downstream approval; recovery verifies that receipt and live source access.
"""

from copy import deepcopy
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.models.project import Project
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.research import ResearchAction, ResearchProtocolRun
from app.models.research_asset import ResearchActionOutputSnapshot
from app.models.user import User
from app.models.workflow_definition import WorkflowNodeResolution
from app.routers.permission import check_user_permission
from app.services.research_action_outputs import (
    action_output_digest,
    action_output_payload,
    verify_action_output_snapshot,
)
from app.services.research_runtime import canonical_digest
from app.services.workflow_contracts import (
    WorkflowContractError,
    evaluate_all_active_join,
    evaluate_workflow_condition,
    workflow_revision_digest,
)
from app.services.workflow_data import protocol_field_catalog, resolve_workflow_bindings
from app.services.workflow_definitions import validate_initial_values


def resolution_payload(row):
    return {
        "schema": "airalogy.workflow-node-resolution.v1",
        "workflow_revision_id": str(row.workflow_revision_id),
        "task_id": str(row.task_id),
        "run_id": str(row.run_id),
        "action_id": str(row.action_id),
        "node_id": row.node_id,
        "state": row.state,
        "initial_values": row.initial_values,
        "receipt": row.receipt,
    }


def verify_resolution_seal(row):
    if row.digest != canonical_digest(resolution_payload(row)):
        raise HTTPException(409, "Workflow resolution receipt integrity check failed")


async def _authorized_record(db, *, task, run, target, source, output):
    """Validate the exact submitted Record and every identity receiving its value."""
    payload = output.get("record") if isinstance(output, dict) else None
    try:
        record_id = UUID(payload["record_id"])
        record_version = payload["record_version"]
        if type(record_version) is not int or record_version < 1:
            raise ValueError("Invalid Record revision")
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(
            409, "Workflow source has no exact submitted Record"
        ) from exc
    typed = await db.scalar(
        select(ResearchProtocolRun).where(ResearchProtocolRun.action_id == source.id)
    )
    record = await db.scalar(
        select(Record)
        .where(Record.id == record_id, Record.version == record_version)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    protocol = await db.get(Protocol, record.protocol_id) if record else None
    project = await db.get(Project, task.project_id)
    if (
        record is None
        or record.deleted_at is not None
        or protocol is None
        or protocol.deleted_at is not None
        or project is None
        or project.deleted_at is not None
    ):
        raise HTTPException(403, "Workflow source Record is no longer available")
    if (
        source.run_id != run.id
        or source.kind != "protocol_run"
        or source.status != "completed"
        or typed is None
        or typed.record_id != record.id
        or typed.record_version != record.version
        or typed.protocol_id != record.protocol_id
        or typed.protocol_version != record.protocol_version
        or protocol.project_id != task.project_id
        or canonical_digest(payload.get("data")) != canonical_digest(record.data)
        or (payload.get("metadata") or {}).get("sha1") != record.hash
    ):
        raise HTTPException(
            409, "Workflow source no longer matches its submitted Record"
        )
    for user_id in {
        task.owner_user_id,
        run.requested_by_user_id,
        target.assignee_user_id,
    }:
        user = await db.get(User, user_id) if user_id else None
        if user is None:
            raise HTTPException(403, "Workflow input recipient is unavailable")
        try:
            await check_user_permission(
                db,
                project=project,
                user=user,
                action="read_record",
                protocol=protocol,
                record=record,
            )
        except HTTPException as exc:
            if exc.status_code in {400, 403}:
                raise HTTPException(
                    403, "Workflow input recipient cannot read the source Record"
                ) from exc
            raise
    return record, typed


async def _source_snapshot(db, *, task, run, target, source):
    analysis = None
    if source.kind == "analysis_run":
        analysis = await _authorized_analysis(
            db, task=task, run=run, target=target, source=source
        )
    else:
        record, typed = await _authorized_record(
            db,
            task=task,
            run=run,
            target=target,
            source=source,
            output=source.output_data,
        )
    payload = action_output_payload(source, task_id=task.id)
    digest = action_output_digest(payload)
    # The same Action may already have become reviewed Evidence. Never overwrite
    # its snapshot, and handle a concurrent independent evidence registration.
    await db.execute(
        insert(ResearchActionOutputSnapshot)
        .values(
            task_id=task.id,
            run_id=run.id,
            action_id=source.id,
            action_revision=source.revision,
            action_kind=source.kind,
            output_data=deepcopy(source.output_data),
            digest=digest,
            created_by_user_id=source.assignee_user_id,
        )
        .on_conflict_do_nothing(index_elements=["action_id"])
    )
    snapshot = await db.scalar(
        select(ResearchActionOutputSnapshot).where(
            ResearchActionOutputSnapshot.action_id == source.id
        )
    )
    verify_action_output_snapshot(snapshot)
    if (
        snapshot.digest != digest
        or snapshot.task_id != task.id
        or snapshot.run_id != run.id
    ):
        raise HTTPException(
            409, "Workflow source snapshot differs from its accepted output"
        )
    common = {
        "action_id": str(source.id),
        "action_revision": snapshot.action_revision,
        "snapshot_id": str(snapshot.id),
        "snapshot_digest": snapshot.digest,
    }
    if analysis is not None:
        return {
            **common,
            "kind": "analysis",
            "analysis_id": str(analysis.id),
            "source_digest": analysis.source_digest,
            "result_digest": analysis.result_digest,
        }, deepcopy(snapshot.output_data["analysis_result"]["outputs"])
    return {
        **common,
        "record_id": str(record.id),
        "record_version": record.version,
        "record_hash": record.hash,
        "protocol_id": str(typed.protocol_id),
        "protocol_version_id": str(typed.protocol_version_id),
        "protocol_version": typed.protocol_version,
    }, deepcopy(snapshot.output_data["record"]["data"])


async def _authorized_analysis(db, *, task, run, target, source):
    from app.models.analysis import AnalysisRun
    from app.models.workflow_analysis import ResearchAnalysisAction
    from app.services.record_analyses import verify_run_integrity
    from app.services.workflow_analysis_runtime import authorize_analysis_sources

    bridge = await db.get(ResearchAnalysisAction, source.id, populate_existing=True)
    analysis = (
        await db.get(AnalysisRun, bridge.analysis_run_id, populate_existing=True)
        if bridge and bridge.analysis_run_id
        else None
    )
    output = (source.output_data or {}).get("analysis_result") or {}
    if (
        source.run_id != run.id
        or source.status != "completed"
        or analysis is None
        or analysis.status != "succeeded"
    ):
        raise HTTPException(
            409, "Workflow analysis source is not a completed persisted result"
        )
    verify_run_integrity(analysis)
    if (
        bridge.source_digest != analysis.source_digest
        or output.get("analysis_id") != str(analysis.id)
        or output.get("result_digest") != analysis.result_digest
        or output.get("report") != analysis.result
    ):
        raise HTTPException(409, "Workflow analysis result receipt changed")
    await authorize_analysis_sources(
        db, task=task, run=run, action=target, snapshot=bridge.input_snapshot
    )
    return analysis


async def _verify_source(db, *, task, run, target, ref):
    try:
        snapshot = await db.get(
            ResearchActionOutputSnapshot,
            UUID(ref["snapshot_id"]),
            populate_existing=True,
        )
        source = await db.get(
            ResearchAction, UUID(ref["action_id"]), populate_existing=True
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(409, "Malformed Workflow source receipt") from exc
    if snapshot is None or source is None:
        raise HTTPException(409, "Workflow source snapshot is missing")
    verify_action_output_snapshot(snapshot)
    if (
        snapshot.digest != ref.get("snapshot_digest")
        or snapshot.action_id != source.id
        or snapshot.task_id != task.id
        or snapshot.run_id != run.id
        or snapshot.action_revision != ref.get("action_revision")
        or action_output_digest(action_output_payload(source, task_id=task.id))
        != snapshot.digest
    ):
        raise HTTPException(
            409, "Workflow source snapshot no longer matches its receipt"
        )
    if ref.get("kind") == "analysis":
        analysis = await _authorized_analysis(
            db, task=task, run=run, target=target, source=source
        )
        if (
            str(analysis.id) != ref.get("analysis_id")
            or analysis.source_digest != ref.get("source_digest")
            or analysis.result_digest != ref.get("result_digest")
        ):
            raise HTTPException(409, "Workflow analysis source lineage changed")
        return
    record, typed = await _authorized_record(
        db,
        task=task,
        run=run,
        target=target,
        source=source,
        output=snapshot.output_data,
    )
    if (
        str(record.id) != ref.get("record_id")
        or record.version != ref.get("record_version")
        or record.hash != ref.get("record_hash")
        or str(typed.protocol_id) != ref.get("protocol_id")
        or str(typed.protocol_version_id) != ref.get("protocol_version_id")
        or typed.protocol_version != ref.get("protocol_version")
    ):
        raise HTTPException(409, "Workflow source Record lineage has changed")


async def verify_workflow_node_resolution(
    db, *, task, run, graph, node, action, resolution
):
    """Do not reinterpret a past decision against a newer Record or Schema."""
    verify_resolution_seal(resolution)
    marker = (run.environment_snapshot or {}).get("manual_workflow") or {}
    if (
        resolution.task_id != task.id
        or resolution.run_id != run.id
        or resolution.action_id != action.id
        or resolution.node_id != node.node_id
        or str(resolution.workflow_revision_id) != marker.get("revision_id")
        or resolution.receipt.get("graph_digest") != workflow_revision_digest(graph)
    ):
        raise HTTPException(
            409, "Workflow resolution does not belong to the pinned node"
        )
    for source in resolution.receipt.get("sources", {}).values():
        await _verify_source(db, task=task, run=run, target=action, ref=source)
    if graph.schema_version >= 4:
        from app.services.workflow_files import verify_resolution_files

        await verify_resolution_files(
            db, task=task, run=run, action=action, resolution=resolution
        )


async def resolve_workflow_node(db, *, task, run, graph, node, action, parents_by_node):
    existing = await db.scalar(
        select(WorkflowNodeResolution).where(
            WorkflowNodeResolution.action_id == action.id
        )
    )
    if existing is not None:
        await verify_workflow_node_resolution(
            db,
            task=task,
            run=run,
            graph=graph,
            node=node,
            action=action,
            resolution=existing,
        )
        return existing
    incoming = [edge for edge in graph.edges if edge.target_node_id == node.node_id]
    if not incoming or set(parents_by_node) != {
        edge.source_node_id for edge in incoming
    }:
        raise HTTPException(
            409, "Workflow resolution requires the exact incoming edge set"
        )
    if any(
        parent.status not in {"completed", "failed", "skipped", "cancelled"}
        for parent in parents_by_node.values()
    ):
        raise ValueError("Workflow is still waiting for incoming edges")
    versions = {
        item.node_id: await db.get(ProtocolVersion, item.protocol_version_id)
        for item in graph.nodes
        if item.kind == "protocol"
    }
    catalogs = {
        key: protocol_field_catalog(version, include_files=graph.schema_version >= 4)
        for key, version in versions.items()
    }
    for item in graph.nodes:
        if item.kind == "analysis":
            from app.services.workflow_analysis_contracts import (
                analysis_output_catalog,
                validate_analysis_method_inputs,
            )
            from app.services.workflow_analysis_runtime import method_for_node

            method = await method_for_node(
                db,
                user=await db.get(User, run.requested_by_user_id),
                project=await db.get(Project, task.project_id),
                node=item,
            )
            if method.recipe.get("kind") == "compute":
                from app.services.workflow_compute_contracts import (
                    compute_output_catalog,
                )

                expected = method.compute_contract["input_schema_contract"]
                for source in item.record_sources:
                    version = versions[source.source_node_id]
                    actual = {
                        "json_schema": version.json_schema,
                        "fields": version.fields,
                    }
                    if canonical_digest(actual) != canonical_digest(expected):
                        raise HTTPException(
                            409,
                            "Compute source Schema differs from its published contract",
                        )
                catalogs[item.node_id] = compute_output_catalog(
                    method.compute_contract["result_schema"], item.compute_outputs
                )
                if graph.schema_version >= 4:
                    from app.services.workflow_file_contracts import (
                        compute_file_output_catalog,
                    )

                    catalogs[item.node_id].update(
                        compute_file_output_catalog(
                            method.recipe, item.compute_file_outputs
                        )
                    )
            else:
                fields = validate_analysis_method_inputs(
                    method.recipe,
                    [versions[source.source_node_id] for source in item.record_sources],
                )
                catalogs[item.node_id] = analysis_output_catalog(
                    method.recipe, fields, item.analysis_outputs
                )
    outcomes = []
    edges = []
    sources = {}
    outputs = {}
    failure = None
    for edge in incoming:
        parent = parents_by_node[edge.source_node_id]
        entry = {
            "edge_id": edge.edge_id,
            "source_node_id": edge.source_node_id,
            "source_action_id": str(parent.id),
            "source_status": parent.status,
            "condition": edge.condition.model_dump(mode="json")
            if edge.condition
            else None,
        }
        outcome = "failed"
        if parent.status == "completed":
            ref, output = await _source_snapshot(
                db, task=task, run=run, target=action, source=parent
            )
            sources[edge.source_node_id] = ref
            try:
                selected = edge.condition is None or evaluate_workflow_condition(
                    edge.condition, output, catalogs[edge.source_node_id]
                )
                outcome = "active" if selected else "inactive"
                if selected:
                    outputs[edge.source_node_id] = output
                if edge.condition:
                    value = output
                    for segment in edge.condition.path:
                        value = value[segment]
                    entry["observed_value"] = value
            except WorkflowContractError as exc:
                failure = str(exc)
                entry["error"] = failure
        elif parent.status == "cancelled":
            outcome = "cancelled"
        elif parent.status == "skipped":
            previous = await db.scalar(
                select(WorkflowNodeResolution).where(
                    WorkflowNodeResolution.action_id == parent.id
                )
            )
            if previous is not None:
                verify_resolution_seal(previous)
                if (
                    previous.state == "branch_not_selected"
                    and previous.run_id == run.id
                ):
                    outcome = "inactive"
        entry["outcome"] = outcome
        edges.append(entry)
        outcomes.append(outcome)
    decision = evaluate_all_active_join(outcomes)
    state = "failed" if failure else decision.state
    values = deepcopy(node.initial_values)
    binding_receipts = []
    file_receipts = []
    analysis_input = None
    if state == "ready":
        savepoint = await db.begin_nested() if graph.schema_version >= 4 else None
        try:
            if node.kind == "analysis":
                from app.services.workflow_analysis_runtime import (
                    prepare_analysis_inputs,
                )

                analysis_input = await prepare_analysis_inputs(
                    db,
                    task=task,
                    run=run,
                    graph=graph,
                    node=node,
                    action=action,
                    parents_by_node=parents_by_node,
                    active_nodes=set(outputs),
                )
            else:
                file_values = None
                if graph.schema_version >= 4:
                    from app.services.workflow_files import materialize_file_bindings

                    file_values, file_receipts = await materialize_file_bindings(
                        db,
                        task=task,
                        run=run,
                        graph=graph,
                        node=node,
                        action=action,
                        parents_by_node=parents_by_node,
                        sources=sources,
                        outputs=outputs,
                    )
                resolved = resolve_workflow_bindings(
                    graph,
                    node.node_id,
                    outputs,
                    catalogs,
                    file_values_by_binding=file_values,
                )
                values = resolved.initial_values
                binding_receipts = resolved.bindings
                validate_initial_values(
                    versions[node.node_id],
                    values,
                    allow_files=graph.schema_version >= 4,
                )
        except ValueError as exc:
            if savepoint is not None:
                await savepoint.rollback()
            state, failure = "failed", str(exc)
            values, binding_receipts, file_receipts = (
                deepcopy(node.initial_values),
                [],
                [],
            )
        except BaseException:
            if savepoint is not None:
                await savepoint.rollback()
            raise
        else:
            if savepoint is not None:
                await savepoint.commit()
    receipt = {
        "graph_digest": workflow_revision_digest(graph),
        "edges": edges,
        "sources": sources,
        "bindings": binding_receipts,
        "join": decision.model_dump(mode="json"),
        "error": failure,
    }
    if analysis_input is not None:
        receipt["analysis_input"] = analysis_input
    if graph.schema_version >= 4:
        receipt["files"] = file_receipts
    row = WorkflowNodeResolution(
        workflow_revision_id=UUID(
            run.environment_snapshot["manual_workflow"]["revision_id"]
        ),
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        node_id=node.node_id,
        state=state,
        initial_values=values,
        receipt=receipt,
    )
    row.digest = canonical_digest(resolution_payload(row))
    db.add(row)
    await db.flush()
    return row
