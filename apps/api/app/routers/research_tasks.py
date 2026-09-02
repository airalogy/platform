"""Research Task workbench and human-in-the-loop execution APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, or_, select

from app.config import config
from app.database import DBSession
from app.models.knowledge import KnowledgeItem, KnowledgeState, Visibility
from app.models.lab import Lab
from app.models.project import Project
from app.models.protocol import Protocol, ProtocolKind
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.research import (
    HumanWorkItemStatus,
    ResearchAction,
    ResearchActionKind,
    ResearchActionStatus,
    ResearchApproval,
    ResearchApprovalStatus,
    ResearchArtifactLink,
    ResearchEvent,
    ResearchHumanWorkItem,
    ResearchPlanVersion,
    ResearchProtocolRun,
    ResearchRun,
    ResearchRunStatus,
    ResearchTask,
    ResearchTaskKnowledge,
    ResearchTaskOutcome,
    ResearchTaskProtocol,
    ResearchTaskStatus,
    ScientificOutcome,
)
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.access_control import resolve_structured_access
from app.services.knowledge import authorize_knowledge_item, snapshot_knowledge
from app.services.research_runtime import (
    ACTIVE_WORK_ITEM_STATUSES,
    activate_protocol_action,
    canonical_digest,
    create_plan_version,
    emit_research_event,
    enqueue_research_advance,
    initial_aira_state,
    require_research_capability,
    research_task_command,
    task_protocol_rows,
    utcnow,
    workflow_info_for_task,
)

router = APIRouter(prefix="/research-tasks", tags=["research-tasks"])
work_items_router = APIRouter(
    prefix="/research-work-items", tags=["research-work-items"]
)
approvals_router = APIRouter(prefix="/research-approvals", tags=["research-approvals"])


class ResearchTaskDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    title: str = Field(min_length=1, max_length=255)
    goal: str = Field(min_length=1, max_length=20_000)
    success_criteria: list[str] = Field(min_length=1, max_length=50)
    stop_conditions: list[str] = Field(default_factory=list, max_length=50)
    autonomy_level: Literal[
        "assisted", "bounded_autopilot", "autonomous_within_policy"
    ] = "assisted"
    protocol_ids: list[UUID] = Field(default_factory=list, max_length=100)
    knowledge_ids: list[UUID] = Field(default_factory=list, max_length=50)
    owner_user_id: UUID | None = None
    ai_model: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def normalize_text(self):
        self.title = self.title.strip()
        self.goal = self.goal.strip()
        self.success_criteria = [
            item.strip() for item in self.success_criteria if item.strip()
        ]
        self.stop_conditions = [
            item.strip() for item in self.stop_conditions if item.strip()
        ]
        if not self.title or not self.goal or not self.success_criteria:
            raise ValueError("Title, goal, and success criteria are required")
        if len(set(self.protocol_ids)) != len(self.protocol_ids):
            raise ValueError("Protocol selection contains duplicates")
        if len(set(self.knowledge_ids)) != len(self.knowledge_ids):
            raise ValueError("Knowledge selection contains duplicates")
        return self


class ResearchTaskCreate(ResearchTaskDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class TaskTransitionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    reason: str = Field(default="", max_length=4_000)


class TaskCompleteParams(TaskTransitionParams):
    outcome: ResearchTaskOutcome
    scientific_outcome: ScientificOutcome
    conclusion: str = Field(min_length=1, max_length=100_000)


class ManualProtocolActionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_id: UUID
    assignee_user_id: UUID | None = None
    title: str | None = Field(default=None, max_length=255)
    instructions: str = Field(default="", max_length=20_000)
    initial_values: dict[str, Any] = Field(default_factory=dict)
    due_at: datetime | None = None
    idempotency_key: str = Field(min_length=8, max_length=160)


class ManualProtocolActionCreate(ManualProtocolActionDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class WorkItemRevisionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)


class WorkItemAssignParams(WorkItemRevisionParams):
    assignee_user_id: UUID
    reason: str = Field(min_length=1, max_length=4_000)


class WorkItemSubmitParams(WorkItemRevisionParams):
    record_id: UUID
    record_version: int | None = Field(default=None, ge=1)
    note: str = Field(default="", max_length=20_000)


class ApprovalDecisionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    expected_action_revision: int = Field(ge=1)
    preview_digest: str = Field(min_length=64, max_length=64)
    reason: str = Field(default="", max_length=4_000)


class ApprovalRejectParams(ApprovalDecisionParams):
    reason: str = Field(min_length=1, max_length=4_000)


async def _project(db_session: DBSession, project_id: UUID) -> Project:
    project = await Project.find_by(
        db_session,
        [Project.id == project_id, Project.deleted_at.is_(None)],
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _task_context(
    db_session: DBSession,
    current_user: User,
    task_id: UUID,
    capability: str = "research.read",
) -> tuple[ResearchTask, Project, Lab]:
    task = await db_session.get(ResearchTask, task_id)
    if task is None or task.archived_at is not None:
        raise HTTPException(status_code=404, detail="Research Task not found")
    project = await _project(db_session, task.project_id)
    await require_research_capability(
        db_session, user=current_user, project=project, capability=capability
    )
    lab = await db_session.get(Lab, task.lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    return task, project, lab


async def _latest_run(db_session: DBSession, task_id: UUID) -> ResearchRun | None:
    return (
        await db_session.scalars(
            select(ResearchRun)
            .where(ResearchRun.task_id == task_id)
            .order_by(ResearchRun.run_number.desc())
            .limit(1)
        )
    ).first()


async def _validate_task_draft(
    db_session: DBSession,
    current_user: User,
    draft: ResearchTaskDraft,
) -> tuple[
    dict[str, Any],
    Project,
    Lab,
    User,
    list[tuple[Protocol, ProtocolVersion]],
    list[KnowledgeItem],
]:
    project = await _project(db_session, draft.project_id)
    await require_research_capability(
        db_session,
        user=current_user,
        project=project,
        capability="research.create",
    )
    lab = await db_session.get(Lab, project.lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")

    owner_id = draft.owner_user_id or current_user.id
    owner = await db_session.get(User, owner_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="Task owner not found")
    await require_research_capability(
        db_session,
        user=owner,
        project=project,
        capability="research.run",
    )

    protocols: list[tuple[Protocol, ProtocolVersion]] = []
    for protocol_id in draft.protocol_ids:
        protocol = await Protocol.find_by(
            db_session,
            [
                Protocol.id == protocol_id,
                Protocol.project_id == project.id,
                Protocol.deleted_at.is_(None),
                Protocol.kind == ProtocolKind.EXPERIMENT,
            ],
        )
        if protocol is None:
            raise HTTPException(
                status_code=422,
                detail=f"Protocol {protocol_id} is not available in this Project",
            )
        version = await ProtocolVersion.find_by(
            db_session,
            [
                ProtocolVersion.protocol_id == protocol.id,
                ProtocolVersion.version == protocol.latest_version,
            ],
        )
        if version is None:
            raise HTTPException(
                status_code=409,
                detail=f"Protocol {protocol.name} has no executable version",
            )
        protocols.append((protocol, version))

    knowledge_items: list[KnowledgeItem] = []
    for knowledge_id in draft.knowledge_ids:
        item = await db_session.get(KnowledgeItem, knowledge_id)
        if item is None:
            raise HTTPException(
                status_code=422,
                detail=f"Knowledge {knowledge_id} is not available",
            )
        await authorize_knowledge_item(db_session, current_user, item)
        belongs_to_environment = (
            item.scope_type == "project" and item.project_id == project.id
        ) or (item.scope_type == "lab" and item.lab_id == lab.id)
        if not belongs_to_environment:
            raise HTTPException(
                status_code=422,
                detail="Knowledge must belong to this Project or its Lab",
            )
        if item.visibility == Visibility.RESTRICTED.value:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Restricted Knowledge cannot be placed in a shared Research "
                    "Environment; publish a scoped non-restricted derivative first"
                ),
            )
        if item.state != KnowledgeState.REVIEWED.value:
            raise HTTPException(
                status_code=422,
                detail="Only reviewed Knowledge can be pinned to a Research Task",
            )
        knowledge_items.append(item)

    command = research_task_command(
        project_id=project.id,
        title=draft.title,
        goal=draft.goal,
        success_criteria=draft.success_criteria,
        stop_conditions=draft.stop_conditions,
        autonomy_level=draft.autonomy_level,
        protocol_ids=[protocol.id for protocol, _version in protocols],
        knowledge_refs=[
            {"id": item.id, "revision": item.revision} for item in knowledge_items
        ],
        owner_user_id=owner.id,
        ai_model=draft.ai_model,
    )
    return command, project, lab, owner, protocols, knowledge_items


def _task_preview(
    *,
    command: dict[str, Any],
    project: Project,
    lab: Lab,
    owner: User,
    protocols: list[tuple[Protocol, ProtocolVersion]],
    knowledge_items: list[KnowledgeItem],
) -> dict[str, Any]:
    ai_path_available = config.effective_ai_enabled and bool(protocols)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": {
            "lab": {"id": str(lab.id), "uid": lab.uid, "name": lab.name},
            "project": {
                "id": str(project.id),
                "uid": project.uid,
                "name": project.name,
            },
        },
        "owner": {
            "id": str(owner.id),
            "username": owner.username,
            "name": owner.name,
        },
        "protocols": [
            {
                "id": str(protocol.id),
                "uid": protocol.uid,
                "name": protocol.name,
                "version": version.version,
            }
            for protocol, version in protocols
        ],
        "knowledge": [
            {
                "id": str(item.id),
                "title": item.title,
                "kind": item.kind,
                "revision": item.revision,
                "scope_type": item.scope_type,
            }
            for item in knowledge_items
        ],
        "effects": [
            "Create a versioned Research Task and draft Research Run",
            "Pin the selected Protocol versions in the Research Environment",
            "Pin reviewed Knowledge revisions in the Research Environment",
            (
                "Use AIRA after the Task is started"
                if ai_path_available
                else "Keep execution under deterministic manual control"
            ),
        ],
        "warnings": (
            []
            if ai_path_available
            else [
                "Aira is unavailable or no Protocol is selected. The Task remains fully usable through manual Protocol Actions."
            ]
        ),
        "ai_path_available": ai_path_available,
    }


def _user_data(user: User | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {"id": str(user.id), "username": user.username, "name": user.name}


async def _task_summary(
    db_session: DBSession,
    task: ResearchTask,
    *,
    project: Project | None = None,
    lab: Lab | None = None,
) -> dict[str, Any]:
    project = project or await db_session.get(Project, task.project_id)
    lab = lab or await db_session.get(Lab, task.lab_id)
    owner = await db_session.get(User, task.owner_user_id)
    run = await _latest_run(db_session, task.id)
    open_items = await db_session.scalar(
        select(func.count())
        .select_from(ResearchHumanWorkItem)
        .join(ResearchAction, ResearchAction.id == ResearchHumanWorkItem.action_id)
        .join(ResearchRun, ResearchRun.id == ResearchAction.run_id)
        .where(
            ResearchRun.task_id == task.id,
            ResearchHumanWorkItem.status.in_(ACTIVE_WORK_ITEM_STATUSES),
        )
    )
    pending_approvals = await db_session.scalar(
        select(func.count())
        .select_from(ResearchApproval)
        .join(ResearchAction, ResearchAction.id == ResearchApproval.action_id)
        .join(ResearchRun, ResearchRun.id == ResearchAction.run_id)
        .where(
            ResearchRun.task_id == task.id,
            ResearchApproval.status == ResearchApprovalStatus.PENDING.value,
        )
    )
    return {
        **task.as_dict(),
        "owner": _user_data(owner),
        "project": {
            "id": str(project.id),
            "uid": project.uid,
            "name": project.name,
        },
        "lab": {"id": str(lab.id), "uid": lab.uid, "name": lab.name},
        "latest_run": run.as_dict() if run is not None else None,
        "open_work_items": open_items or 0,
        "pending_approvals": pending_approvals or 0,
        "ai_available": config.effective_ai_enabled,
    }


async def _action_data(
    db_session: DBSession,
    action: ResearchAction,
    *,
    project: Project,
    lab: Lab,
) -> dict[str, Any]:
    assignee = (
        await db_session.get(User, action.assignee_user_id)
        if action.assignee_user_id
        else None
    )
    protocol_run = await ResearchProtocolRun.find_by(
        db_session, [ResearchProtocolRun.action_id == action.id]
    )
    work_item = await ResearchHumanWorkItem.find_by(
        db_session, [ResearchHumanWorkItem.action_id == action.id]
    )
    approval = (
        await db_session.scalars(
            select(ResearchApproval)
            .where(ResearchApproval.action_id == action.id)
            .order_by(ResearchApproval.requested_at.desc())
            .limit(1)
        )
    ).first()
    protocol_data = None
    if protocol_run is not None:
        protocol = await db_session.get(Protocol, protocol_run.protocol_id)
        if protocol is not None:
            protocol_data = {
                "id": str(protocol.id),
                "uid": protocol.uid,
                "name": protocol.name,
                "version": protocol_run.protocol_version,
                "lab_uid": lab.uid,
                "project_uid": project.uid,
            }
    return {
        **action.as_dict(),
        "assignee": _user_data(assignee),
        "protocol_run": protocol_run.as_dict() if protocol_run else None,
        "protocol": protocol_data,
        "work_item": work_item.as_dict() if work_item else None,
        "approval": (
            await _approval_summary(db_session, approval)
            if approval is not None
            else None
        ),
    }


async def _approval_summary(
    db_session: DBSession,
    approval: ResearchApproval,
) -> dict[str, Any]:
    approver = await db_session.get(User, approval.approver_user_id)
    requested_by = await db_session.get(User, approval.requested_by_user_id)
    decided_by = (
        await db_session.get(User, approval.decided_by_user_id)
        if approval.decided_by_user_id
        else None
    )
    return {
        **approval.as_dict(),
        "approver": _user_data(approver),
        "requested_by": _user_data(requested_by),
        "decided_by": _user_data(decided_by),
    }


async def _task_detail(
    db_session: DBSession,
    task: ResearchTask,
    project: Project,
    lab: Lab,
) -> dict[str, Any]:
    summary = await _task_summary(db_session, task, project=project, lab=lab)
    runs = list(
        (
            await db_session.scalars(
                select(ResearchRun)
                .where(ResearchRun.task_id == task.id)
                .order_by(ResearchRun.run_number.desc())
            )
        ).all()
    )
    run_ids = [run.id for run in runs]
    actions = (
        list(
            (
                await db_session.scalars(
                    select(ResearchAction)
                    .where(ResearchAction.run_id.in_(run_ids))
                    .order_by(
                        ResearchAction.created_at.desc(), ResearchAction.sequence.desc()
                    )
                )
            ).all()
        )
        if run_ids
        else []
    )
    events = list(
        (
            await db_session.scalars(
                select(ResearchEvent)
                .where(ResearchEvent.task_id == task.id)
                .order_by(ResearchEvent.created_at.desc())
                .limit(200)
            )
        ).all()
    )
    plans = (
        list(
            (
                await db_session.scalars(
                    select(ResearchPlanVersion)
                    .where(ResearchPlanVersion.run_id.in_(run_ids))
                    .order_by(
                        ResearchPlanVersion.created_at.desc(),
                        ResearchPlanVersion.version.desc(),
                    )
                )
            ).all()
        )
        if run_ids
        else []
    )
    protocols = [
        {
            "id": str(protocol.id),
            "uid": protocol.uid,
            "name": protocol.name,
            "version": version.version,
            "position": task_protocol.position,
        }
        for task_protocol, protocol, version in await task_protocol_rows(
            db_session, task.id
        )
    ]
    knowledge = [
        {
            **row.snapshot,
            "id": str(row.knowledge_item_id),
            "revision": row.knowledge_revision,
            "position": row.position,
        }
        for row in list(
            (
                await db_session.scalars(
                    select(ResearchTaskKnowledge)
                    .where(ResearchTaskKnowledge.task_id == task.id)
                    .order_by(ResearchTaskKnowledge.position)
                )
            ).all()
        )
    ]
    return {
        **summary,
        "runs": [run.as_dict() for run in runs],
        "actions": [
            await _action_data(db_session, action, project=project, lab=lab)
            for action in actions
        ],
        "events": [event.as_dict() for event in events],
        "plan_versions": [plan.as_dict() for plan in plans],
        "protocols": protocols,
        "knowledge": knowledge,
    }


@router.post("/preview")
async def preview_research_task(
    params: ResearchTaskDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    command, project, lab, owner, protocols, knowledge_items = await _validate_task_draft(
        db_session, current_user, params
    )
    return _task_preview(
        command=command,
        project=project,
        lab=lab,
        owner=owner,
        protocols=protocols,
        knowledge_items=knowledge_items,
    )


@router.post("")
async def create_research_task(
    params: ResearchTaskCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    command, project, lab, owner, protocols, knowledge_items = await _validate_task_draft(
        db_session, current_user, params
    )
    expected_digest = canonical_digest(command)
    if params.preview_digest != expected_digest:
        raise HTTPException(
            status_code=409,
            detail="The Research Task preview is stale; preview it again before creating.",
        )

    task = ResearchTask(
        lab_id=lab.id,
        project_id=project.id,
        title=command["title"],
        goal=command["goal"],
        success_criteria=command["success_criteria"],
        stop_conditions=command["stop_conditions"],
        autonomy_level=command["autonomy_level"],
        ai_model=command["ai_model"],
        owner_user_id=owner.id,
        created_by_user_id=current_user.id,
        status=ResearchTaskStatus.DRAFT.value,
    )
    db_session.add(task)
    await db_session.flush()
    for position, (protocol, version) in enumerate(protocols, start=1):
        db_session.add(
            ResearchTaskProtocol(
                task_id=task.id,
                protocol_id=protocol.id,
                protocol_version_id=version.id,
                protocol_version=version.version,
                position=position,
            )
        )
    pinned_knowledge: list[dict[str, Any]] = []
    for position, item in enumerate(knowledge_items, start=1):
        snapshot = {
            **snapshot_knowledge(item),
            "id": str(item.id),
            "scope_type": item.scope_type,
        }
        pinned_knowledge.append(snapshot)
        db_session.add(
            ResearchTaskKnowledge(
                task_id=task.id,
                knowledge_item_id=item.id,
                knowledge_revision=item.revision,
                position=position,
                snapshot=snapshot,
            )
        )
    run = ResearchRun(
        task_id=task.id,
        run_number=1,
        status=ResearchRunStatus.DRAFT.value,
        aira_state=initial_aira_state(task.goal),
        requested_by_user_id=current_user.id,
    )
    db_session.add(run)
    await db_session.flush()
    rows = await task_protocol_rows(db_session, task.id)
    environment_snapshot = {
        "schema": "airalogy.research-environment.v1",
        "captured_at": utcnow().isoformat(),
        "lab": {"id": str(lab.id), "uid": lab.uid},
        "project": {"id": str(project.id), "uid": project.uid},
        "protocols": [
            {
                "id": str(protocol.id),
                "uid": protocol.uid,
                "name": protocol.name,
                "version": version.version,
                "version_id": str(version.id),
            }
            for _task_protocol, protocol, version in rows
        ],
        "knowledge": pinned_knowledge,
        "ai_available_at_capture": config.effective_ai_enabled,
        "autonomy_level": task.autonomy_level,
    }
    run.environment_snapshot = environment_snapshot
    await create_plan_version(
        db_session,
        task=task,
        run=run,
        kind="initial",
        plan={
            "workflow": workflow_info_for_task(
                task, project, lab, rows, knowledge_context=pinned_knowledge
            ),
            "success_criteria": task.success_criteria,
            "stop_conditions": task.stop_conditions,
        },
        summary="Initial user-confirmed Research Environment and method set",
    )
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        kind="task.created",
        actor_user_id=current_user.id,
        payload={
            "preview_digest": expected_digest,
            "project_id": str(project.id),
            "owner_user_id": str(owner.id),
        },
        idempotency_key=f"task:{task.id}:created",
    )
    await db_session.commit()
    return await _task_detail(db_session, task, project, lab)


@router.get("")
async def list_research_tasks(
    current_user: CurrentUser,
    db_session: DBSession,
    project_id: UUID | None = None,
    status: list[str] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    conditions = [ResearchTask.archived_at.is_(None)]
    if status:
        conditions.append(ResearchTask.status.in_(status))
    if project_id is not None:
        project = await _project(db_session, project_id)
        await require_research_capability(
            db_session,
            user=current_user,
            project=project,
            capability="research.read",
        )
        conditions.append(ResearchTask.project_id == project_id)
    else:
        assigned = (
            select(ResearchAction.id)
            .join(ResearchRun, ResearchRun.id == ResearchAction.run_id)
            .where(
                ResearchRun.task_id == ResearchTask.id,
                ResearchAction.assignee_user_id == current_user.id,
            )
            .exists()
        )
        conditions.append(
            or_(
                ResearchTask.owner_user_id == current_user.id,
                ResearchTask.created_by_user_id == current_user.id,
                assigned,
            )
        )

    candidates = list(
        (
            await db_session.scalars(
                select(ResearchTask)
                .where(*conditions)
                .order_by(ResearchTask.updated_at.desc())
            )
        ).all()
    )
    if project_id is not None:
        visible_tasks = candidates
    else:
        visible_tasks = []
        for task in candidates:
            project = await _project(db_session, task.project_id)
            try:
                await require_research_capability(
                    db_session,
                    user=current_user,
                    project=project,
                    capability="research.read",
                )
            except HTTPException as error:
                if error.status_code == 403:
                    continue
                raise
            visible_tasks.append(task)
    total = len(visible_tasks)
    tasks = visible_tasks[(page - 1) * page_size : page * page_size]
    return {
        "tasks": [await _task_summary(db_session, task) for task in tasks],
        "total_count": total or 0,
    }


@router.get("/{task_id}")
async def get_research_task(
    task_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, project, lab = await _task_context(db_session, current_user, task_id)
    return await _task_detail(db_session, task, project, lab)


@router.post("/{task_id}/start")
async def start_research_task(
    task_id: UUID,
    params: TaskTransitionParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, project, lab = await _task_context(
        db_session, current_user, task_id, "research.run"
    )
    if task.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Research Task has changed")
    if task.status != ResearchTaskStatus.DRAFT.value:
        raise HTTPException(status_code=409, detail="Only a draft Task can be started")
    run = await _latest_run(db_session, task.id)
    if run is None or run.status != ResearchRunStatus.DRAFT.value:
        raise HTTPException(status_code=409, detail="Draft Research Run not found")

    rows = await task_protocol_rows(db_session, task.id)
    now = utcnow()
    run.status = (
        ResearchRunStatus.PLANNING.value
        if config.effective_ai_enabled and rows
        else ResearchRunStatus.RUNNING.value
    )
    run.started_at = now
    run.last_error = None
    task.status = ResearchTaskStatus.ACTIVE.value
    task.revision += 1
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        kind="run.started",
        actor_user_id=current_user.id,
        payload={
            "ai": bool(config.effective_ai_enabled and rows),
            "reason": params.reason,
        },
        idempotency_key=f"run:{run.id}:started",
    )
    if config.effective_ai_enabled and rows:
        await enqueue_research_advance(db_session, task=task, run=run)
    else:
        await emit_research_event(
            db_session,
            task_id=task.id,
            run_id=run.id,
            kind="run.manual_control_required",
            actor_user_id=current_user.id,
            payload={"reason": "ai_unavailable_or_no_protocol"},
            idempotency_key=f"run:{run.id}:manual:start",
        )
    await db_session.commit()
    return await _task_detail(db_session, task, project, lab)


@router.post("/{task_id}/pause")
async def pause_research_task(
    task_id: UUID,
    params: TaskTransitionParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, project, lab = await _task_context(
        db_session, current_user, task_id, "research.run"
    )
    if task.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Research Task has changed")
    run = await _latest_run(db_session, task.id)
    if run is None or run.status in {
        ResearchRunStatus.COMPLETED.value,
        ResearchRunStatus.FAILED.value,
        ResearchRunStatus.CANCELLED.value,
    }:
        raise HTTPException(status_code=409, detail="Research Run cannot be paused")
    run.status = ResearchRunStatus.PAUSED.value
    task.status = ResearchTaskStatus.PAUSED.value
    task.revision += 1
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        kind="run.paused",
        actor_user_id=current_user.id,
        payload={"reason": params.reason},
    )
    await db_session.commit()
    return await _task_detail(db_session, task, project, lab)


@router.post("/{task_id}/resume")
async def resume_research_task(
    task_id: UUID,
    params: TaskTransitionParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, project, lab = await _task_context(
        db_session, current_user, task_id, "research.run"
    )
    if task.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Research Task has changed")
    run = await _latest_run(db_session, task.id)
    if run is None or run.status not in {
        ResearchRunStatus.PAUSED.value,
        ResearchRunStatus.FAILED.value,
    }:
        raise HTTPException(status_code=409, detail="Research Run cannot be resumed")
    open_work_item = (
        await db_session.scalars(
            select(ResearchHumanWorkItem)
            .join(ResearchAction, ResearchAction.id == ResearchHumanWorkItem.action_id)
            .where(
                ResearchAction.run_id == run.id,
                ResearchHumanWorkItem.status.in_(ACTIVE_WORK_ITEM_STATUSES),
            )
            .limit(1)
        )
    ).first()
    task.status = ResearchTaskStatus.ACTIVE.value
    task.outcome = None
    task.revision += 1
    run.last_error = None
    run.completed_at = None
    if open_work_item is not None:
        run.status = ResearchRunStatus.WAITING_FOR_HUMAN.value
    else:
        run.status = ResearchRunStatus.RUNNING.value
        if config.effective_ai_enabled and await task_protocol_rows(
            db_session, task.id
        ):
            await enqueue_research_advance(db_session, task=task, run=run)
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        kind="run.resumed",
        actor_user_id=current_user.id,
        payload={"reason": params.reason},
    )
    await db_session.commit()
    return await _task_detail(db_session, task, project, lab)


@router.post("/{task_id}/cancel")
async def cancel_research_task(
    task_id: UUID,
    params: TaskTransitionParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, project, lab = await _task_context(
        db_session, current_user, task_id, "research.run"
    )
    if task.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Research Task has changed")
    if task.status in {
        ResearchTaskStatus.COMPLETED.value,
        ResearchTaskStatus.CANCELLED.value,
        ResearchTaskStatus.ARCHIVED.value,
    }:
        raise HTTPException(status_code=409, detail="Research Task cannot be cancelled")
    run = await _latest_run(db_session, task.id)
    now = utcnow()
    if run is not None:
        run.status = ResearchRunStatus.CANCELLED.value
        run.cancel_reason = params.reason
        run.completed_at = now
        actions = list(
            (
                await db_session.scalars(
                    select(ResearchAction).where(
                        ResearchAction.run_id == run.id,
                        ResearchAction.status.not_in(
                            [
                                ResearchActionStatus.COMPLETED.value,
                                ResearchActionStatus.CANCELLED.value,
                                ResearchActionStatus.SKIPPED.value,
                            ]
                        ),
                    )
                )
            ).all()
        )
        for action in actions:
            action.status = ResearchActionStatus.CANCELLED.value
            action.completed_at = now
        if actions:
            work_items = list(
                (
                    await db_session.scalars(
                        select(ResearchHumanWorkItem).where(
                            ResearchHumanWorkItem.action_id.in_(
                                [action.id for action in actions]
                            ),
                            ResearchHumanWorkItem.status.in_(ACTIVE_WORK_ITEM_STATUSES),
                        )
                    )
                ).all()
            )
            for item in work_items:
                item.status = HumanWorkItemStatus.CANCELLED.value
                item.revision += 1
            approvals = list(
                (
                    await db_session.scalars(
                        select(ResearchApproval).where(
                            ResearchApproval.action_id.in_(
                                [action.id for action in actions]
                            ),
                            ResearchApproval.status
                            == ResearchApprovalStatus.PENDING.value,
                        )
                    )
                ).all()
            )
            for approval in approvals:
                approval.status = ResearchApprovalStatus.REVOKED.value
                approval.decision_reason = params.reason or "Task cancelled"
                approval.decided_by_user_id = current_user.id
                approval.decided_at = now
                approval.revision += 1
    task.status = ResearchTaskStatus.CANCELLED.value
    task.outcome = ResearchTaskOutcome.CANCELLED.value
    task.completed_at = now
    task.revision += 1
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id if run else None,
        kind="task.cancelled",
        actor_user_id=current_user.id,
        payload={"reason": params.reason},
    )
    await db_session.commit()
    return await _task_detail(db_session, task, project, lab)


@router.post("/{task_id}/complete")
async def complete_research_task(
    task_id: UUID,
    params: TaskCompleteParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, project, lab = await _task_context(
        db_session, current_user, task_id, "research.run"
    )
    if task.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Research Task has changed")
    if current_user.id != task.owner_user_id:
        await require_research_capability(
            db_session,
            user=current_user,
            project=project,
            capability="research.approve",
        )
    active_items = await db_session.scalar(
        select(func.count())
        .select_from(ResearchHumanWorkItem)
        .join(ResearchAction, ResearchAction.id == ResearchHumanWorkItem.action_id)
        .join(ResearchRun, ResearchRun.id == ResearchAction.run_id)
        .where(
            ResearchRun.task_id == task.id,
            ResearchHumanWorkItem.status.in_(ACTIVE_WORK_ITEM_STATUSES),
        )
    )
    if active_items:
        raise HTTPException(
            status_code=409,
            detail="Complete or cancel open Human Work Items first",
        )
    pending_approvals = await db_session.scalar(
        select(func.count())
        .select_from(ResearchApproval)
        .join(ResearchAction, ResearchAction.id == ResearchApproval.action_id)
        .join(ResearchRun, ResearchRun.id == ResearchAction.run_id)
        .where(
            ResearchRun.task_id == task.id,
            ResearchApproval.status == ResearchApprovalStatus.PENDING.value,
        )
    )
    if pending_approvals:
        raise HTTPException(
            status_code=409,
            detail="Approve, reject, or cancel pending Research Actions first",
        )
    run = await _latest_run(db_session, task.id)
    now = utcnow()
    if run is not None:
        run.status = ResearchRunStatus.COMPLETED.value
        run.completed_at = run.completed_at or now
    task.status = ResearchTaskStatus.COMPLETED.value
    task.outcome = params.outcome.value
    task.scientific_outcome = params.scientific_outcome.value
    task.conclusion = params.conclusion.strip()
    task.completed_at = now
    task.result_package = {
        **(task.result_package or {}),
        "goal_assessment": params.outcome.value,
        "scientific_outcome": params.scientific_outcome.value,
        "reviewed_conclusion": task.conclusion,
        "reviewed_by_user_id": str(current_user.id),
        "reviewed_at": now.isoformat(),
    }
    if run is not None:
        run.result_package = task.result_package
    task.revision += 1
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id if run else None,
        kind="task.completed",
        actor_user_id=current_user.id,
        payload={
            "outcome": task.outcome,
            "scientific_outcome": task.scientific_outcome,
            "reason": params.reason,
        },
    )
    await db_session.commit()
    return await _task_detail(db_session, task, project, lab)


async def _manual_action_context(
    db_session: DBSession,
    current_user: User,
    task_id: UUID,
    params: ManualProtocolActionDraft,
) -> tuple[
    ResearchTask,
    Project,
    Lab,
    ResearchRun,
    Protocol,
    ProtocolVersion,
    User,
    int,
    dict[str, Any],
]:
    task, project, lab = await _task_context(
        db_session, current_user, task_id, "research.run"
    )
    if task.status not in {
        ResearchTaskStatus.ACTIVE.value,
        ResearchTaskStatus.PAUSED.value,
    }:
        raise HTTPException(status_code=409, detail="Start the Research Task first")
    run = await _latest_run(db_session, task.id)
    if run is None or run.status in {
        ResearchRunStatus.COMPLETED.value,
        ResearchRunStatus.CANCELLED.value,
    }:
        raise HTTPException(status_code=409, detail="Active Research Run not found")
    protocol = await Protocol.find_by(
        db_session,
        [
            Protocol.id == params.protocol_id,
            Protocol.project_id == project.id,
            Protocol.kind == ProtocolKind.EXPERIMENT,
            Protocol.deleted_at.is_(None),
        ],
    )
    if protocol is None:
        raise HTTPException(
            status_code=404, detail="Protocol not found in this Project"
        )
    task_protocol = await ResearchTaskProtocol.find_by(
        db_session,
        [
            ResearchTaskProtocol.task_id == task.id,
            ResearchTaskProtocol.protocol_id == protocol.id,
        ],
    )
    version = (
        await db_session.get(ProtocolVersion, task_protocol.protocol_version_id)
        if task_protocol is not None
        else await ProtocolVersion.find_by(
            db_session,
            [
                ProtocolVersion.protocol_id == protocol.id,
                ProtocolVersion.version == protocol.latest_version,
            ],
        )
    )
    if version is None:
        raise HTTPException(status_code=409, detail="Protocol version not found")
    assignee = await db_session.get(User, params.assignee_user_id or task.owner_user_id)
    if assignee is None:
        raise HTTPException(status_code=404, detail="Assignee not found")
    await require_research_capability(
        db_session,
        user=assignee,
        project=project,
        capability="research.run",
    )
    if assignee.id != current_user.id:
        await require_research_capability(
            db_session,
            user=current_user,
            project=project,
            capability="research.assign",
        )
    position = (
        task_protocol.position
        if task_protocol
        else (
            (
                await db_session.scalar(
                    select(func.max(ResearchTaskProtocol.position)).where(
                        ResearchTaskProtocol.task_id == task.id
                    )
                )
                or 0
            )
            + 1
        )
    )
    command = {
        "task_id": str(task.id),
        "task_revision": task.revision,
        "run_id": str(run.id),
        "run_plan_version": run.plan_version,
        "protocol_id": str(protocol.id),
        "protocol_version": version.version,
        "protocol_position": position,
        "assignee_user_id": str(assignee.id),
        "title": (params.title or protocol.name).strip(),
        "instructions": params.instructions.strip(),
        "initial_values": params.initial_values,
        "due_at": params.due_at.isoformat() if params.due_at else None,
        "idempotency_key": params.idempotency_key,
    }
    return task, project, lab, run, protocol, version, assignee, position, command


@router.post("/{task_id}/actions/preview")
async def preview_manual_protocol_action(
    task_id: UUID,
    params: ManualProtocolActionDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    (
        task,
        project,
        lab,
        run,
        protocol,
        version,
        assignee,
        position,
        command,
    ) = await _manual_action_context(db_session, current_user, task_id, params)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": {
            "lab": {"id": str(lab.id), "uid": lab.uid, "name": lab.name},
            "project": {
                "id": str(project.id),
                "uid": project.uid,
                "name": project.name,
            },
            "task": {"id": str(task.id), "title": task.title},
            "run": {"id": str(run.id), "number": run.run_number},
        },
        "protocol": {
            "id": str(protocol.id),
            "uid": protocol.uid,
            "name": protocol.name,
            "version": version.version,
            "position": position,
        },
        "assignee": _user_data(assignee),
        "effects": [
            "Create a pinned Protocol Run",
            "Create and assign a Human Work Item",
            "Wait for a validated Record before continuing the Research Run",
        ],
    }


@router.post("/{task_id}/actions")
async def create_manual_protocol_action(
    task_id: UUID,
    params: ManualProtocolActionCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    (
        task,
        project,
        lab,
        run,
        protocol,
        version,
        assignee,
        position,
        command,
    ) = await _manual_action_context(db_session, current_user, task_id, params)
    digest = canonical_digest(command)
    if params.preview_digest != digest:
        raise HTTPException(
            status_code=409,
            detail="The Action preview is stale; preview it again before creating.",
        )
    existing = await ResearchAction.find_by(
        db_session,
        [
            ResearchAction.run_id == run.id,
            ResearchAction.idempotency_key == params.idempotency_key,
        ],
    )
    if existing is not None:
        if existing.preview_digest != digest:
            raise HTTPException(
                status_code=409,
                detail="This idempotency key was already used for another Action",
            )
        return await _action_data(db_session, existing, project=project, lab=lab)

    task_protocol = await ResearchTaskProtocol.find_by(
        db_session,
        [
            ResearchTaskProtocol.task_id == task.id,
            ResearchTaskProtocol.protocol_id == protocol.id,
        ],
    )
    if task_protocol is None:
        db_session.add(
            ResearchTaskProtocol(
                task_id=task.id,
                protocol_id=protocol.id,
                protocol_version_id=version.id,
                protocol_version=version.version,
                position=position,
            )
        )
        await db_session.flush()
        snapshot = dict(run.environment_snapshot or {})
        snapshot["protocols"] = [
            *(snapshot.get("protocols") or []),
            {
                "id": str(protocol.id),
                "uid": protocol.uid,
                "name": protocol.name,
                "version": version.version,
                "version_id": str(version.id),
            },
        ]
        run.environment_snapshot = snapshot

    await create_plan_version(
        db_session,
        task=task,
        run=run,
        kind="manual",
        plan={
            "action": command,
            "previous_plan_version": command["run_plan_version"],
        },
        summary=f"Manually schedule {protocol.name}",
    )
    sequence = (
        await db_session.scalar(
            select(func.max(ResearchAction.sequence)).where(
                ResearchAction.run_id == run.id
            )
        )
        or 0
    ) + 1
    action = ResearchAction(
        run_id=run.id,
        sequence=sequence,
        plan_version=run.plan_version,
        kind=ResearchActionKind.PROTOCOL_RUN.value,
        status=ResearchActionStatus.WAITING.value,
        title=command["title"],
        description=command["instructions"],
        executor_type="human",
        assignee_user_id=assignee.id,
        input_data={
            "protocol_id": str(protocol.id),
            "protocol_version": version.version,
            "protocol_position": position,
            "initial_values": params.initial_values,
            "source": "manual",
        },
        requirements={"record_required": True},
        policy_decision="allow",
        preview_digest=digest,
        idempotency_key=params.idempotency_key,
        due_at=params.due_at,
    )
    db_session.add(action)
    await db_session.flush()
    protocol_run = ResearchProtocolRun(
        action_id=action.id,
        protocol_id=protocol.id,
        protocol_version_id=version.id,
        protocol_version=version.version,
        initial_values=params.initial_values,
    )
    work_item = ResearchHumanWorkItem(
        action_id=action.id,
        assignee_user_id=assignee.id,
        instructions=params.instructions.strip()
        or f"Execute {protocol.name} and submit its Record.",
        submission_contract={
            "type": "protocol_record",
            "protocol_id": str(protocol.id),
            "protocol_version": version.version,
        },
        due_at=params.due_at,
    )
    db_session.add_all([protocol_run, work_item])
    db_session.add(
        ResearchArtifactLink(
            task_id=task.id,
            run_id=run.id,
            action_id=action.id,
            artifact_type="protocol",
            artifact_id=str(protocol.id),
            artifact_version=version.version,
            relation="method",
            link_metadata={"position": position},
        )
    )
    state = dict(run.aira_state or initial_aira_state(task.goal))
    steps = list(state.get("steps") or [])
    protocol_airalogy_id = (
        f"airalogy.id.lab.{lab.uid}.project.{project.uid}.protocol."
        f"{protocol.uid}.v.{version.version}"
    )
    steps.extend(
        [
            {
                "step": "add_next_protocol",
                "path_index": len(steps),
                "mode": "user",
                "data": {
                    "protocol_index": position,
                    "airalogy_protocol_id": protocol_airalogy_id,
                    "end_path": False,
                    "thought": params.instructions.strip(),
                },
            },
            {
                "step": "add_initial_values_for_fields_in_next_protocol",
                "path_index": len(steps) + 1,
                "mode": "user",
                "data": {
                    "protocol_index": position,
                    "airalogy_protocol_id": protocol_airalogy_id,
                    "values": params.initial_values,
                },
            },
        ]
    )
    run.aira_state = {**state, "path_status": "waiting_for_record", "steps": steps}
    run.status = ResearchRunStatus.WAITING_FOR_HUMAN.value
    task.status = ResearchTaskStatus.ACTIVE.value
    task.revision += 1
    await db_session.flush()
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        work_item_id=work_item.id,
        kind="work_item.assigned",
        actor_user_id=current_user.id,
        payload={
            "assignee_user_id": str(assignee.id),
            "protocol_id": str(protocol.id),
            "protocol_version": version.version,
            "preview_digest": digest,
        },
        idempotency_key=f"action:{action.id}:assigned:1",
    )
    await db_session.commit()
    return await _action_data(db_session, action, project=project, lab=lab)


async def _work_item_context(
    db_session: DBSession,
    current_user: User,
    work_item_id: UUID,
) -> tuple[
    ResearchHumanWorkItem,
    ResearchAction,
    ResearchRun,
    ResearchTask,
    Project,
    Lab,
]:
    item = await db_session.get(ResearchHumanWorkItem, work_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Human Work Item not found")
    action = await db_session.get(ResearchAction, item.action_id)
    run = await db_session.get(ResearchRun, action.run_id) if action else None
    task = await db_session.get(ResearchTask, run.task_id) if run else None
    if action is None or run is None or task is None:
        raise HTTPException(status_code=404, detail="Research Task context not found")
    project = await _project(db_session, task.project_id)
    await require_research_capability(
        db_session,
        user=current_user,
        project=project,
        capability="research.read",
    )
    lab = await db_session.get(Lab, task.lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    return item, action, run, task, project, lab


async def _can_manage_work_item(
    db_session: DBSession,
    *,
    current_user: User,
    item: ResearchHumanWorkItem,
    task: ResearchTask,
    project: Project,
) -> bool:
    if current_user.id in {item.assignee_user_id, task.owner_user_id}:
        return True
    decision = await resolve_structured_access(
        db_session,
        current_user.id,
        project.lab_id,
        project,
        include_legacy=True,
    )
    return decision.allows("research.assign")


async def _work_item_data(
    db_session: DBSession,
    item: ResearchHumanWorkItem,
    action: ResearchAction,
    run: ResearchRun,
    task: ResearchTask,
    project: Project,
    lab: Lab,
) -> dict[str, Any]:
    action_data = await _action_data(db_session, action, project=project, lab=lab)
    return {
        **item.as_dict(),
        "assignee": action_data["assignee"],
        "action": action_data,
        "run": run.as_dict(),
        "task": {
            "id": str(task.id),
            "title": task.title,
            "goal": task.goal,
            "status": task.status,
            "revision": task.revision,
        },
        "project": {
            "id": str(project.id),
            "uid": project.uid,
            "name": project.name,
        },
        "lab": {"id": str(lab.id), "uid": lab.uid, "name": lab.name},
    }


@work_items_router.get("")
async def list_research_work_items(
    current_user: CurrentUser,
    db_session: DBSession,
    status: list[str] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    conditions = [ResearchHumanWorkItem.assignee_user_id == current_user.id]
    if status:
        conditions.append(ResearchHumanWorkItem.status.in_(status))
    else:
        conditions.append(ResearchHumanWorkItem.status.in_(ACTIVE_WORK_ITEM_STATUSES))
    items = list(
        (
            await db_session.scalars(
                select(ResearchHumanWorkItem)
                .where(*conditions)
                .order_by(
                    ResearchHumanWorkItem.due_at.asc().nulls_last(),
                    ResearchHumanWorkItem.created_at.desc(),
                )
            )
        ).all()
    )
    result = []
    for item in items:
        try:
            context = await _work_item_context(db_session, current_user, item.id)
        except HTTPException as error:
            if error.status_code == 403:
                continue
            raise
        result.append(await _work_item_data(db_session, *context))
    total = len(result)
    return {
        "work_items": result[(page - 1) * page_size : page * page_size],
        "total_count": total,
    }


@work_items_router.get("/{work_item_id}")
async def get_research_work_item(
    work_item_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    context = await _work_item_context(db_session, current_user, work_item_id)
    return await _work_item_data(db_session, *context)


@work_items_router.post("/{work_item_id}/start")
async def start_research_work_item(
    work_item_id: UUID,
    params: WorkItemRevisionParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    item, action, run, task, project, lab = await _work_item_context(
        db_session, current_user, work_item_id
    )
    if item.assignee_user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Only the assignee can start this work"
        )
    if item.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Human Work Item has changed")
    if item.status not in {
        HumanWorkItemStatus.OPEN.value,
        HumanWorkItemStatus.CHANGES_REQUESTED.value,
    }:
        raise HTTPException(status_code=409, detail="Human Work Item cannot be started")
    item.status = HumanWorkItemStatus.IN_PROGRESS.value
    item.started_at = item.started_at or utcnow()
    item.revision += 1
    action.status = ResearchActionStatus.RUNNING.value
    action.started_at = action.started_at or utcnow()
    action.revision += 1
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        work_item_id=item.id,
        kind="work_item.started",
        actor_user_id=current_user.id,
    )
    await db_session.commit()
    return await _work_item_data(db_session, item, action, run, task, project, lab)


@work_items_router.post("/{work_item_id}/assign")
async def assign_research_work_item(
    work_item_id: UUID,
    params: WorkItemAssignParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    item, action, run, task, project, lab = await _work_item_context(
        db_session, current_user, work_item_id
    )
    await require_research_capability(
        db_session,
        user=current_user,
        project=project,
        capability="research.assign",
    )
    if item.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Human Work Item has changed")
    if item.status not in ACTIVE_WORK_ITEM_STATUSES:
        raise HTTPException(
            status_code=409, detail="Human Work Item cannot be assigned"
        )
    assignee = await db_session.get(User, params.assignee_user_id)
    if assignee is None:
        raise HTTPException(status_code=404, detail="Assignee not found")
    await require_research_capability(
        db_session,
        user=assignee,
        project=project,
        capability="research.run",
    )
    previous = item.assignee_user_id
    item.assignee_user_id = assignee.id
    item.status = HumanWorkItemStatus.OPEN.value
    item.started_at = None
    item.revision += 1
    action.assignee_user_id = assignee.id
    action.status = ResearchActionStatus.WAITING.value
    action.revision += 1
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        work_item_id=item.id,
        kind="work_item.assigned",
        actor_user_id=current_user.id,
        payload={
            "previous_assignee_user_id": str(previous),
            "assignee_user_id": str(assignee.id),
            "reason": params.reason,
        },
        idempotency_key=f"work-item:{item.id}:assigned:{item.revision}",
    )
    await db_session.commit()
    return await _work_item_data(db_session, item, action, run, task, project, lab)


def _record_payload(
    *,
    record: Record,
    protocol: Protocol,
    protocol_version: ResearchProtocolRun,
    project: Project,
    lab: Lab,
    user: User,
) -> dict[str, Any]:
    airalogy_protocol_id = (
        f"airalogy.id.lab.{lab.uid}.project.{project.uid}.protocol."
        f"{protocol.uid}.v.{protocol_version.protocol_version}"
    )
    return {
        "airalogy_record_id": record.airalogy_id,
        "record_id": str(record.id),
        "record_version": record.version,
        "metadata": {
            "airalogy_protocol_id": airalogy_protocol_id,
            "protocol_id": protocol.uid,
            "protocol_uuid": str(protocol.id),
            "protocol_version": record.protocol_version,
            "record_current_version_submission_time": record.created_at,
            "record_current_version_submission_user_id": user.username,
            "lab_id": lab.uid,
            "project_id": project.uid,
            "record_num": record.number,
            "sha1": record.hash,
        },
        "data": record.data,
        "report": record.report,
    }


@work_items_router.post("/{work_item_id}/submit")
async def submit_research_work_item(
    work_item_id: UUID,
    params: WorkItemSubmitParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    item, action, run, task, project, lab = await _work_item_context(
        db_session, current_user, work_item_id
    )
    if item.assignee_user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Only the assignee can submit this work"
        )
    if item.status == HumanWorkItemStatus.ACCEPTED.value:
        if item.record_id == params.record_id and (
            params.record_version is None
            or item.record_version == params.record_version
        ):
            return await _work_item_data(
                db_session, item, action, run, task, project, lab
            )
        raise HTTPException(
            status_code=409, detail="Human Work Item is already complete"
        )
    if item.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Human Work Item has changed")
    if item.status not in ACTIVE_WORK_ITEM_STATUSES:
        raise HTTPException(
            status_code=409, detail="Human Work Item cannot be submitted"
        )
    protocol_run = await ResearchProtocolRun.find_by(
        db_session, [ResearchProtocolRun.action_id == action.id]
    )
    if protocol_run is None:
        raise HTTPException(status_code=409, detail="Protocol Run not found")
    conditions = [
        Record.id == params.record_id,
        Record.protocol_id == protocol_run.protocol_id,
        Record.deleted_at.is_(None),
    ]
    if params.record_version is not None:
        conditions.append(Record.version == params.record_version)
    record = (
        await db_session.scalars(
            select(Record).where(*conditions).order_by(Record.version.desc()).limit(1)
        )
    ).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Matching Record not found")
    if record.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Submit a Record created by the assigned user",
        )
    if record.protocol_version != protocol_run.protocol_version:
        raise HTTPException(
            status_code=409,
            detail="Record Protocol version does not match the pinned Protocol Run",
        )
    protocol = await db_session.get(Protocol, protocol_run.protocol_id)
    record_user = await db_session.get(User, record.user_id)
    if protocol is None or record_user is None:
        raise HTTPException(status_code=409, detail="Record context not found")
    payload = _record_payload(
        record=record,
        protocol=protocol,
        protocol_version=protocol_run,
        project=project,
        lab=lab,
        user=record_user,
    )
    now = utcnow()
    item.status = HumanWorkItemStatus.ACCEPTED.value
    item.submission = {"note": params.note, "record": payload}
    item.record_id = record.id
    item.record_version = record.version
    item.submitted_at = now
    item.accepted_at = now
    item.validation_issues = []
    item.revision += 1
    action.status = ResearchActionStatus.COMPLETED.value
    action.output_data = {"record": payload}
    action.completed_at = now
    action.error = None
    action.revision += 1
    protocol_run.record_id = record.id
    protocol_run.record_version = record.version
    protocol_run.validation_status = "completed"
    protocol_run.validation_report = {
        "record_exists": True,
        "protocol_matches": True,
        "protocol_version_matches": True,
        "submitted_by_assignee": True,
        "validated_at": now.isoformat(),
    }
    existing_artifact = await ResearchArtifactLink.find_by(
        db_session,
        [
            ResearchArtifactLink.action_id == action.id,
            ResearchArtifactLink.artifact_type == "record",
            ResearchArtifactLink.artifact_id == str(record.id),
            ResearchArtifactLink.artifact_version == str(record.version),
            ResearchArtifactLink.relation == "evidence",
        ],
    )
    if existing_artifact is None:
        db_session.add(
            ResearchArtifactLink(
                task_id=task.id,
                run_id=run.id,
                action_id=action.id,
                artifact_type="record",
                artifact_id=str(record.id),
                artifact_version=str(record.version),
                relation="evidence",
                link_metadata={
                    "protocol_id": str(protocol.id),
                    "protocol_version": record.protocol_version,
                },
            )
        )
    state = dict(run.aira_state or initial_aira_state(task.goal))
    steps = list(state.get("steps") or [])
    protocol_position = int(action.input_data.get("protocol_position") or 0)
    if not protocol_position:
        task_protocol = await ResearchTaskProtocol.find_by(
            db_session,
            [
                ResearchTaskProtocol.task_id == task.id,
                ResearchTaskProtocol.protocol_id == protocol.id,
            ],
        )
        protocol_position = task_protocol.position if task_protocol else 1
    steps.append(
        {
            "step": "add_record",
            "path_index": len(steps),
            "mode": "user",
            "data": {
                "protocol_index": protocol_position,
                "airalogy_protocol_id": payload["metadata"]["airalogy_protocol_id"],
                "airalogy_record_id": record.airalogy_id,
                "record_data": payload,
            },
        }
    )
    run.aira_state = {
        **state,
        "path_status": "waiting_for_phased_research_conclusion",
        "steps": steps,
    }
    run.status = ResearchRunStatus.RUNNING.value
    run.last_error = None
    task.status = ResearchTaskStatus.ACTIVE.value
    task.revision += 1
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        work_item_id=item.id,
        kind="work_item.completed",
        actor_user_id=current_user.id,
        payload={
            "record_id": str(record.id),
            "record_version": record.version,
        },
        idempotency_key=(f"work-item:{item.id}:record:{record.id}:v{record.version}"),
    )
    if config.effective_ai_enabled:
        await enqueue_research_advance(db_session, task=task, run=run)
    else:
        await emit_research_event(
            db_session,
            task_id=task.id,
            run_id=run.id,
            kind="run.manual_control_required",
            actor_user_id=current_user.id,
            payload={"reason": "ai_disabled_after_record"},
            idempotency_key=f"run:{run.id}:manual:record:{record.id}:v{record.version}",
        )
    await db_session.commit()
    return await _work_item_data(db_session, item, action, run, task, project, lab)


async def _approval_context(
    db_session: DBSession,
    current_user: User,
    approval_id: UUID,
    *,
    lock: bool = False,
) -> tuple[
    ResearchApproval,
    ResearchAction,
    ResearchRun,
    ResearchTask,
    Project,
    Lab,
]:
    statement = select(ResearchApproval).where(ResearchApproval.id == approval_id)
    if lock:
        statement = statement.with_for_update()
    approval = (await db_session.scalars(statement)).first()
    if approval is None:
        raise HTTPException(status_code=404, detail="Research Approval not found")
    action = await db_session.get(ResearchAction, approval.action_id)
    run = await db_session.get(ResearchRun, action.run_id) if action else None
    task = await db_session.get(ResearchTask, run.task_id) if run else None
    if action is None or run is None or task is None:
        raise HTTPException(status_code=404, detail="Research Task context not found")
    project = await _project(db_session, task.project_id)
    await require_research_capability(
        db_session,
        user=current_user,
        project=project,
        capability="research.read",
    )
    lab = await db_session.get(Lab, task.lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    return approval, action, run, task, project, lab


async def _approval_data(
    db_session: DBSession,
    approval: ResearchApproval,
    action: ResearchAction,
    run: ResearchRun,
    task: ResearchTask,
    project: Project,
    lab: Lab,
) -> dict[str, Any]:
    return {
        **(await _approval_summary(db_session, approval)),
        "action": await _action_data(db_session, action, project=project, lab=lab),
        "run": run.as_dict(),
        "task": {
            "id": str(task.id),
            "title": task.title,
            "goal": task.goal,
            "status": task.status,
            "revision": task.revision,
        },
        "project": {
            "id": str(project.id),
            "uid": project.uid,
            "name": project.name,
        },
        "lab": {"id": str(lab.id), "uid": lab.uid, "name": lab.name},
    }


async def _require_approval_authority(
    db_session: DBSession,
    *,
    current_user: User,
    approval: ResearchApproval,
    project: Project,
) -> None:
    if current_user.id == approval.approver_user_id:
        return
    await require_research_capability(
        db_session,
        user=current_user,
        project=project,
        capability="research.approve",
    )


def _validate_pending_approval(
    approval: ResearchApproval,
    action: ResearchAction,
    params: ApprovalDecisionParams,
) -> None:
    if approval.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Research Approval has changed")
    if action.revision != params.expected_action_revision:
        raise HTTPException(status_code=409, detail="Research Action has changed")
    if approval.preview_digest != params.preview_digest:
        raise HTTPException(
            status_code=409, detail="Research Approval preview is stale"
        )
    if action.preview_digest != params.preview_digest:
        raise HTTPException(status_code=409, detail="Research Action preview is stale")
    if approval.status != ResearchApprovalStatus.PENDING.value:
        raise HTTPException(status_code=409, detail="Research Approval is not pending")
    if action.status != ResearchActionStatus.PROPOSED.value:
        raise HTTPException(status_code=409, detail="Research Action is not proposed")


@approvals_router.get("")
async def list_research_approvals(
    current_user: CurrentUser,
    db_session: DBSession,
    status: list[str] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    conditions = [ResearchApproval.approver_user_id == current_user.id]
    if status:
        conditions.append(ResearchApproval.status.in_(status))
    else:
        conditions.append(
            ResearchApproval.status == ResearchApprovalStatus.PENDING.value
        )
    approvals = list(
        (
            await db_session.scalars(
                select(ResearchApproval)
                .where(*conditions)
                .order_by(ResearchApproval.requested_at.asc())
            )
        ).all()
    )
    result = []
    for approval in approvals:
        try:
            context = await _approval_context(db_session, current_user, approval.id)
        except HTTPException as error:
            if error.status_code == 403:
                continue
            raise
        result.append(await _approval_data(db_session, *context))
    total = len(result)
    return {
        "approvals": result[(page - 1) * page_size : page * page_size],
        "total_count": total,
    }


@approvals_router.get("/{approval_id}")
async def get_research_approval(
    approval_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    context = await _approval_context(db_session, current_user, approval_id)
    return await _approval_data(db_session, *context)


@approvals_router.post("/{approval_id}/approve")
async def approve_research_action(
    approval_id: UUID,
    params: ApprovalDecisionParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    approval, action, run, task, project, lab = await _approval_context(
        db_session, current_user, approval_id, lock=True
    )
    await _require_approval_authority(
        db_session,
        current_user=current_user,
        approval=approval,
        project=project,
    )
    _validate_pending_approval(approval, action, params)
    if (
        task.status != ResearchTaskStatus.ACTIVE.value
        or run.status != ResearchRunStatus.WAITING_FOR_APPROVAL.value
    ):
        raise HTTPException(
            status_code=409,
            detail="Resume the active Research Run before approving this Action",
        )
    protocol_run = await ResearchProtocolRun.find_by(
        db_session, [ResearchProtocolRun.action_id == action.id]
    )
    if protocol_run is None:
        raise HTTPException(status_code=409, detail="Protocol Run not found")
    protocol = await db_session.get(Protocol, protocol_run.protocol_id)
    version = await db_session.get(ProtocolVersion, protocol_run.protocol_version_id)
    if protocol is None or version is None:
        raise HTTPException(status_code=409, detail="Protocol context not found")

    now = utcnow()
    approval.status = ResearchApprovalStatus.APPROVED.value
    approval.decision_reason = params.reason.strip()
    approval.decided_by_user_id = current_user.id
    approval.decided_at = now
    approval.revision += 1
    action.policy_decision = "allow"
    await activate_protocol_action(
        db_session,
        task=task,
        run=run,
        action=action,
        protocol=protocol,
        version=version,
        instructions=action.description,
        actor_user_id=current_user.id,
    )
    task.revision += 1
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="approval.approved",
        actor_user_id=current_user.id,
        payload={
            "approval_id": str(approval.id),
            "preview_digest": approval.preview_digest,
            "reason": approval.decision_reason,
        },
        idempotency_key=f"approval:{approval.id}:approved",
    )
    await db_session.commit()
    return await _approval_data(db_session, approval, action, run, task, project, lab)


@approvals_router.post("/{approval_id}/reject")
async def reject_research_action(
    approval_id: UUID,
    params: ApprovalRejectParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    approval, action, run, task, project, lab = await _approval_context(
        db_session, current_user, approval_id, lock=True
    )
    await _require_approval_authority(
        db_session,
        current_user=current_user,
        approval=approval,
        project=project,
    )
    _validate_pending_approval(approval, action, params)
    if (
        task.status != ResearchTaskStatus.ACTIVE.value
        or run.status != ResearchRunStatus.WAITING_FOR_APPROVAL.value
    ):
        raise HTTPException(
            status_code=409,
            detail="Resume the active Research Run before rejecting this Action",
        )
    now = utcnow()
    approval.status = ResearchApprovalStatus.REJECTED.value
    approval.decision_reason = params.reason.strip()
    approval.decided_by_user_id = current_user.id
    approval.decided_at = now
    approval.revision += 1
    action.status = ResearchActionStatus.CANCELLED.value
    action.error = f"Rejected: {approval.decision_reason}"
    action.completed_at = now
    action.revision += 1

    state = dict(run.aira_state or initial_aira_state(task.goal))
    run.aira_state = {
        **state,
        "path_status": "waiting_for_next_protocol",
        "rejected_actions": [
            *(state.get("rejected_actions") or []),
            {
                "action_id": str(action.id),
                "reason": approval.decision_reason,
                "rejected_at": now.isoformat(),
            },
        ],
    }
    run.status = ResearchRunStatus.RUNNING.value
    run.last_error = None
    task.status = ResearchTaskStatus.ACTIVE.value
    task.revision += 1
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="approval.rejected",
        actor_user_id=current_user.id,
        payload={
            "approval_id": str(approval.id),
            "preview_digest": approval.preview_digest,
            "reason": approval.decision_reason,
        },
        idempotency_key=f"approval:{approval.id}:rejected",
    )
    if config.effective_ai_enabled and await task_protocol_rows(db_session, task.id):
        await enqueue_research_advance(db_session, task=task, run=run)
    else:
        await emit_research_event(
            db_session,
            task_id=task.id,
            run_id=run.id,
            kind="run.manual_control_required",
            actor_user_id=current_user.id,
            payload={"reason": "approval_rejected_without_ai"},
            idempotency_key=f"run:{run.id}:manual:approval:{approval.id}",
        )
    await db_session.commit()
    return await _approval_data(db_session, approval, action, run, task, project, lab)
