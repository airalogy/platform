"""Research Task workbench and human-in-the-loop execution APIs."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

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
    ResearchReviewRecommendation,
    ResearchRun,
    ResearchRunStatus,
    ResearchTask,
    ResearchTaskKnowledge,
    ResearchTaskOutcome,
    ResearchTaskProtocol,
    ResearchTaskResourceRequirement,
    ResearchTaskStatus,
    ScientificOutcome,
)
from app.models.research_asset import (
    ClaimState,
    EvidenceKind,
    EvidenceQuality,
    ResearchClaim,
    ResearchEvidence,
)
from app.models.research_execution import (
    ResearchInstrumentJob,
    ResearchInstrumentJobStatus,
    ResearchResourceReservation,
    ResearchResourceReservationStatus,
    ResearchToolJob,
    ResearchToolJobStatus,
    ResearchWaitEvent,
    ResearchWaitEventStatus,
)
from app.models.resource import ResourceType, ResourceTypeRevision
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.access_control import (
    resolve_resource_access,
    resolve_structured_access,
)
from app.services.knowledge import authorize_knowledge_item, snapshot_knowledge
from app.services.model_usage import create_usage_context
from app.services.research_assets import research_asset_bundle
from app.services.research_budget import normalize_currency, reached_operational_limit
from app.services.research_capabilities import (
    protocol_capability,
    resource_capability,
    tool_capability,
)
from app.services.research_executor_bindings import (
    enforce_environment_binding_scope,
    resolve_executor_binding,
)
from app.services.research_resources import (
    ResearchResourceError,
    activate_aira_resource_action,
    release_research_run_reservations,
)
from app.services.research_review import generate_research_review
from app.services.research_runtime import (
    ACTIVE_WORK_ITEM_STATUSES,
    TERMINAL_RUN_STATUSES,
    activate_protocol_action,
    activate_tool_action,
    activate_wait_event_action,
    canonical_digest,
    create_plan_version,
    emit_research_event,
    enqueue_research_advance,
    has_research_capability,
    initial_aira_state,
    require_research_capability,
    research_environment_has_ai_path,
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
    tool_keys: list[str] = Field(default_factory=list, max_length=50)
    knowledge_ids: list[UUID] = Field(default_factory=list, max_length=50)
    resource_type_ids: list[UUID] = Field(default_factory=list, max_length=100)
    owner_user_id: UUID | None = None
    ai_model: str | None = Field(default=None, max_length=128)
    deadline_at: datetime | None = None
    budget_limit: Decimal | None = Field(
        default=None, gt=0, max_digits=38, decimal_places=18
    )
    budget_currency: str | None = Field(default=None, min_length=1, max_length=16)

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
        self.tool_keys = [item.strip() for item in self.tool_keys if item.strip()]
        if len(set(self.tool_keys)) != len(self.tool_keys):
            raise ValueError("Research Tool selection contains duplicates")
        if len(set(self.knowledge_ids)) != len(self.knowledge_ids):
            raise ValueError("Knowledge selection contains duplicates")
        if len(set(self.resource_type_ids)) != len(self.resource_type_ids):
            raise ValueError("Resource requirement selection contains duplicates")
        if (self.budget_limit is None) != (self.budget_currency is None):
            raise ValueError("Budget limit and currency must be provided together")
        if self.budget_currency is not None:
            self.budget_currency = normalize_currency(self.budget_currency)
        if self.deadline_at is not None:
            if self.deadline_at.tzinfo is None:
                self.deadline_at = self.deadline_at.replace(tzinfo=UTC)
            if self.deadline_at <= utcnow():
                raise ValueError("Research Task deadline must be in the future")
        return self


class ResearchTaskCreate(ResearchTaskDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class TaskTransitionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    reason: str = Field(default="", max_length=4_000)


class ResearchRunDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_task_revision: int = Field(ge=1)
    source_run_id: UUID
    kind: Literal["retry", "replication", "continuation"]
    purpose: str = Field(min_length=1, max_length=4_000)
    idempotency_key: str = Field(min_length=8, max_length=160)

    @model_validator(mode="after")
    def normalize(self):
        self.purpose = self.purpose.strip()
        self.idempotency_key = self.idempotency_key.strip()
        if not self.purpose:
            raise ValueError("Research Run purpose cannot be empty")
        if len(self.idempotency_key) < 8:
            raise ValueError("Research Run idempotency key is too short")
        return self


class ResearchRunCreate(ResearchRunDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class TaskCompleteParams(TaskTransitionParams):
    outcome: ResearchTaskOutcome
    scientific_outcome: ScientificOutcome
    conclusion: str = Field(min_length=1, max_length=100_000)
    review_recommendation_id: UUID | None = None


class ResearchReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_task_revision: int = Field(ge=1)


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


def _new_run_command(
    *,
    task: ResearchTask,
    source_run: ResearchRun,
    next_run_number: int,
    params: ResearchRunDraft,
) -> dict[str, Any]:
    return {
        "task_id": str(task.id),
        "task_revision": task.revision,
        "source_run_id": str(source_run.id),
        "source_run_number": source_run.run_number,
        "source_environment_digest": canonical_digest(
            source_run.environment_snapshot or {}
        ),
        "source_result_digest": canonical_digest(source_run.result_package or {}),
        "next_run_number": next_run_number,
        "kind": params.kind,
        "purpose": params.purpose,
        "idempotency_key": params.idempotency_key,
    }


async def _validate_new_run(
    db_session: DBSession,
    *,
    task: ResearchTask,
    params: ResearchRunDraft,
) -> tuple[ResearchRun, int, dict[str, Any]]:
    if task.revision != params.expected_task_revision:
        raise HTTPException(status_code=409, detail="Research Task has changed")
    if task.status not in {
        ResearchTaskStatus.COMPLETED.value,
        ResearchTaskStatus.FAILED.value,
        ResearchTaskStatus.CANCELLED.value,
    }:
        raise HTTPException(
            status_code=409,
            detail="Complete, fail, or cancel the current Research Task first",
        )
    source_run = await db_session.get(ResearchRun, params.source_run_id)
    if source_run is None or source_run.task_id != task.id:
        raise HTTPException(status_code=404, detail="Source Research Run not found")
    if source_run.status not in TERMINAL_RUN_STATUSES:
        raise HTTPException(
            status_code=409, detail="Source Research Run must be terminal"
        )
    nonterminal_run = (
        await db_session.scalars(
            select(ResearchRun)
            .where(
                ResearchRun.task_id == task.id,
                ResearchRun.status.not_in(TERMINAL_RUN_STATUSES),
            )
            .limit(1)
        )
    ).first()
    if nonterminal_run is not None:
        raise HTTPException(
            status_code=409,
            detail="Complete, cancel, or resume the current Research Run first",
        )
    operational_limit = await reached_operational_limit(db_session, task=task)
    if operational_limit is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Research Task {operational_limit[0]} limit has been reached",
        )
    next_run_number = (
        await db_session.scalar(
            select(func.max(ResearchRun.run_number)).where(
                ResearchRun.task_id == task.id
            )
        )
        or 0
    ) + 1
    command = _new_run_command(
        task=task,
        source_run=source_run,
        next_run_number=next_run_number,
        params=params,
    )
    return source_run, next_run_number, command


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
    list[Any],
    list[dict[str, Any]],
    list[KnowledgeItem],
    list[tuple[ResourceType, ResourceTypeRevision]],
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

    from app.services.research_tools import get_research_tool

    tools = []
    for tool_key in draft.tool_keys:
        try:
            tools.append(get_research_tool(tool_key))
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    capability_snapshots = [
        *[
            protocol_capability(protocol, version).payload()
            for protocol, version in protocols
        ],
        *[tool_capability(definition).payload() for definition in tools],
    ]
    executor_bindings = []
    for capability in capability_snapshots:
        try:
            executor_bindings.append(
                await resolve_executor_binding(
                    db_session,
                    lab_id=lab.id,
                    capability=capability,
                    owner_user_id=owner.id,
                    project_id=project.id,
                    autonomy_level=draft.autonomy_level,
                )
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    denied = next(
        (
            binding
            for binding in executor_bindings
            if binding["approval_policy"] == "deny"
        ),
        None,
    )
    if denied is not None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Capability {denied['capability_key']} is denied by the current "
                "Lab Executor Binding"
            ),
        )
    for binding in executor_bindings:
        try:
            enforce_environment_binding_scope(
                binding,
                project_id=project.id,
                autonomy_level=draft.autonomy_level,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    for binding in executor_bindings:
        if binding["executor_type"] != "human":
            continue
        executor_ref = binding.get("resolved_executor_ref") or binding.get(
            "executor_ref"
        )
        if (executor_ref or {}).get("type") != "user":
            raise HTTPException(
                status_code=422,
                detail="Protocol Executor Binding did not resolve to a user",
            )
        executor = await db_session.get(User, UUID(str(executor_ref["id"])))
        if executor is None:
            raise HTTPException(status_code=422, detail="Protocol executor not found")
        await require_research_capability(
            db_session,
            user=executor,
            project=project,
            capability="research.run",
        )

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

    resources: list[tuple[ResourceType, ResourceTypeRevision]] = []
    for resource_type_id in draft.resource_type_ids:
        resource_type = await ResourceType.find_by(
            db_session,
            [
                ResourceType.id == resource_type_id,
                ResourceType.lab_id == lab.id,
                ResourceType.archived_at.is_(None),
            ],
        )
        if resource_type is None or resource_type.current_revision_id is None:
            raise HTTPException(
                status_code=422,
                detail=f"Resource type {resource_type_id} is unavailable in this Lab",
            )
        revision = await db_session.get(
            ResourceTypeRevision, resource_type.current_revision_id
        )
        if revision is None:
            raise HTTPException(
                status_code=409,
                detail=f"Resource type {resource_type.name} has no current revision",
            )
        for user in {current_user.id: current_user, owner.id: owner}.values():
            access = await resolve_resource_access(
                db_session,
                user.id,
                lab.id,
                resource_type_id=resource_type.id,
            )
            if not access.allows("resource.read"):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"{user.name or user.username} cannot read the selected "
                        f"Resource type {resource_type.name}"
                    ),
                )
        resources.append((resource_type, revision))

    command = research_task_command(
        project_id=project.id,
        title=draft.title,
        goal=draft.goal,
        success_criteria=draft.success_criteria,
        stop_conditions=draft.stop_conditions,
        autonomy_level=draft.autonomy_level,
        protocol_ids=[protocol.id for protocol, _version in protocols],
        tool_refs=[
            {"key": definition.key, "version": definition.version}
            for definition in tools
        ],
        executor_binding_refs=executor_bindings,
        knowledge_refs=[
            {"id": item.id, "revision": item.revision} for item in knowledge_items
        ],
        resource_refs=[
            {
                "id": resource_type.id,
                "revision_id": revision.id,
                "revision": revision.revision,
            }
            for resource_type, revision in resources
        ],
        deadline_at=draft.deadline_at,
        budget_limit=draft.budget_limit,
        budget_currency=draft.budget_currency,
        owner_user_id=owner.id,
        ai_model=draft.ai_model,
    )
    return (
        command,
        project,
        lab,
        owner,
        protocols,
        tools,
        executor_bindings,
        knowledge_items,
        resources,
    )


def _task_preview(
    *,
    command: dict[str, Any],
    project: Project,
    lab: Lab,
    owner: User,
    protocols: list[tuple[Protocol, ProtocolVersion]],
    tools: list[Any],
    executor_bindings: list[dict[str, Any]],
    knowledge_items: list[KnowledgeItem],
    resources: list[tuple[ResourceType, ResourceTypeRevision]],
) -> dict[str, Any]:
    ai_path_available = config.effective_ai_enabled and bool(protocols or tools)
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
        "tools": [definition.payload() for definition in tools],
        "executor_bindings": executor_bindings,
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
        "resources": [
            resource_capability(resource_type, revision).payload()
            for resource_type, revision in resources
        ],
        "operational_limits": {
            "deadline_at": command["deadline_at"],
            "budget_limit": command["budget_limit"],
            "budget_currency": command["budget_currency"],
        },
        "effects": [
            "Create a versioned Research Task and draft Research Run",
            "Pin the selected Protocol versions in the Research Environment",
            "Pin the selected digital Tool versions in the Research Environment",
            "Pin reviewed Knowledge revisions in the Research Environment",
            "Pin selected resource-type revisions as explicit requirements",
            "Enforce the confirmed deadline and budget as runtime stop boundaries",
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
                (
                    "Aira is unavailable. The Task remains fully usable through "
                    "manual Protocol and digital Actions."
                    if not config.effective_ai_enabled
                    else "No executable capability is selected for Aira."
                )
            ]
        ),
        "ai_instance_available": config.effective_ai_enabled,
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
        "deadline_at": task.deadline_at.isoformat() if task.deadline_at else None,
        "budget_limit": (
            str(task.budget_limit) if task.budget_limit is not None else None
        ),
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
        "ai_available": bool(
            config.effective_ai_enabled
            and run is not None
            and research_environment_has_ai_path(run.environment_snapshot or {})
        ),
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
    tool_job = await ResearchToolJob.find_by(
        db_session, [ResearchToolJob.action_id == action.id]
    )
    instrument_job = await ResearchInstrumentJob.find_by(
        db_session, [ResearchInstrumentJob.action_id == action.id]
    )
    wait_event = await ResearchWaitEvent.find_by(
        db_session, [ResearchWaitEvent.action_id == action.id]
    )
    resource_reservation = await ResearchResourceReservation.find_by(
        db_session, [ResearchResourceReservation.action_id == action.id]
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
        "tool_job": tool_job.as_dict() if tool_job else None,
        "instrument_job": instrument_job.as_dict() if instrument_job else None,
        "wait_event": wait_event.as_dict() if wait_event else None,
        "resource_reservation": (
            resource_reservation.as_dict() if resource_reservation else None
        ),
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


async def _research_review_context(
    db_session: DBSession,
    task: ResearchTask,
    *,
    scientific_assets: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], ResearchRun | None]:
    run = await _latest_run(db_session, task.id)
    actions = (
        list(
            (
                await db_session.scalars(
                    select(ResearchAction)
                    .where(ResearchAction.run_id == run.id)
                    .order_by(ResearchAction.sequence)
                )
            ).all()
        )
        if run is not None
        else []
    )
    assets = scientific_assets or await research_asset_bundle(
        db_session, task_id=task.id
    )
    return (
        {
            "schema": "airalogy.research-review-context.v1",
            "task": {
                "id": str(task.id),
                "revision": task.revision,
                "goal": task.goal,
                "success_criteria": task.success_criteria,
                "stop_conditions": task.stop_conditions,
                "status": task.status,
                "existing_outcome": task.outcome,
                "existing_scientific_outcome": task.scientific_outcome,
            },
            "result_package": task.result_package or {},
            "latest_run": (
                {
                    "id": str(run.id),
                    "run_number": run.run_number,
                    "status": run.status,
                    "last_error": run.last_error,
                    "result_package": run.result_package or {},
                    "environment_digest": canonical_digest(
                        run.environment_snapshot or {}
                    ),
                }
                if run is not None
                else None
            ),
            "actions": [
                {
                    "id": str(action.id),
                    "sequence": action.sequence,
                    "kind": action.kind,
                    "status": action.status,
                    "title": action.title,
                    "output": action.output_data,
                    "error": action.error,
                }
                for action in actions
            ],
            "available_evidence": assets["evidence"],
            "claims": assets["claims"],
            "data_assets": assets["data_assets"],
            "knowledge_items": assets["knowledge_items"],
            "protocol_improvements": assets["protocol_improvements"],
        },
        run,
    )


async def _task_detail(
    db_session: DBSession,
    task: ResearchTask,
    project: Project,
    lab: Lab,
    current_user: User,
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
    resources = [
        {
            **row.snapshot,
            "position": row.position,
        }
        for row in list(
            (
                await db_session.scalars(
                    select(ResearchTaskResourceRequirement)
                    .where(ResearchTaskResourceRequirement.task_id == task.id)
                    .order_by(ResearchTaskResourceRequirement.position)
                )
            ).all()
        )
    ]
    review_recommendations = list(
        (
            await db_session.scalars(
                select(ResearchReviewRecommendation)
                .where(ResearchReviewRecommendation.task_id == task.id)
                .order_by(ResearchReviewRecommendation.created_at.desc())
                .limit(10)
            )
        ).all()
    )
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
        "resources": resources,
        "review_recommendations": [item.as_dict() for item in review_recommendations],
        "permissions": {
            "can_run": await has_research_capability(
                db_session,
                user=current_user,
                project=project,
                capability="research.run",
            ),
            "can_approve": await has_research_capability(
                db_session,
                user=current_user,
                project=project,
                capability="research.approve",
            ),
        },
    }


@router.post("/preview")
async def preview_research_task(
    params: ResearchTaskDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    (
        command,
        project,
        lab,
        owner,
        protocols,
        tools,
        executor_bindings,
        knowledge_items,
        resources,
    ) = await _validate_task_draft(db_session, current_user, params)
    return _task_preview(
        command=command,
        project=project,
        lab=lab,
        owner=owner,
        protocols=protocols,
        tools=tools,
        executor_bindings=executor_bindings,
        knowledge_items=knowledge_items,
        resources=resources,
    )


@router.post("")
async def create_research_task(
    params: ResearchTaskCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    (
        command,
        project,
        lab,
        owner,
        protocols,
        tools,
        executor_bindings,
        knowledge_items,
        resources,
    ) = await _validate_task_draft(db_session, current_user, params)
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
        deadline_at=params.deadline_at,
        budget_limit=params.budget_limit,
        budget_currency=params.budget_currency,
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
    pinned_resources: list[dict[str, Any]] = []
    for position, (resource_type, revision) in enumerate(resources, start=1):
        snapshot = resource_capability(resource_type, revision).payload()
        pinned_resources.append(snapshot)
        db_session.add(
            ResearchTaskResourceRequirement(
                task_id=task.id,
                resource_type_id=resource_type.id,
                resource_type_revision_id=revision.id,
                resource_type_revision=revision.revision,
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
    protocol_capabilities = [
        protocol_capability(protocol, version).payload()
        for _task_protocol, protocol, version in rows
    ]
    tool_capabilities = [tool_capability(definition).payload() for definition in tools]
    environment_snapshot = {
        "schema": "airalogy.research-environment.v2",
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
        "tools": [definition.payload() for definition in tools],
        "resources": pinned_resources,
        "capabilities": [
            *protocol_capabilities,
            *tool_capabilities,
            *pinned_resources,
        ],
        "executor_bindings": executor_bindings,
        "knowledge": pinned_knowledge,
        "ai_available_at_capture": config.effective_ai_enabled,
        "autonomy_level": task.autonomy_level,
        "operational_limits": {
            "deadline_at": task.deadline_at.isoformat() if task.deadline_at else None,
            "budget_limit": (
                str(task.budget_limit) if task.budget_limit is not None else None
            ),
            "budget_currency": task.budget_currency,
        },
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
    return await _task_detail(db_session, task, project, lab, current_user)


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
    return await _task_detail(db_session, task, project, lab, current_user)


@router.post("/{task_id}/runs/preview")
async def preview_research_run(
    task_id: UUID,
    params: ResearchRunDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, project, lab = await _task_context(
        db_session, current_user, task_id, "research.run"
    )
    source_run, next_run_number, command = await _validate_new_run(
        db_session, task=task, params=params
    )
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
        },
        "source_run": {
            "id": str(source_run.id),
            "run_number": source_run.run_number,
            "status": source_run.status,
            "environment_digest": command["source_environment_digest"],
            "result_digest": command["source_result_digest"],
        },
        "new_run": {"run_number": next_run_number, "kind": params.kind},
        "effects": [
            "Create a new draft Research Run under the same Research Task",
            "Inherit the exact source Research Environment without changing versions",
            "Preserve every prior Run, Action, Record, Evidence, and Result Package",
            "Reopen the Task for an explicit new execution and human review",
        ],
    }


@router.post("/{task_id}/runs")
async def create_research_run(
    task_id: UUID,
    params: ResearchRunCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, project, lab = await _task_context(
        db_session, current_user, task_id, "research.run"
    )
    task = (
        await db_session.scalars(
            select(ResearchTask)
            .where(ResearchTask.id == task.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Research Task not found")
    event_key = f"research-run:{task.id}:{params.idempotency_key}"
    existing_event = await ResearchEvent.find_by(
        db_session, [ResearchEvent.idempotency_key == event_key]
    )
    if existing_event is not None:
        if (
            existing_event.kind != "run.created"
            or existing_event.payload.get("preview_digest") != params.preview_digest
            or existing_event.run_id is None
        ):
            raise HTTPException(
                status_code=409, detail="Research Run idempotency key is already in use"
            )
        return await _task_detail(db_session, task, project, lab, current_user)

    source_run, next_run_number, command = await _validate_new_run(
        db_session, task=task, params=params
    )
    preview_digest = canonical_digest(command)
    if preview_digest != params.preview_digest:
        raise HTTPException(status_code=409, detail="Research Run preview has changed")
    released_resource_ids = await release_research_run_reservations(
        db_session,
        run_id=source_run.id,
        actor_user_id=current_user.id,
        reason=f"Preparing Research Run {next_run_number}",
    )
    origin = {
        "kind": params.kind,
        "purpose": params.purpose,
        "source_run_id": str(source_run.id),
        "source_run_number": source_run.run_number,
        "source_environment_digest": command["source_environment_digest"],
        "source_result_digest": command["source_result_digest"],
        "created_at": utcnow().isoformat(),
    }
    environment_snapshot = deepcopy(source_run.environment_snapshot or {})
    environment_snapshot["run_origin"] = origin
    run = ResearchRun(
        task_id=task.id,
        run_number=next_run_number,
        status=ResearchRunStatus.DRAFT.value,
        environment_snapshot=environment_snapshot,
        aira_state=initial_aira_state(task.goal),
        requested_by_user_id=current_user.id,
    )
    db_session.add(run)
    await db_session.flush()
    rows = await task_protocol_rows(db_session, task.id)
    await create_plan_version(
        db_session,
        task=task,
        run=run,
        kind=params.kind,
        plan={
            "workflow": workflow_info_for_task(
                task,
                project,
                lab,
                rows,
                knowledge_context=list(environment_snapshot.get("knowledge") or []),
            ),
            "success_criteria": task.success_criteria,
            "stop_conditions": task.stop_conditions,
            "run_origin": origin,
        },
        summary=f"{params.kind.replace('_', ' ').title()}: {params.purpose}",
    )
    task.status = ResearchTaskStatus.DRAFT.value
    task.outcome = None
    task.scientific_outcome = None
    task.conclusion = ""
    task.result_package = {}
    task.completed_at = None
    task.revision += 1
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        kind="run.created",
        actor_user_id=current_user.id,
        payload={
            "preview_digest": preview_digest,
            "kind": params.kind,
            "purpose": params.purpose,
            "source_run_id": str(source_run.id),
            "source_run_number": source_run.run_number,
            "run_number": run.run_number,
            "released_resource_reservation_ids": [
                str(item) for item in released_resource_ids
            ],
        },
        idempotency_key=event_key,
    )
    await db_session.commit()
    return await _task_detail(db_session, task, project, lab, current_user)


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
    operational_limit = await reached_operational_limit(db_session, task=task)
    if operational_limit is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Research Task {operational_limit[0]} limit has been reached",
        )

    now = utcnow()
    ai_path_available = bool(
        config.effective_ai_enabled
        and research_environment_has_ai_path(run.environment_snapshot or {})
    )
    run.status = (
        ResearchRunStatus.PLANNING.value
        if ai_path_available
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
            "ai": ai_path_available,
            "reason": params.reason,
        },
        idempotency_key=f"run:{run.id}:started",
    )
    if ai_path_available:
        await enqueue_research_advance(db_session, task=task, run=run)
    else:
        await emit_research_event(
            db_session,
            task_id=task.id,
            run_id=run.id,
            kind="run.manual_control_required",
            actor_user_id=current_user.id,
            payload={"reason": "ai_unavailable_or_no_capability"},
            idempotency_key=f"run:{run.id}:manual:start",
        )
    await db_session.commit()
    return await _task_detail(db_session, task, project, lab, current_user)


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
    active_instrument_job = (
        await db_session.scalars(
            select(ResearchInstrumentJob)
            .join(ResearchAction, ResearchAction.id == ResearchInstrumentJob.action_id)
            .where(
                ResearchAction.run_id == run.id,
                ResearchInstrumentJob.status.in_(
                    [
                        ResearchInstrumentJobStatus.QUEUED.value,
                        ResearchInstrumentJobStatus.LEASED.value,
                        ResearchInstrumentJobStatus.RUNNING.value,
                        ResearchInstrumentJobStatus.STOP_REQUESTED.value,
                    ]
                ),
            )
            .limit(1)
            .with_for_update()
        )
    ).first()
    if active_instrument_job is not None and active_instrument_job.status in {
        ResearchInstrumentJobStatus.LEASED.value,
        ResearchInstrumentJobStatus.RUNNING.value,
    }:
        now = utcnow()
        active_instrument_job.status = (
            ResearchInstrumentJobStatus.STOP_REQUESTED.value
        )
        active_instrument_job.stop_reason = params.reason or "Research Task paused"
        active_instrument_job.stop_requested_at = now
        active_instrument_job.revision += 1
        instrument_action = await db_session.get(
            ResearchAction, active_instrument_job.action_id
        )
        if instrument_action is not None:
            instrument_action.status = ResearchActionStatus.WAITING.value
            instrument_action.error = (
                f"Stop requested: {active_instrument_job.stop_reason}"
            )
            instrument_action.revision += 1
        await emit_research_event(
            db_session,
            task_id=task.id,
            run_id=run.id,
            action_id=active_instrument_job.action_id,
            kind="instrument_job.stop_requested",
            actor_user_id=current_user.id,
            payload={
                "instrument_job_id": str(active_instrument_job.id),
                "reason": active_instrument_job.stop_reason,
            },
            idempotency_key=(
                f"instrument-job:{active_instrument_job.id}:pause:"
                f"{active_instrument_job.revision}"
            ),
        )
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
    return await _task_detail(db_session, task, project, lab, current_user)


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
    operational_limit = await reached_operational_limit(db_session, task=task)
    if operational_limit is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Research Task {operational_limit[0]} limit has been reached",
        )
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
    active_instrument_job = (
        await db_session.scalars(
            select(ResearchInstrumentJob)
            .join(ResearchAction, ResearchAction.id == ResearchInstrumentJob.action_id)
            .where(
                ResearchAction.run_id == run.id,
                ResearchInstrumentJob.status.in_(
                    [
                        ResearchInstrumentJobStatus.QUEUED.value,
                        ResearchInstrumentJobStatus.LEASED.value,
                        ResearchInstrumentJobStatus.RUNNING.value,
                        ResearchInstrumentJobStatus.STOP_REQUESTED.value,
                    ]
                ),
            )
            .limit(1)
        )
    ).first()
    if (
        active_instrument_job is not None
        and active_instrument_job.status
        == ResearchInstrumentJobStatus.STOP_REQUESTED.value
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Wait for the Instrument Gateway to acknowledge the stop and inspect "
                "the equipment before resuming"
            ),
        )
    task.status = ResearchTaskStatus.ACTIVE.value
    task.outcome = None
    task.revision += 1
    run.last_error = None
    run.completed_at = None
    if open_work_item is not None:
        run.status = ResearchRunStatus.WAITING_FOR_HUMAN.value
    elif active_instrument_job is not None:
        run.status = ResearchRunStatus.WAITING_FOR_INSTRUMENT.value
    else:
        run.status = ResearchRunStatus.RUNNING.value
        if config.effective_ai_enabled and research_environment_has_ai_path(
            run.environment_snapshot or {}
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
    return await _task_detail(db_session, task, project, lab, current_user)


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
        released_resource_ids = await release_research_run_reservations(
            db_session,
            run_id=run.id,
            actor_user_id=current_user.id,
            reason=params.reason or "Research Task cancelled",
        )
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
            tool_jobs = list(
                (
                    await db_session.scalars(
                        select(ResearchToolJob).where(
                            ResearchToolJob.action_id.in_(
                                [action.id for action in actions]
                            ),
                            ResearchToolJob.status.in_(
                                [
                                    ResearchToolJobStatus.QUEUED.value,
                                    ResearchToolJobStatus.RUNNING.value,
                                ]
                            ),
                        )
                    )
                ).all()
            )
            for tool_job in tool_jobs:
                tool_job.status = ResearchToolJobStatus.CANCELLED.value
                tool_job.completed_at = now
            instrument_jobs = list(
                (
                    await db_session.scalars(
                        select(ResearchInstrumentJob).where(
                            ResearchInstrumentJob.action_id.in_(
                                [action.id for action in actions]
                            ),
                            ResearchInstrumentJob.status.in_(
                                [
                                    ResearchInstrumentJobStatus.QUEUED.value,
                                    ResearchInstrumentJobStatus.LEASED.value,
                                    ResearchInstrumentJobStatus.RUNNING.value,
                                    ResearchInstrumentJobStatus.STOP_REQUESTED.value,
                                ]
                            ),
                        )
                    )
                ).all()
            )
            for instrument_job in instrument_jobs:
                instrument_job.stop_reason = params.reason or "Task cancelled"
                instrument_job.stop_requested_at = now
                instrument_job.revision += 1
                if (
                    instrument_job.status
                    == ResearchInstrumentJobStatus.QUEUED.value
                ):
                    instrument_job.status = ResearchInstrumentJobStatus.CANCELLED.value
                    instrument_job.completed_at = now
                else:
                    instrument_job.status = (
                        ResearchInstrumentJobStatus.STOP_REQUESTED.value
                    )
            wait_events = list(
                (
                    await db_session.scalars(
                        select(ResearchWaitEvent).where(
                            ResearchWaitEvent.action_id.in_(
                                [action.id for action in actions]
                            ),
                            ResearchWaitEvent.status
                            == ResearchWaitEventStatus.WAITING.value,
                        )
                    )
                ).all()
            )
            for wait_event in wait_events:
                wait_event.status = ResearchWaitEventStatus.CANCELLED.value
                wait_event.revision += 1
            resource_proposals = list(
                (
                    await db_session.scalars(
                        select(ResearchResourceReservation).where(
                            ResearchResourceReservation.action_id.in_(
                                [action.id for action in actions]
                            ),
                            ResearchResourceReservation.status
                            == ResearchResourceReservationStatus.PROPOSED.value,
                        )
                    )
                ).all()
            )
            for resource_proposal in resource_proposals:
                resource_proposal.status = (
                    ResearchResourceReservationStatus.CANCELLED.value
                )
                resource_proposal.revision += 1
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
        payload={
            "reason": params.reason,
            "released_resource_reservation_ids": [
                str(item) for item in released_resource_ids
            ]
            if run
            else [],
        },
    )
    await db_session.commit()
    return await _task_detail(db_session, task, project, lab, current_user)


@router.post("/{task_id}/review-recommendations")
async def generate_review_recommendation(
    task_id: UUID,
    params: ResearchReviewRequest,
    current_user: CurrentUser,
    db_session: DBSession,
):
    if not config.effective_ai_enabled:
        raise HTTPException(status_code=503, detail="Reviewer Agent is not available")
    task, project, lab = await _task_context(
        db_session, current_user, task_id, "research.read"
    )
    if task.revision != params.expected_task_revision:
        raise HTTPException(status_code=409, detail="Research Task has changed")
    if task.status in {
        ResearchTaskStatus.COMPLETED.value,
        ResearchTaskStatus.CANCELLED.value,
        ResearchTaskStatus.ARCHIVED.value,
    }:
        raise HTTPException(
            status_code=409,
            detail="Reviewer Agent only evaluates a Task before final completion",
        )
    if current_user.id != task.owner_user_id:
        await require_research_capability(
            db_session,
            user=current_user,
            project=project,
            capability="research.approve",
        )
    review_context, _run = await _research_review_context(db_session, task)
    context_digest = canonical_digest(review_context)
    model_name = config.CHAT_MODEL_DEEP
    existing = await ResearchReviewRecommendation.find_by(
        db_session,
        [
            ResearchReviewRecommendation.task_id == task.id,
            ResearchReviewRecommendation.context_digest == context_digest,
            ResearchReviewRecommendation.model_name == model_name,
        ],
    )
    if existing is not None:
        return existing.as_dict()
    usage_context = create_usage_context(
        feature="research.review.recommendation",
        user_id=current_user.id,
        lab_id=lab.id,
        project_id=project.id,
        attributes={
            "task_id": str(task.id),
            "task_revision": str(task.revision),
            "context_digest": context_digest,
        },
    )
    # Model latency must not keep a database transaction open.
    await db_session.commit()
    output = await generate_research_review(
        context=review_context,
        model_name=model_name,
        usage_context=usage_context,
    )

    current_task, current_project, _current_lab = await _task_context(
        db_session, current_user, task_id, "research.read"
    )
    if current_user.id != current_task.owner_user_id:
        await require_research_capability(
            db_session,
            user=current_user,
            project=current_project,
            capability="research.approve",
        )
    current_context, current_run = await _research_review_context(
        db_session, current_task
    )
    if (
        current_task.revision != params.expected_task_revision
        or canonical_digest(current_context) != context_digest
    ):
        raise HTTPException(
            status_code=409,
            detail="Research results changed while Reviewer Agent was evaluating them",
        )
    recommendation = ResearchReviewRecommendation(
        task_id=current_task.id,
        run_id=current_run.id if current_run else None,
        task_revision=current_task.revision,
        context_digest=context_digest,
        model_name=model_name,
        recommendation=output.recommendation,
        recommended_task_outcome=output.recommended_task_outcome.value,
        recommended_scientific_outcome=(output.recommended_scientific_outcome.value),
        summary=output.summary,
        supporting_evidence_ids=output.supporting_evidence_ids,
        contradicting_evidence_ids=output.contradicting_evidence_ids,
        uncertainties=output.uncertainties,
        missing_checks=output.missing_checks,
        risk_flags=output.risk_flags,
        requested_by_user_id=current_user.id,
    )
    db_session.add(recommendation)
    try:
        await db_session.flush()
    except IntegrityError:
        await db_session.rollback()
        concurrent = await ResearchReviewRecommendation.find_by(
            db_session,
            [
                ResearchReviewRecommendation.task_id == task_id,
                ResearchReviewRecommendation.context_digest == context_digest,
                ResearchReviewRecommendation.model_name == model_name,
            ],
        )
        if concurrent is None:
            raise
        return concurrent.as_dict()
    await emit_research_event(
        db_session,
        task_id=current_task.id,
        run_id=current_run.id if current_run else None,
        kind="review.recommendation_generated",
        actor_user_id=None,
        payload={
            "recommendation_id": str(recommendation.id),
            "recommendation": recommendation.recommendation,
            "model": model_name,
            "requested_by_user_id": str(current_user.id),
            "context_digest": context_digest,
        },
        idempotency_key=f"review-recommendation:{recommendation.id}",
    )
    await db_session.commit()
    return recommendation.as_dict()


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
    pending_evidence = await ResearchEvidence.count(
        db_session,
        [
            ResearchEvidence.task_id == task.id,
            ResearchEvidence.quality_state == EvidenceQuality.PENDING.value,
        ],
    )
    pending_claims = await ResearchClaim.count(
        db_session,
        [
            ResearchClaim.task_id == task.id,
            ResearchClaim.state.in_(
                [ClaimState.SUGGESTED.value, ClaimState.DRAFT.value]
            ),
        ],
    )
    if pending_evidence or pending_claims:
        raise HTTPException(
            status_code=409,
            detail=(
                "Review or reject pending Evidence and Claims before completing "
                "the Research Task"
            ),
        )
    scientific_assets = await research_asset_bundle(db_session, task_id=task.id)
    review_recommendation = None
    if params.review_recommendation_id is not None:
        review_recommendation = await db_session.get(
            ResearchReviewRecommendation, params.review_recommendation_id
        )
        if review_recommendation is None or review_recommendation.task_id != task.id:
            raise HTTPException(
                status_code=422,
                detail="Review recommendation does not belong to this Research Task",
            )
        current_review_context, _review_run = await _research_review_context(
            db_session,
            task,
            scientific_assets=scientific_assets,
        )
        if (
            review_recommendation.task_revision != task.revision
            or review_recommendation.context_digest
            != canonical_digest(current_review_context)
        ):
            raise HTTPException(
                status_code=409,
                detail="Review recommendation is stale; generate or review it again",
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
    unfinished_actions = await db_session.scalar(
        select(func.count())
        .select_from(ResearchAction)
        .join(ResearchRun, ResearchRun.id == ResearchAction.run_id)
        .where(
            ResearchRun.task_id == task.id,
            ResearchAction.status.in_(
                [
                    ResearchActionStatus.PROPOSED.value,
                    ResearchActionStatus.APPROVED.value,
                    ResearchActionStatus.QUEUED.value,
                    ResearchActionStatus.RUNNING.value,
                    ResearchActionStatus.WAITING.value,
                    ResearchActionStatus.SUBMITTED.value,
                    ResearchActionStatus.VALIDATING.value,
                ]
            ),
        )
    )
    if unfinished_actions:
        raise HTTPException(
            status_code=409,
            detail="Complete or cancel unfinished Research Actions first",
        )
    run = await _latest_run(db_session, task.id)
    now = utcnow()
    if run is not None:
        released_resource_ids = await release_research_run_reservations(
            db_session,
            run_id=run.id,
            actor_user_id=current_user.id,
            reason=params.reason or "Research Task completed",
        )
        run.status = ResearchRunStatus.COMPLETED.value
        run.completed_at = run.completed_at or now
    task.status = ResearchTaskStatus.COMPLETED.value
    task.outcome = params.outcome.value
    task.scientific_outcome = params.scientific_outcome.value
    task.conclusion = params.conclusion.strip()
    task.completed_at = now
    task.result_package = {
        **(task.result_package or {}),
        **scientific_assets,
        "goal_assessment": params.outcome.value,
        "scientific_outcome": params.scientific_outcome.value,
        "reviewed_conclusion": task.conclusion,
        "reviewed_by_user_id": str(current_user.id),
        "reviewed_at": now.isoformat(),
        "review_recommendation": (
            review_recommendation.as_dict()
            if review_recommendation is not None
            else None
        ),
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
            "released_resource_reservation_ids": [
                str(item) for item in released_resource_ids
            ]
            if run
            else [],
        },
    )
    await db_session.commit()
    return await _task_detail(db_session, task, project, lab, current_user)


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
    operational_limit = await reached_operational_limit(db_session, task=task)
    if operational_limit is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Research Task {operational_limit[0]} limit has been reached",
        )
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
    # Supersede any planner result computed against the previous manual state.
    run.advance_generation += 1
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
    operational_limit = await reached_operational_limit(db_session, task=task)
    if operational_limit is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Research Task {operational_limit[0]} limit has been reached",
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
    existing_evidence = await ResearchEvidence.find_by(
        db_session,
        [
            ResearchEvidence.task_id == task.id,
            ResearchEvidence.artifact_type == "record",
            ResearchEvidence.artifact_id == str(record.id),
            ResearchEvidence.artifact_version == str(record.version),
            ResearchEvidence.kind == EvidenceKind.OBSERVATION.value,
        ],
    )
    if existing_evidence is None:
        evidence = ResearchEvidence(
            task_id=task.id,
            run_id=run.id,
            action_id=action.id,
            kind=EvidenceKind.OBSERVATION.value,
            artifact_type="record",
            artifact_id=str(record.id),
            artifact_version=str(record.version),
            summary=params.note.strip() or f"Validated Record for {action.title}",
            quality_state=EvidenceQuality.VALIDATED.value,
            validation_report=protocol_run.validation_report,
            created_by_user_id=current_user.id,
            reviewed_by_user_id=current_user.id,
            reviewed_at=now,
        )
        db_session.add(evidence)
        await db_session.flush()
        await emit_research_event(
            db_session,
            task_id=task.id,
            run_id=run.id,
            action_id=action.id,
            work_item_id=item.id,
            kind="evidence.registered",
            actor_user_id=current_user.id,
            payload={
                "evidence_id": str(evidence.id),
                "kind": evidence.kind,
                "quality_state": evidence.quality_state,
            },
            idempotency_key=f"evidence:{evidence.id}:registered",
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
    if config.effective_ai_enabled and research_environment_has_ai_path(
        run.environment_snapshot or {}
    ):
        await enqueue_research_advance(db_session, task=task, run=run)
    else:
        await emit_research_event(
            db_session,
            task_id=task.id,
            run_id=run.id,
            kind="run.manual_control_required",
            actor_user_id=current_user.id,
            payload={"reason": "ai_disabled_or_no_capability_after_record"},
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
    operational_limit = await reached_operational_limit(db_session, task=task)
    if operational_limit is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Research Task {operational_limit[0]} limit has been reached",
        )
    if action.kind not in {
        ResearchActionKind.PROTOCOL_RUN.value,
        ResearchActionKind.TOOL_JOB.value,
        ResearchActionKind.RESOURCE_RESERVATION.value,
        ResearchActionKind.WAIT_EVENT.value,
    }:
        raise HTTPException(
            status_code=409, detail="Research Action type cannot be approved"
        )

    now = utcnow()
    approval.status = ResearchApprovalStatus.APPROVED.value
    approval.decision_reason = params.reason.strip()
    approval.decided_by_user_id = current_user.id
    approval.decided_at = now
    approval.revision += 1
    action.policy_decision = "allow"
    resource_event: tuple[str, dict[str, Any]] | None = None
    if action.kind == ResearchActionKind.PROTOCOL_RUN.value:
        protocol_run = await ResearchProtocolRun.find_by(
            db_session, [ResearchProtocolRun.action_id == action.id]
        )
        if protocol_run is None:
            raise HTTPException(status_code=409, detail="Protocol Run not found")
        protocol = await db_session.get(Protocol, protocol_run.protocol_id)
        version = await db_session.get(
            ProtocolVersion, protocol_run.protocol_version_id
        )
        if protocol is None or version is None:
            raise HTTPException(status_code=409, detail="Protocol context not found")
        try:
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
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
    elif action.kind == ResearchActionKind.TOOL_JOB.value:
        try:
            await activate_tool_action(
                db_session,
                task=task,
                run=run,
                action=action,
                actor_user_id=current_user.id,
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
    elif action.kind == ResearchActionKind.RESOURCE_RESERVATION.value:
        try:
            resource_event = await activate_aira_resource_action(
                db_session,
                task=task,
                run=run,
                action=action,
                actor_user_id=run.requested_by_user_id,
            )
        except (ResearchResourceError, IntegrityError) as error:
            await db_session.rollback()
            detail = (
                str(error)
                if isinstance(error, ResearchResourceError)
                else "Equipment is already booked in that time range"
            )
            raise HTTPException(status_code=409, detail=detail) from error
        if action.status == ResearchActionStatus.COMPLETED.value:
            await enqueue_research_advance(db_session, task=task, run=run)
    else:
        try:
            await activate_wait_event_action(
                db_session,
                task=task,
                run=run,
                action=action,
                actor_user_id=current_user.id,
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
    task.revision += 1
    if resource_event is not None:
        event_kind, event_payload = resource_event
        await emit_research_event(
            db_session,
            task_id=task.id,
            run_id=run.id,
            action_id=action.id,
            kind=event_kind,
            actor_user_id=current_user.id,
            payload=event_payload,
            idempotency_key=f"research-resource:{event_payload['reservation_id']}:created",
        )
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
    tool_job = await ResearchToolJob.find_by(
        db_session, [ResearchToolJob.action_id == action.id]
    )
    if tool_job is not None:
        tool_job.status = ResearchToolJobStatus.CANCELLED.value
        tool_job.completed_at = now
    wait_event = await ResearchWaitEvent.find_by(
        db_session, [ResearchWaitEvent.action_id == action.id]
    )
    if wait_event is not None:
        wait_event.status = ResearchWaitEventStatus.CANCELLED.value
        wait_event.revision += 1
    resource_reservation = await ResearchResourceReservation.find_by(
        db_session, [ResearchResourceReservation.action_id == action.id]
    )
    if (
        resource_reservation is not None
        and resource_reservation.status
        == ResearchResourceReservationStatus.PROPOSED.value
    ):
        resource_reservation.status = ResearchResourceReservationStatus.REJECTED.value
        resource_reservation.revision += 1

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
    if config.effective_ai_enabled and research_environment_has_ai_path(
        run.environment_snapshot or {}
    ):
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
