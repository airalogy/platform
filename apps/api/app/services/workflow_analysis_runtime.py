"""Governed Workflow cards adapting the ordinary persisted analysis engine.

This is a lifecycle adapter, not a second analysis engine or scheduler. Private
method ownership is never broadened: only explicitly published methods enter it.
"""

from copy import deepcopy
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from app.models.analysis import AnalysisRun
from app.models.research import ResearchAction, ResearchRun, ResearchTask
from app.models.user import User
from app.models.workflow_analysis import ResearchAnalysisAction
from app.services.analysis_engine import (
    ENGINE_VERSION,
    AnalysisRecipe,
    preview_analysis,
)
from app.services.persistent_jobs import JobDeferred
from app.services.record_analyses import (
    AnalysisPreviewRequest,
    AnalysisSelection,
    analysis_scope,
    authorize_source_manifest,
    cancel_analysis,
    capture_sources,
    confirm_analysis,
    create_preview,
    verify_run_integrity,
)


async def method_for_node(db, *, user, project, node):
    from app.services.workflow_analysis_methods import get_method

    method = await get_method(db, user, node.method_publication_id, project=project)
    from app.services.analysis_compute_contracts import COMPUTE_ENGINE_VERSION

    if method.engine_version not in {ENGINE_VERSION, COMPUTE_ENGINE_VERSION}:
        raise HTTPException(422, "This Workflow analysis engine is unsupported")
    return method


async def materialize_analysis_card(
    db, *, task, run, node, graph_meta, idempotency_key
):
    from app.models.project import Project
    from app.services.research_runtime import (
        _next_action_sequence,
        _workflow_action_preview,
    )

    user = await db.get(User, run.requested_by_user_id)
    method = await method_for_node(
        db, user=user, project=await db.get(Project, task.project_id), node=node
    )
    action = ResearchAction(
        run_id=run.id,
        sequence=await _next_action_sequence(db, run.id),
        plan_version=run.plan_version,
        kind="analysis_run",
        status="blocked",
        title=node.title or method.title,
        description="Analyze all declared exact upstream Records.",
        executor_type="internal",
        assignee_user_id=run.requested_by_user_id,
        input_data={
            "source": "manual_workflow",
            "action_graph": graph_meta,
            "method_publication_id": str(method.id),
            "method_digest": method.digest,
            "engine_version": method.engine_version,
            "record_sources": [
                item.model_dump(mode="json") for item in node.record_sources
            ],
            "input_policy": node.input_policy,
            "analysis_outputs": [
                item.model_dump(mode="json") for item in node.analysis_outputs
            ],
        },
        output_data={},
        requirements={"approval_policy": "always_ask"},
        policy_decision="ask",
        policy_reason="Review the exact analysis method and resolved Record inputs before execution.",
        preview_digest="",
        idempotency_key=idempotency_key,
        revision=1,
    )
    if method.recipe.get("kind") == "compute":
        action.input_data.update(
            {
                "analysis_kind": "compute",
                "compute_outputs": [
                    item.model_dump(mode="json") for item in node.compute_outputs
                ],
            }
        )
        if getattr(node, "compute_file_outputs", None):
            action.input_data["compute_file_outputs"] = [
                item.model_dump(mode="json") for item in node.compute_file_outputs
            ]
    action.preview_digest = _workflow_action_preview(action)
    db.add(action)
    await db.flush()
    db.add(
        ResearchAnalysisAction(
            action_id=action.id, method_publication_id=method.id, input_snapshot={}
        )
    )
    await db.flush()
    return action


async def authorize_analysis_sources(
    db, *, task, run, action, snapshot, extra_user=None
):
    """Receiving resolved values requires each identity's current Record ACL."""
    identities = {task.owner_user_id, run.requested_by_user_id, action.assignee_user_id}
    if extra_user is not None:
        identities.add(extra_user.id)
    for user_id in identities:
        user = await db.get(User, user_id) if user_id else None
        if user is None:
            raise HTTPException(403, "Workflow analysis recipient is unavailable")
        _, project, own_only = await analysis_scope(
            db, UUID(snapshot["protocol_id"]), user
        )
        if project.id != task.project_id:
            raise HTTPException(409, "Workflow analysis source Project changed")
        await authorize_source_manifest(
            db,
            UUID(snapshot["protocol_id"]),
            user,
            snapshot["records"],
            own_only=own_only,
        )


