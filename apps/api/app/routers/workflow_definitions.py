"""Versioned, deterministic Project Workflows alongside legacy /workflow."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from app.database import DBSession
from app.models.protocol import Protocol, ProtocolKind
from app.models.protocol_version import ProtocolVersion
from app.models.research import (
    ResearchAction,
    ResearchRun,
    ResearchRunStatus,
    ResearchTask,
    ResearchTaskStatus,
)
from app.models.user import User
from app.models.workflow_definition import (
    WorkflowDefinition,
    WorkflowRevision,
    WorkflowRunBinding,
)
from app.routers.depends import CurrentUser
from app.services.research_budget import reached_operational_limit
from app.services.research_runtime import (
    canonical_digest,
    emit_research_event,
    require_research_capability,
    utcnow,
)
from app.services.workflow_contracts import workflow_revision_digest
from app.services.workflow_data import protocol_field_catalog
from app.services.workflow_definitions import (
    WorkflowConfirm,
    WorkflowDraft,
    WorkflowRunConfirm,
    WorkflowRunDraft,
    capabilities,
    definition,
    definition_payload,
    preview_draft,
    request_lock,
    require_protocol_read,
    resolve_pins,
    scope,
    verify_revision,
)

router = APIRouter(prefix="/workflow-definitions", tags=["workflow-definitions"])


def workflow_version_context(version):
    targets = protocol_field_catalog(version, for_target=True, include_files=True)
    return {
        "id": version.id,
        "version": version.version,
        "fields": [
            {
                "path": list(path),
                "title": path[-1],
                "bindable_target": path in targets,
                **spec.model_dump(mode="json"),
            }
            for path, spec in protocol_field_catalog(version, include_files=True).items()
        ],
    }


@router.get("")
async def list_definitions(
    project_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    project = await scope(db_session, current_user, project_id)
    rows = (
        await db_session.scalars(
            select(WorkflowDefinition)
            .where(WorkflowDefinition.project_id == project.id)
            .order_by(WorkflowDefinition.updated_at.desc())
            .limit(100)
        )
    ).all()
    items = []
    for item in rows:
        try:
            items.append(
                await definition_payload(db_session, current_user, item, project)
            )
        except HTTPException as exc:
            if exc.status_code not in {403, 404}:
                raise
    return {
        "items": items,
        "capabilities": await capabilities(db_session, current_user, project),
    }


@router.get("/context")
async def workflow_context(
    project_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    project = await scope(db_session, current_user, project_id)
    protocols = []
    from app.services.workflow_analysis_methods import list_methods

    rows = (
        await db_session.scalars(
            select(Protocol)
            .where(
                Protocol.project_id == project.id,
                Protocol.deleted_at.is_(None),
                Protocol.kind == ProtocolKind.EXPERIMENT,
            )
            .order_by(Protocol.name)
            .limit(500)
        )
    ).all()
    for protocol in rows:
        try:
            await require_protocol_read(db_session, current_user, project, protocol)
        except HTTPException as exc:
            if exc.status_code != 403:
                raise
            continue
        versions = (
            await db_session.scalars(
                select(ProtocolVersion)
                .where(ProtocolVersion.protocol_id == protocol.id)
                .order_by(ProtocolVersion.created_at.desc())
            )
        ).all()
        protocols.append(
            {
                "id": protocol.id,
                "name": protocol.name,
                "versions": [workflow_version_context(item) for item in versions],
            }
        )
    rows = (
        await db_session.execute(
            select(ResearchTask, ResearchRun)
            .join(ResearchRun, ResearchRun.task_id == ResearchTask.id)
            .where(
                ResearchTask.project_id == project.id,
                ResearchTask.archived_at.is_(None),
                ResearchTask.status == ResearchTaskStatus.DRAFT.value,
                ResearchRun.status == ResearchRunStatus.DRAFT.value,
            )
            .order_by(ResearchTask.created_at.desc())
            .limit(100)
        )
    ).all()
    readable_ids = {str(item["id"]) for item in protocols}
    tasks = [
        {
            "id": task.id,
            "title": task.title,
            "revision": task.revision,
            "run_id": run.id,
            "protocols": (run.environment_snapshot or {}).get("protocols", []),
            "compute": (run.environment_snapshot or {}).get("compute", []),
            "owner_user_id": task.owner_user_id,
            "budget_limit": task.budget_limit,
            "budget_currency": task.budget_currency,
            "deadline_at": task.deadline_at,
        }
        for task, run in rows
        if all(
            str(pin.get("id")) in readable_ids
            for pin in (run.environment_snapshot or {}).get("protocols", [])
        )
    ]
    unavailable_methods = []
    methods = await list_methods(
        db_session, current_user, project, unavailable=unavailable_methods
    )
    from app.services.workflow_compute_governance import approver_candidates

    return {
        "protocols": protocols,
        "analysis_methods": methods,
        "compute_approvers": await approver_candidates(
            db_session, current_user, project
        ),
        "analysis_method_warnings": unavailable_methods,
        "tasks": tasks,
        "capabilities": await capabilities(db_session, current_user, project),
    }


@router.post("/preview")
async def preview_workflow(
    params: WorkflowDraft, current_user: CurrentUser, db_session: DBSession
):
    preview, _, _ = await preview_draft(db_session, current_user, params)
    return preview


@router.post("/confirm")
async def confirm_workflow(
    params: WorkflowConfirm, current_user: CurrentUser, db_session: DBSession
):
    await scope(db_session, current_user, params.project_id, "research.create")
    await request_lock(db_session, current_user.id, params.idempotency_key)
    request_digest = canonical_digest(
        params.model_dump(mode="json", exclude={"idempotency_key"})
    )
    previous = (
        await db_session.scalars(
            select(WorkflowRevision).where(
                WorkflowRevision.created_by_user_id == current_user.id,
                WorkflowRevision.idempotency_key == params.idempotency_key,
            )
        )
    ).first()
    if previous is not None:
        if previous.request_digest != request_digest:
            raise HTTPException(
                409, "Idempotency key already belongs to another Workflow confirmation"
            )
        item, project = await definition(
            db_session, current_user, previous.definition_id
        )
        result = await definition_payload(
            db_session, current_user, item, project, history=True
        )
        return {**result, "confirmed_revision_id": previous.id}
    preview, item, project = await preview_draft(
        db_session, current_user, params, lock=True
    )
    if preview["preview_digest"] != params.preview_digest:
        raise HTTPException(
            409, "Workflow preview changed; preview again before confirmation"
        )
    if item is None:
        item = WorkflowDefinition(
            project_id=project.id,
            title=params.title,
            description=params.description,
            revision=1,
            created_by_user_id=current_user.id,
        )
        db_session.add(item)
        await db_session.flush()
    else:
        item.title, item.description = params.title, params.description
        item.revision += 1
    content = {key: preview[key] for key in ("title", "description", "graph", "pins")}
    revision = WorkflowRevision(
        definition_id=item.id,
        revision=item.revision,
        **content,
        digest=canonical_digest(content),
        request_digest=request_digest,
        idempotency_key=params.idempotency_key,
        created_by_user_id=current_user.id,
    )
    db_session.add(revision)
    await db_session.commit()
    result = await definition_payload(
        db_session, current_user, item, project, history=True
    )
    return {**result, "confirmed_revision_id": revision.id}


@router.get("/{definition_id}")
async def get_workflow(
    definition_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    item, project = await definition(db_session, current_user, definition_id)
    result = await definition_payload(
        db_session, current_user, item, project, history=True
    )
    rows = (
        await db_session.execute(
            select(WorkflowRunBinding, ResearchRun)
            .join(ResearchRun, ResearchRun.id == WorkflowRunBinding.run_id)
            .join(
                WorkflowRevision,
                WorkflowRevision.id == WorkflowRunBinding.workflow_revision_id,
            )
            .where(WorkflowRevision.definition_id == item.id)
            .order_by(WorkflowRunBinding.created_at.desc())
            .limit(100)
        )
    ).all()
    result["runs"] = []
    for binding, run in rows:
        actions = list(
            (
                await db_session.scalars(
                    select(ResearchAction)
                    .where(ResearchAction.run_id == run.id)
                    .order_by(ResearchAction.sequence)
                )
            ).all()
        )
        result["runs"].append(
            {
                "task_id": binding.task_id,
                "run_id": run.id,
                "workflow_revision_id": binding.workflow_revision_id,
                "status": run.status,
                "actions": [
                    {
                        "id": action.id,
                        "node_id": (
                            (action.input_data or {}).get("action_graph") or {}
                        ).get("node_id"),
                        "title": action.title,
                        "status": action.status,
                        "skip_reason": (
                            "branch_not_selected"
                            if action.status == "skipped"
                            and (
                                (action.output_data or {}).get("workflow_resolution")
                                or {}
                            ).get("state")
                            == "branch_not_selected"
                            else "dependency_failed"
                            if action.status == "skipped"
                            else None
                        ),
                        "error": action.error,
                    }
                    for action in actions
                ],
            }
        )
    result["capabilities"] = await capabilities(db_session, current_user, project)
    return result


async def run_preview(db, user, definition_id, params, *, lock=False):
    item, project = await definition(db, user, definition_id)
    await require_research_capability(
        db, user=user, project=project, capability="research.run"
    )
    revision = await db.get(WorkflowRevision, params.workflow_revision_id)
    if revision is None or revision.definition_id != item.id:
        raise HTTPException(404, "Workflow revision not found")
    graph = verify_revision(revision)
    pins = await resolve_pins(db, user, project, graph)
    if {pin["node_id"]: pin["content_digest"] for pin in pins} != {
        pin["node_id"]: pin["content_digest"] for pin in revision.pins
    }:
        raise HTTPException(
            409, "Pinned Protocol content changed; publish a new Workflow revision"
        )
    statement = select(ResearchTask).where(ResearchTask.id == params.task_id)
    if lock:
        statement = statement.with_for_update().execution_options(
            populate_existing=True
        )
    task = (await db.scalars(statement)).first()
    if task is None or task.project_id != project.id or task.archived_at is not None:
        raise HTTPException(404, "Research Task not found in this Project")
    if (
        task.status != ResearchTaskStatus.DRAFT.value
        or task.revision != params.expected_task_revision
    ):
        raise HTTPException(409, "Select an unchanged draft Research Task")
    statement = (
        select(ResearchRun)
        .where(ResearchRun.task_id == task.id)
        .order_by(ResearchRun.run_number.desc())
        .limit(1)
    )
    if lock:
        statement = statement.with_for_update().execution_options(
            populate_existing=True
        )
    run = (await db.scalars(statement)).first()
    if run is None or run.status != ResearchRunStatus.DRAFT.value:
        raise HTTPException(409, "Draft Research Run not found")
    if await db.scalar(
        select(ResearchAction.id).where(ResearchAction.run_id == run.id).limit(1)
    ):
        raise HTTPException(
            409, "Workflow requires a draft Run without existing Actions"
        )
    owner = await db.get(User, task.owner_user_id)
    if owner is None:
        raise HTTPException(409, "Research Task owner is unavailable")
    await require_research_capability(
        db, user=owner, project=project, capability="research.run"
    )
    await resolve_pins(db, owner, project, graph)
    environment = run.environment_snapshot or {}
    pinned = {
        (str(pin.get("id")), str(pin.get("version_id")))
        for pin in environment.get("protocols", [])
    }
    if any(
        (str(node.protocol_id), str(node.protocol_version_id)) not in pinned
        for node in graph.nodes
        if node.kind == "protocol"
    ):
        raise HTTPException(
            409,
            "Every card must match an exact Protocol version in the selected Research Environment",
        )
    limit = await reached_operational_limit(db, task=task)
    if limit:
        raise HTTPException(409, f"Research Task {limit[0]} limit has been reached")
    from app.services.workflow_compute_governance import preview_compute_governance

    governance = await preview_compute_governance(
        db,
        user=user,
        owner=owner,
        project=project,
        task=task,
        run=run,
        graph=graph,
        approvers=params.compute_approvers,
    )
    command = {
        "definition_id": str(item.id),
        "workflow_revision_id": str(revision.id),
        "workflow_digest": revision.digest,
        "task_id": str(task.id),
        "expected_task_revision": task.revision,
        "run_id": str(run.id),
        "environment_digest": canonical_digest(environment),
        "title": revision.title,
        "nodes": graph.model_dump(mode="json")["nodes"],
        "edges": graph.model_dump(mode="json")["edges"],
        "bindings": graph.model_dump(mode="json")["bindings"],
        "execution_contract_version": graph.schema_version + 1,
        "pins": pins,
        "environment": environment,
        "owner": {"id": str(owner.id), "name": owner.name, "username": owner.username},
        "requested_by_user_id": str(user.id),
        "destination": "project_research_task",
    }
    if graph.schema_version >= 3:
        command["compute_governance"] = governance
    return (
        {
            **command,
            "preview_digest": canonical_digest({"user_id": str(user.id), **command}),
        },
        task,
        run,
        revision,
        graph,
    )


@router.post("/{definition_id}/runs/preview")
async def preview_workflow_run(
    definition_id: UUID,
    params: WorkflowRunDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    result, *_ = await run_preview(db_session, current_user, definition_id, params)
    return result


async def run_result(db, binding):
    actions = (
        await db.scalars(
            select(ResearchAction)
            .where(ResearchAction.run_id == binding.run_id)
            .order_by(ResearchAction.sequence)
        )
    ).all()
    return {
        "task_id": binding.task_id,
        "run_id": binding.run_id,
        "workflow_revision_id": binding.workflow_revision_id,
        "actions": [
            {
                "id": action.id,
                "status": action.status,
                "node_id": (action.input_data or {})
                .get("action_graph", {})
                .get("node_id"),
            }
            for action in actions
        ],
    }


@router.post("/{definition_id}/runs/confirm")
async def confirm_workflow_run(
    definition_id: UUID,
    params: WorkflowRunConfirm,
    current_user: CurrentUser,
    db_session: DBSession,
):
    _, project = await definition(db_session, current_user, definition_id)
    await require_research_capability(
        db_session, user=current_user, project=project, capability="research.run"
    )
    await request_lock(db_session, current_user.id, params.idempotency_key)
    request_digest = canonical_digest(
        {
            "definition_id": str(definition_id),
            **params.model_dump(mode="json", exclude={"idempotency_key"}),
        }
    )
    previous = (
        await db_session.scalars(
            select(WorkflowRunBinding).where(
                WorkflowRunBinding.created_by_user_id == current_user.id,
                WorkflowRunBinding.idempotency_key == params.idempotency_key,
            )
        )
    ).first()
    if previous is not None:
        if previous.request_digest != request_digest:
            raise HTTPException(
                409, "Idempotency key already belongs to another Workflow run"
            )
        # Recheck all sources, but never start or queue another Action on replay.
        revision = await db_session.get(WorkflowRevision, previous.workflow_revision_id)
        await resolve_pins(db_session, current_user, project, verify_revision(revision))
        return await run_result(db_session, previous)
    preview, task, run, revision, graph = await run_preview(
        db_session, current_user, definition_id, params, lock=True
    )
    if preview["preview_digest"] != params.preview_digest:
        raise HTTPException(409, "Workflow run preview changed; preview again")
    marker = {
        "definition_id": str(definition_id),
        "revision_id": str(revision.id),
        "digest": workflow_revision_digest(graph),
        "revision_digest": revision.digest,
        "execution_contract_version": graph.schema_version + 1,
    }
    if graph.schema_version >= 3:
        marker["compute_governance"] = preview["compute_governance"]
    run.environment_snapshot = {**run.environment_snapshot, "manual_workflow": marker}
    run.requested_by_user_id = current_user.id
    binding = WorkflowRunBinding(
        workflow_revision_id=revision.id,
        task_id=task.id,
        run_id=run.id,
        environment_digest=canonical_digest(run.environment_snapshot),
        request_digest=request_digest,
        idempotency_key=params.idempotency_key,
        created_by_user_id=current_user.id,
    )
    db_session.add(binding)
    task.status = ResearchTaskStatus.ACTIVE.value
    task.revision += 1
    run.status, run.started_at, run.last_error = (
        ResearchRunStatus.RUNNING.value,
        utcnow(),
        None,
    )
    from app.services.research_runtime import materialize_manual_workflow

    try:
        await materialize_manual_workflow(
            db_session,
            task=task,
            run=run,
            graph=graph,
            workflow_revision_id=revision.id,
            workflow_digest=marker["digest"],
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        kind="run.started",
        actor_user_id=current_user.id,
        payload={"ai": False, "source": "manual_workflow", **marker},
        idempotency_key=f"run:{run.id}:started",
    )
    await db_session.commit()
    return await run_result(db_session, binding)