async def prepare_analysis_inputs(
    db, *, task, run, graph, node, action, parents_by_node, active_nodes
):
    from app.models.project import Project
    from app.services.research_runtime import canonical_digest

    requested = {item.source_node_id for item in node.record_sources}
    if not requested or not requested <= active_nodes:
        raise ValueError(
            "All declared analysis Record sources must be active; partial samples are forbidden"
        )
    user = await db.get(User, action.assignee_user_id)
    method = await method_for_node(
        db, user=user, project=await db.get(Project, task.project_id), node=node
    )
    records = []
    graph_nodes = {item.node_id: item for item in graph.nodes}
    for node_id in sorted(requested):
        parent = parents_by_node[node_id]
        source = graph_nodes[node_id]
        if (
            parent.kind != "protocol_run"
            or parent.status != "completed"
            or source.protocol_id != method.protocol_id
        ):
            raise ValueError(
                "Analysis inputs must be completed Records from the published method's Protocol"
            )
        payload = (parent.output_data or {}).get("record") or {}
        records.append(
            {"id": payload["record_id"], "version": payload["record_version"]}
        )
    if len({(item["id"], item["version"]) for item in records}) != len(records):
        raise ValueError(
            "Analysis input occurrences must have distinct Record revisions"
        )
    selection = AnalysisSelection(mode="selected", records=records)
    snapshot, _, _ = await capture_sources(
        db, protocol_id=method.protocol_id, user=user, selection=selection
    )
    await authorize_analysis_sources(
        db, task=task, run=run, action=action, snapshot=snapshot
    )
    if method.recipe.get("kind") == "compute":
        from app.services.workflow_compute_runtime import compute_preview

        preview = await compute_preview(
            db, task=task, run=run, action=action, method=method, selection=selection
        )
        if preview.source_digest != canonical_digest(snapshot):
            raise HTTPException(409, "Compute sources changed during resolution")
        summary = preview.summary
    else:
        summary = preview_analysis(
            AnalysisRecipe.model_validate(method.recipe),
            snapshot["records"],
            snapshot["fields"],
        )
    bridge = await db.get(ResearchAnalysisAction, action.id)
    if bridge is None or bridge.source_digest is not None:
        raise HTTPException(
            409, "Workflow analysis input resolution cannot be replaced"
        )
    # This field is sealed with its digests by the caller in the same transaction
    # after WorkflowNodeResolution receives its immutable identity.
    bridge.input_snapshot = deepcopy(snapshot)
    return {
        "source_digest": canonical_digest(snapshot),
        "method_digest": method.digest,
        "engine_version": method.engine_version,
        "selection": selection.model_dump(mode="json"),
        "summary": summary,
    }


async def verify_analysis_card(db, *, task, run, action, node, resolution=None):
    from app.models.project import Project
    from app.services.research_runtime import canonical_digest

    bridge = await db.get(ResearchAnalysisAction, action.id, populate_existing=True)
    if bridge is None or bridge.method_publication_id != node.method_publication_id:
        raise HTTPException(409, "Workflow analysis typed binding changed")
    user = await db.get(User, run.requested_by_user_id)
    method = await method_for_node(
        db, user=user, project=await db.get(Project, task.project_id), node=node
    )
    data = action.input_data or {}
    if data.get("method_digest") != method.digest or data.get(
        "method_publication_id"
    ) != str(method.id):
        raise HTTPException(409, "Workflow analysis method pin changed")
    if bridge.source_digest is not None:
        if (
            resolution is None
            or bridge.resolution_digest != resolution.digest
            or bridge.source_digest != canonical_digest(bridge.input_snapshot)
            or bridge.source_digest
            != (resolution.receipt.get("analysis_input") or {}).get("source_digest")
            or bridge.preview_digest != action.preview_digest
            or data.get("analysis_input") != resolution.receipt.get("analysis_input")
        ):
            raise HTTPException(409, "Workflow analysis sealed inputs changed")
        await authorize_analysis_sources(
            db, task=task, run=run, action=action, snapshot=bridge.input_snapshot
        )
    elif resolution is not None and resolution.state == "ready":
        raise HTTPException(409, "Workflow analysis ready input is not sealed")
    if bridge.analysis_run_id is not None:
        analysis = await db.get(
            AnalysisRun, bridge.analysis_run_id, populate_existing=True
        )
        if analysis is None:
            raise HTTPException(409, "Workflow analysis execution is missing")
        verify_run_integrity(analysis)
        if (
            analysis.source_digest != bridge.source_digest
            or analysis.recipe != method.recipe
            or analysis.created_by_user_id != action.assignee_user_id
            or analysis.project_id != task.project_id
            or analysis.protocol_id != method.protocol_id
        ):
            raise HTTPException(409, "Workflow analysis execution contract changed")
        if action.status == "completed":
            output = (action.output_data or {}).get("analysis_result") or {}
            projected = await projected_analysis_result(
                db,
                method=method,
                node=node,
                analysis=analysis,
                fields=bridge.input_snapshot["fields"],
            )
            if (
                analysis.status != "succeeded"
                or output.get("report") != analysis.result
                or output.get("result_digest") != analysis.result_digest
                or output.get("outputs") != projected
            ):
                raise HTTPException(409, "Workflow analysis output projection changed")
    return bridge


async def verify_analysis_execution(db, *, task, run, action):
    from app.models.workflow_definition import (
        WorkflowNodeResolution,
        WorkflowRevision,
        WorkflowRunBinding,
    )
    from app.services.research_runtime import _workflow_action_preview, canonical_digest
    from app.services.workflow_definitions import verify_revision
    from app.services.workflow_resolutions import verify_workflow_node_resolution

    marker = run.environment_snapshot.get("manual_workflow") or {}
    revision = await db.get(
        WorkflowRevision, UUID(marker["revision_id"]), populate_existing=True
    )
    binding = await db.scalar(
        select(WorkflowRunBinding).where(WorkflowRunBinding.run_id == run.id)
    )
    if (
        marker.get("execution_contract_version") not in {3, 4, 5}
        or revision is None
        or revision.digest != marker.get("revision_digest")
        or binding is None
        or binding.environment_digest != canonical_digest(run.environment_snapshot)
        or binding.workflow_revision_id != revision.id
        or binding.task_id != task.id
        or action.preview_digest != _workflow_action_preview(action)
    ):
        raise HTTPException(409, "Workflow analysis revision binding changed")
    graph = verify_revision(revision)
    node = next(
        (
            item
            for item in graph.nodes
            if item.node_id
            == (action.input_data.get("action_graph") or {}).get("node_id")
        ),
        None,
    )
    resolution = await db.scalar(
        select(WorkflowNodeResolution)
        .where(WorkflowNodeResolution.action_id == action.id)
        .execution_options(populate_existing=True)
    )
    if (
        node is None
        or node.kind != "analysis"
        or resolution is None
        or resolution.state != "ready"
    ):
        raise HTTPException(409, "Workflow analysis has no ready sealed resolution")
    await verify_workflow_node_resolution(
        db,
        task=task,
        run=run,
        graph=graph,
        node=node,
        action=action,
        resolution=resolution,
    )
    return await verify_analysis_card(
        db, task=task, run=run, action=action, node=node, resolution=resolution
    )


async def approve_workflow_analysis(db, *, task, run, action, current_user):
    from app.models.project import Project
    from app.services.research_runtime import canonical_digest, emit_research_event
    from app.services.workflow_analysis_methods import get_method

    bridge = await verify_analysis_execution(db, task=task, run=run, action=action)
    if (
        bridge is None
        or bridge.source_digest is None
        or bridge.preview_digest != action.preview_digest
    ):
        raise HTTPException(409, "Resolve and review the analysis inputs first")
    await authorize_analysis_sources(
        db,
        task=task,
        run=run,
        action=action,
        snapshot=bridge.input_snapshot,
        extra_user=current_user,
    )
    if bridge.analysis_run_id is not None:
        return await db.get(AnalysisRun, bridge.analysis_run_id)
    user = await db.get(User, action.assignee_user_id)
    method = await get_method(
        db,
        user,
        bridge.method_publication_id,
        project=await db.get(Project, task.project_id),
    )
    selection = AnalysisSelection(
        mode="selected",
        records=[
            {"id": item["record_id"], "version": item["record_version"]}
            for item in bridge.input_snapshot["records"]
        ],
    )
    if method.recipe.get("kind") == "compute":
        from app.services.workflow_compute_runtime import approve_compute_card

        analysis = await approve_compute_card(
            db,
            task=task,
            run=run,
            action=action,
            bridge=bridge,
            method=method,
            selection=selection,
            current_user=current_user,
        )
        action.status = "queued"
        action.revision += 1
        run.status = "waiting_for_compute"
        await emit_research_event(
            db,
            task_id=task.id,
            run_id=run.id,
            action_id=action.id,
            kind="analysis.queued",
            actor_user_id=current_user.id,
            payload={
                "analysis_run_id": str(analysis.id),
                "source_digest": bridge.source_digest,
            },
            idempotency_key=f"workflow-analysis:{action.id}:queued",
        )
        return analysis
    recipe = AnalysisRecipe.model_validate(method.recipe)
    # Ordinary private analysis APIs retain their owner-only policy. This explicit
    # publication is copied as a recipe, never forged as someone's private method.
    preview = await create_preview(
        db,
        AnalysisPreviewRequest(
            protocol_id=method.protocol_id,
            recipe=recipe,
            selection=selection,
            question=action.title,
        ),
        user,
    )
    if (
        preview.source_digest != bridge.source_digest
        or preview.recipe_digest != canonical_digest(method.recipe)
    ):
        raise HTTPException(
            409,
            "Resolved analysis data or Schema changed; use a newly confirmed Workflow",
        )
    analysis = await confirm_analysis(
        db,
        preview_id=preview.id,
        preview_digest=preview.preview_digest,
        key=f"workflow-analysis:{action.id}",
        user=user,
    )
    bridge.analysis_preview_id = preview.id
    bridge.analysis_run_id = analysis.id
    action.status = "queued"
    action.revision += 1
    run.status = "waiting_for_compute"
    await emit_research_event(
        db,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="analysis.queued",
        actor_user_id=current_user.id,
        payload={
            "analysis_run_id": str(analysis.id),
            "source_digest": bridge.source_digest,
        },
        idempotency_key=f"workflow-analysis:{action.id}:queued",
    )
    return analysis


async def workflow_analysis_context(db, analysis_id, *, skip_locked=False):
    """Acquire Task -> Run -> Action before locking the inner Analysis Run."""
    bridge = await db.scalar(
        select(ResearchAnalysisAction).where(
            ResearchAnalysisAction.analysis_run_id == analysis_id
        )
    )
    if bridge is None:
        return None
    action = await db.get(ResearchAction, bridge.action_id)
    run = await db.get(ResearchRun, action.run_id) if action else None
    if action is None or run is None:
        raise HTTPException(409, "Workflow analysis lifecycle is missing")
    task = await db.scalar(
        select(ResearchTask)
        .where(ResearchTask.id == run.task_id)
        .with_for_update(skip_locked=skip_locked)
        .execution_options(populate_existing=True)
    )
    if task is None:
        raise JobDeferred("Workflow context is currently locked or unavailable")
    run = await db.scalar(
        select(ResearchRun)
        .where(ResearchRun.id == run.id)
        .with_for_update(skip_locked=skip_locked)
        .execution_options(populate_existing=True)
    )
    if run is None:
        raise JobDeferred("Workflow Run is currently locked or unavailable")
    action = await db.scalar(
        select(ResearchAction)
        .where(ResearchAction.id == action.id)
        .with_for_update(skip_locked=skip_locked)
        .execution_options(populate_existing=True)
    )
    if action is None:
        raise JobDeferred("Workflow Action is currently locked or unavailable")
    return task, run, action, bridge


async def before_workflow_analysis_execution(db, analysis_id, *, finishing=False):
    from app.services.research_runtime import emit_research_event, utcnow

    context = await workflow_analysis_context(db, analysis_id)
    if context is None:
        return True
    task, run, action, bridge = context
    analysis = await db.get(
        AnalysisRun, analysis_id, with_for_update=True, populate_existing=True
    )
    if analysis.status in {"succeeded", "failed", "cancelled"}:
        return True
    if (
        task.status in {"cancelled", "archived"}
        or run.status == "cancelled"
        or action.status == "cancelled"
    ):
        if analysis.status not in {"succeeded", "failed", "cancelled"}:
            await cancel_analysis(db, analysis)
        return False
    if task.status == "paused" and not finishing:
        raise JobDeferred(
            "Workflow is paused; the same sealed analysis remains pending"
        )
    if task.status not in {"active", "paused"}:
        raise JobDeferred("Workflow is not active")
    try:
        if not finishing:
            from app.services.research_runtime import manual_workflow_dispatch_allowed

            if not await manual_workflow_dispatch_allowed(db, task=task, run=run):
                raise JobDeferred("Workflow dispatch is not currently authorized")
        await verify_analysis_execution(db, task=task, run=run, action=action)
        await authorize_analysis_sources(
            db, task=task, run=run, action=action, snapshot=bridge.input_snapshot
        )
        verify_run_integrity(analysis)
        from app.services.research_runtime import canonical_digest

        if (
            analysis.source_digest != bridge.source_digest
            or canonical_digest(bridge.input_snapshot) != bridge.source_digest
        ):
            raise HTTPException(409, "Workflow analysis sources changed")
    except (HTTPException, ValueError) as error:
        task.status = run.status = "paused"
        task.revision += 1
        run.last_error = (
            str(error.detail) if isinstance(error, HTTPException) else str(error)
        )
        if analysis.status == "running":
            analysis.status = "pending"
        await emit_research_event(
            db,
            task_id=task.id,
            run_id=run.id,
            action_id=action.id,
            kind="workflow.analysis_paused",
            actor_user_id=None,
            payload={"reason": run.last_error},
            idempotency_key=f"workflow-analysis:{action.id}:paused:{task.revision}",
        )
        raise JobDeferred(
            "Workflow analysis source authority must be restored before resuming"
        ) from error
    if not finishing:
        action.status = "running"
        action.started_at = action.started_at or utcnow()
        action.revision += 1
    return True


async def sync_workflow_analysis(db, analysis):
    from app.models.workflow_definition import WorkflowRevision
    from app.services.research_runtime import (
        emit_research_event,
        hold_or_release_aira_action_group,
        utcnow,
    )
    from app.services.workflow_analysis_methods import get_method
    from app.services.workflow_contracts import validate_workflow_graph

    context = await workflow_analysis_context(db, analysis.id)
    if context is None or analysis.status not in {"succeeded", "failed", "cancelled"}:
        return
    task, run, action, bridge = context
    if action.status in {"completed", "failed", "skipped", "cancelled"}:
        if action.status == "completed":
            await hold_or_release_aira_action_group(
                db, task=task, run=run, action=action
            )
        return
    if analysis.status == "succeeded":
        verify_run_integrity(analysis)
        revision = await db.get(
            WorkflowRevision,
            UUID(run.environment_snapshot["manual_workflow"]["revision_id"]),
        )
        graph = validate_workflow_graph(revision.graph)
        node = next(
            item
            for item in graph.nodes
            if item.node_id == action.input_data["action_graph"]["node_id"]
        )
        user = await db.get(User, action.assignee_user_id)
        method = await get_method(db, user, bridge.method_publication_id)
        try:
            projected = await projected_analysis_result(
                db,
                method=method,
                node=node,
                analysis=analysis,
                fields=bridge.input_snapshot["fields"],
            )
        except ValueError as error:
            action.status = "failed"
            action.error = str(error)
            action.output_data = {
                "analysis_result": {
                    "analysis_id": str(analysis.id),
                    "status": "output_contract_failed",
                    "result_digest": analysis.result_digest,
                }
            }
            action.completed_at = utcnow()
            action.revision += 1
            await db.flush()
            await hold_or_release_aira_action_group(
                db, task=task, run=run, action=action
            )
            return
        action.output_data = {
            "analysis_result": {
                "analysis_id": str(analysis.id),
                "source_digest": analysis.source_digest,
                "result_digest": analysis.result_digest,
                "engine_version": analysis.engine_version,
                "outputs": projected,
                "report": analysis.result,
            }
        }
        action.status = "completed"
        action.error = None
    else:
        action.status = "cancelled" if analysis.status == "cancelled" else "failed"
        action.error = analysis.error
        action.output_data = {
            "analysis_result": {
                "analysis_id": str(analysis.id),
                "status": analysis.status,
            }
        }
    action.completed_at = utcnow()
    action.revision += 1
    await emit_research_event(
        db,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind=f"analysis.{action.status}",
        actor_user_id=None,
        payload={
            "analysis_run_id": str(analysis.id),
            "result_digest": analysis.result_digest,
        },
        idempotency_key=f"workflow-analysis:{action.id}:terminal",
    )
    await hold_or_release_aira_action_group(db, task=task, run=run, action=action)


async def cancel_workflow_analyses(db, *, run):
    rows = (
        await db.execute(
            select(ResearchAnalysisAction, AnalysisRun)
            .join(ResearchAction, ResearchAction.id == ResearchAnalysisAction.action_id)
            .join(AnalysisRun, AnalysisRun.id == ResearchAnalysisAction.analysis_run_id)
            .where(ResearchAction.run_id == run.id)
        )
    ).all()
    for _, analysis in rows:
        if analysis.status not in {"succeeded", "failed", "cancelled"}:
            from app.services.analysis_compute_contracts import COMPUTE_ENGINE_VERSION

            if analysis.engine_version != COMPUTE_ENGINE_VERSION:
                await cancel_analysis(db, analysis)
    from app.services.workflow_compute_runtime import stop_workflow_computes

    await stop_workflow_computes(db, run=run)


async def analysis_action_readable(db, *, task, run, action, user):
    from app.models.workflow_definition import WorkflowNodeResolution
    from app.services.research_runtime import canonical_digest
    from app.services.workflow_resolutions import verify_resolution_seal
    from app.services.workflow_visibility import _readable_record

    bridge = await db.get(ResearchAnalysisAction, action.id, populate_existing=True)
    if bridge is None:
        return False
    try:
        resolution = await db.scalar(
            select(WorkflowNodeResolution)
            .where(WorkflowNodeResolution.action_id == action.id)
            .execution_options(populate_existing=True)
        )
        if resolution is None:
            return (
                bridge.source_digest is None
                and action.status == "blocked"
                and not action.input_data.get("workflow_resolution")
                and not action.input_data.get("analysis_input")
                and not action.output_data
            )
        verify_resolution_seal(resolution)
        reference = {
            "id": str(resolution.id),
            "digest": resolution.digest,
            "state": resolution.state,
            "receipt": resolution.receipt,
        }
        if (
            action.input_data.get("workflow_resolution") != reference
            or resolution.run_id != run.id
            or resolution.task_id != task.id
            or str(resolution.workflow_revision_id)
            != run.environment_snapshot["manual_workflow"]["revision_id"]
        ):
            return False
        from app.models.project import Project

        project = await db.get(Project, task.project_id)
        for source in resolution.receipt["sources"].values():
            await _readable_record(
                db, source=source, current_user=user, project=project
            )
        if bridge.source_digest is None:
            return (
                resolution.state != "ready"
                and not action.input_data.get("analysis_input")
                and not (action.output_data or {}).get("analysis_result")
            )
        if canonical_digest(bridge.input_snapshot) != bridge.source_digest:
            return False
        if (
            resolution.run_id != run.id
            or resolution.task_id != task.id
            or resolution.digest != bridge.resolution_digest
            or resolution.state != "ready"
            or (resolution.receipt.get("analysis_input") or {}).get("source_digest")
            != bridge.source_digest
            or resolution.receipt.get("analysis_input")
            != action.input_data.get("analysis_input")
            or action.preview_digest != bridge.preview_digest
        ):
            return False
        _, project, own_only = await analysis_scope(
            db, UUID(bridge.input_snapshot["protocol_id"]), user
        )
        if project.id != task.project_id:
            return False
        await authorize_source_manifest(
            db,
            UUID(bridge.input_snapshot["protocol_id"]),
            user,
            bridge.input_snapshot["records"],
            own_only=own_only,
        )
        for record in bridge.input_snapshot["records"]:
            actual = await _readable_record(
                db,
                source={**record, "protocol_id": bridge.input_snapshot["protocol_id"]},
                current_user=user,
                project=project,
            )
            if canonical_digest(actual.data) != canonical_digest(record["data"]):
                return False
        if bridge.analysis_run_id:
            analysis = await db.get(
                AnalysisRun, bridge.analysis_run_id, populate_existing=True
            )
            if analysis is None:
                return False
            verify_run_integrity(analysis)
            output = (action.output_data or {}).get("analysis_result") or {}
            if (
                analysis.status == "succeeded"
                and action.status == "completed"
                and (
                    output.get("result_digest") != analysis.result_digest
                    or output.get("report") != analysis.result
                )
            ):
                return False
            if action.status == "completed":
                from app.models.workflow_definition import WorkflowRevision
                from app.services.workflow_definitions import verify_revision

                revision = await db.get(
                    WorkflowRevision,
                    UUID(run.environment_snapshot["manual_workflow"]["revision_id"]),
                )
                graph = verify_revision(revision)
                node = next(
                    item for item in graph.nodes if item.node_id == resolution.node_id
                )
                from app.services.workflow_analysis_methods import get_method

                method = await get_method(db, user, bridge.method_publication_id)
                if output.get("outputs") != await projected_analysis_result(
                    db,
                    method=method,
                    node=node,
                    analysis=analysis,
                    fields=bridge.input_snapshot["fields"],
                ):
                    return False
    except (HTTPException, KeyError, ValueError, TypeError):
        return False
    return True


async def projected_analysis_result(db, *, method, node, analysis, fields):
    if method.recipe.get("kind") == "compute":
        from app.services.research_instruments import validate_schema_payload
        from app.services.workflow_compute_contracts import (
            compute_output_catalog,
            project_compute_outputs,
        )
        from app.services.workflow_compute_runtime import verify_bound_compute

        await verify_bound_compute(db, analysis)
        schema = method.compute_contract["result_schema"]
        validate_schema_payload(
            schema, analysis.result["computed_result"], "published Compute result"
        )
        catalog = compute_output_catalog(schema, node.compute_outputs)
        return project_compute_outputs(
            schema, analysis.result, node.compute_outputs, catalog
        )
    from app.services.workflow_analysis_contracts import (
        analysis_output_catalog,
        project_analysis_outputs,
    )

    catalog = analysis_output_catalog(method.recipe, fields, node.analysis_outputs)
    return project_analysis_outputs(
        method.recipe, analysis.result, node.analysis_outputs, catalog
    )
