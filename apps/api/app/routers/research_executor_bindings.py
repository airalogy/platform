"""Lab-governed Executor Binding configuration and revision audit APIs."""

from __future__ import annotations

import json
import re
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.database import DBSession
from app.models.lab import Lab, LabRole, LabUser
from app.models.project import Project
from app.models.protocol import Protocol, ProtocolKind
from app.models.protocol_version import ProtocolVersion
from app.models.research_execution import (
    ResearchExecutorBinding,
    ResearchExecutorBindingAudit,
)
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.access_control import resolve_structured_access
from app.services.research_executor_bindings import executor_binding_snapshot
from app.services.research_runtime import (
    canonical_digest,
    has_research_capability,
    require_research_capability,
    utcnow,
)
from app.services.research_tools import research_tool_catalog

router = APIRouter(
    prefix="/research-executor-bindings", tags=["research-executor-bindings"]
)

SKILL_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")


class ExecutorBindingConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_project_ids: list[UUID] = Field(default_factory=list, max_length=100)
    allowed_autonomy_levels: list[
        Literal["assisted", "bounded_autopilot", "autonomous_within_policy"]
    ] = Field(default_factory=list, max_length=3)
    max_actions_per_run: int | None = Field(default=None, ge=1, le=100)
    required_skill_keys: list[str] = Field(default_factory=list, max_length=20)
    minimum_skill_level: int | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def reject_duplicates(self):
        self.required_skill_keys = [
            item.strip().lower() for item in self.required_skill_keys
        ]
        if len(set(self.allowed_project_ids)) != len(self.allowed_project_ids):
            raise ValueError("Allowed Project selection contains duplicates")
        if len(set(self.allowed_autonomy_levels)) != len(self.allowed_autonomy_levels):
            raise ValueError("Allowed autonomy selection contains duplicates")
        if len(set(self.required_skill_keys)) != len(self.required_skill_keys):
            raise ValueError("Required skill selection contains duplicates")
        if any(not SKILL_KEY_RE.fullmatch(item) for item in self.required_skill_keys):
            raise ValueError("Required skill keys are invalid")
        if self.minimum_skill_level is not None and not self.required_skill_keys:
            raise ValueError("Minimum skill level requires at least one skill")
        return self


def _normalize_constraints(value: dict[str, Any]) -> dict[str, Any]:
    if len(json.dumps(value, ensure_ascii=False)) > 20_000:
        raise ValueError("Executor constraints are too large")
    return ExecutorBindingConstraints.model_validate(value).model_dump(
        mode="json", exclude_none=True
    )


class ExecutorBindingDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lab_id: UUID
    capability_key: str = Field(min_length=3, max_length=255)
    capability_version: str = Field(min_length=1, max_length=64)
    executor_type: Literal["human", "platform_tool"]
    executor_ref_type: Literal["task_role", "user", "skill_pool", "platform_worker"]
    executor_ref_id: str = Field(min_length=1, max_length=255)
    mode: Literal["protocol_record", "structured_submission", "durable_job"]
    approval_policy: Literal["always_ask", "allow_read_only", "deny"] = "always_ask"
    constraints: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=0, ge=-1000, le=1000)
    enabled: bool = True
    reason: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def normalize_and_validate(self):
        self.capability_key = self.capability_key.strip()
        self.capability_version = self.capability_version.strip()
        self.executor_ref_id = self.executor_ref_id.strip()
        self.reason = self.reason.strip()
        self.constraints = _normalize_constraints(self.constraints)
        if self.executor_type == "human":
            if self.executor_ref_type not in {"task_role", "user", "skill_pool"}:
                raise ValueError(
                    "Human executors require a task role, user, or skill-pool reference"
                )
            expected_mode = (
                "protocol_record"
                if self.capability_key.startswith("protocol:")
                else "structured_submission"
            )
            if self.mode != expected_mode:
                raise ValueError(
                    f"Human execution for this capability requires {expected_mode} mode"
                )
            if self.approval_policy == "allow_read_only":
                raise ValueError("Human execution cannot use read-only auto-approval")
            required_skills = self.constraints.get("required_skill_keys") or []
            if self.executor_ref_type == "skill_pool":
                if self.executor_ref_id != "lab.skills" or not required_skills:
                    raise ValueError(
                        "Skill-pool executors require lab.skills and at least one skill"
                    )
            elif required_skills:
                raise ValueError(
                    "Skill requirements can only be used with a skill-pool executor"
                )
        elif self.executor_ref_type != "platform_worker" or self.mode != "durable_job":
            raise ValueError(
                "Platform Tool execution requires a Platform worker and durable_job mode"
            )
        return self


class ExecutorBindingCreate(ExecutorBindingDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class ExecutorBindingUpdateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    approval_policy: Literal["always_ask", "allow_read_only", "deny"]
    constraints: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=0, ge=-1000, le=1000)
    enabled: bool = True
    reason: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def normalize_and_validate(self):
        self.reason = self.reason.strip()
        self.constraints = _normalize_constraints(self.constraints)
        return self


class ExecutorBindingUpdate(ExecutorBindingUpdateDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


def _validate_updated_constraints(
    binding: ResearchExecutorBinding,
    constraints: dict[str, Any],
) -> None:
    required_skills = constraints.get("required_skill_keys") or []
    if binding.executor_ref_type == "skill_pool" and not required_skills:
        raise HTTPException(
            status_code=422,
            detail="Skill-pool executors require at least one verified skill",
        )
    if binding.executor_ref_type != "skill_pool" and required_skills:
        raise HTTPException(
            status_code=422,
            detail="Skill requirements require a skill-pool executor",
        )


async def _membership(
    db_session: DBSession,
    *,
    user: User,
    lab_id: UUID,
    manage: bool,
) -> tuple[Lab, LabUser]:
    lab = await db_session.get(Lab, lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    membership = await LabUser.find_by(
        db_session, [LabUser.lab_id == lab_id, LabUser.user_id == user.id]
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="Executor Binding access denied")
    if manage and membership.role > LabRole.MANAGER:
        raise HTTPException(
            status_code=403, detail="Only Lab Owners and Managers can manage bindings"
        )
    return lab, membership


async def _validate_capability_and_executor(
    db_session: DBSession,
    params: ExecutorBindingDraft,
) -> dict[str, Any]:
    if params.capability_key.startswith("tool:"):
        tool_key = params.capability_key.removeprefix("tool:")
        definition = research_tool_catalog().get(tool_key)
        if definition is None or definition.version != params.capability_version:
            raise HTTPException(
                status_code=422, detail="Research Tool version is unavailable"
            )
        if params.executor_type != "platform_tool":
            raise HTTPException(
                status_code=422, detail="Research Tools require platform_tool executors"
            )
        if params.executor_ref_id != tool_key:
            raise HTTPException(
                status_code=422,
                detail="Platform worker reference must match the Research Tool key",
            )
        if (
            params.approval_policy == "allow_read_only"
            and definition.risk != "read_only"
        ):
            raise HTTPException(
                status_code=422,
                detail="This Tool is not eligible for internal read-only auto-approval",
            )
        return {"kind": "tool", "name": definition.name, "risk": definition.risk}

    if params.capability_key.startswith("protocol:"):
        try:
            protocol_id = UUID(params.capability_key.removeprefix("protocol:"))
        except ValueError as error:
            raise HTTPException(
                status_code=422, detail="Invalid Protocol capability key"
            ) from error
        row = (
            await db_session.execute(
                select(Protocol, ProtocolVersion, Project)
                .join(Project, Project.id == Protocol.project_id)
                .join(ProtocolVersion, ProtocolVersion.protocol_id == Protocol.id)
                .where(
                    Protocol.id == protocol_id,
                    Protocol.deleted_at.is_(None),
                    Protocol.kind == ProtocolKind.EXPERIMENT,
                    Project.lab_id == params.lab_id,
                    Project.deleted_at.is_(None),
                    ProtocolVersion.version == params.capability_version,
                )
            )
        ).first()
        if row is None:
            raise HTTPException(
                status_code=422, detail="Protocol version is unavailable in this Lab"
            )
        protocol, _version, project = row
        if params.executor_type != "human":
            raise HTTPException(
                status_code=422, detail="Protocol capabilities require human executors"
            )
        if params.approval_policy == "allow_read_only":
            raise HTTPException(
                status_code=422,
                detail="Human Protocol execution cannot use read-only auto-approval",
            )
        if params.executor_ref_type == "task_role":
            if params.executor_ref_id != "task.owner":
                raise HTTPException(
                    status_code=422, detail="Only task.owner is a supported task role"
                )
        elif params.executor_ref_type == "user":
            try:
                executor_user_id = UUID(params.executor_ref_id)
            except ValueError as error:
                raise HTTPException(
                    status_code=422, detail="Invalid executor user reference"
                ) from error
            executor_membership = await LabUser.find_by(
                db_session,
                [
                    LabUser.lab_id == params.lab_id,
                    LabUser.user_id == executor_user_id,
                ],
            )
            if executor_membership is None:
                raise HTTPException(
                    status_code=422, detail="Executor must be a current Lab member"
                )
            access = await resolve_structured_access(
                db_session,
                executor_user_id,
                params.lab_id,
                project,
                include_legacy=True,
            )
            if not access.allows("research.run"):
                raise HTTPException(
                    status_code=422,
                    detail="Executor must be allowed to run Research in the Project",
                )
        elif params.executor_ref_id != "lab.skills":
            raise HTTPException(
                status_code=422, detail="Invalid Lab skill-pool executor reference"
            )
        return {
            "kind": "protocol",
            "name": protocol.name,
            "risk": "physical_or_structured_execution",
        }

    raise HTTPException(status_code=422, detail="Unsupported capability key")


def _create_command(params: ExecutorBindingDraft) -> dict[str, Any]:
    return {
        "operation": "create_executor_binding",
        "lab_id": str(params.lab_id),
        "capability_key": params.capability_key,
        "capability_version": params.capability_version,
        "executor_type": params.executor_type,
        "executor_ref_type": params.executor_ref_type,
        "executor_ref_id": params.executor_ref_id,
        "mode": params.mode,
        "approval_policy": params.approval_policy,
        "constraints": params.constraints,
        "priority": params.priority,
        "enabled": params.enabled,
    }


def _update_command(
    binding: ResearchExecutorBinding,
    params: ExecutorBindingUpdateDraft,
) -> dict[str, Any]:
    return {
        "operation": "update_executor_binding",
        "binding_id": str(binding.id),
        "expected_revision": params.expected_revision,
        "approval_policy": params.approval_policy,
        "constraints": params.constraints,
        "priority": params.priority,
        "enabled": params.enabled,
    }


def _binding_data(binding: ResearchExecutorBinding) -> dict[str, Any]:
    return {
        **executor_binding_snapshot(binding),
        "enabled": binding.enabled,
        "created_by_user_id": str(binding.created_by_user_id),
        "updated_by_user_id": str(binding.updated_by_user_id),
        "created_at": binding.created_at,
        "updated_at": binding.updated_at,
    }


def _audit_snapshot(binding: ResearchExecutorBinding) -> dict[str, Any]:
    return {
        **executor_binding_snapshot(binding),
        "enabled": binding.enabled,
    }


@router.get("")
async def list_executor_bindings(
    lab_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    _lab, membership = await _membership(
        db_session, user=current_user, lab_id=lab_id, manage=False
    )
    bindings = list(
        (
            await db_session.scalars(
                select(ResearchExecutorBinding)
                .where(
                    ResearchExecutorBinding.lab_id == lab_id,
                    ResearchExecutorBinding.archived_at.is_(None),
                )
                .order_by(
                    ResearchExecutorBinding.capability_key,
                    ResearchExecutorBinding.priority.desc(),
                )
            )
        ).all()
    )
    return {
        "items": [_binding_data(item) for item in bindings],
        "can_manage": membership.role <= LabRole.MANAGER,
    }


@router.get("/eligible-users")
async def list_eligible_executor_users(
    project_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    """List only current Lab members allowed to execute Research in a Project."""

    project = await db_session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Project not found")
    await require_research_capability(
        db_session,
        user=current_user,
        project=project,
        capability="research.read",
    )
    users = list(
        (
            await db_session.scalars(
                select(User)
                .join(LabUser, LabUser.user_id == User.id)
                .where(LabUser.lab_id == project.lab_id)
                .order_by(User.name, User.username, User.id)
            )
        ).all()
    )
    eligible = []
    for user in users:
        if await has_research_capability(
            db_session,
            user=user,
            project=project,
            capability="research.run",
        ):
            eligible.append(
                {"id": str(user.id), "username": user.username, "name": user.name}
            )
    return {"items": eligible}


@router.post("/preview")
async def preview_executor_binding(
    params: ExecutorBindingDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    lab, _membership_row = await _membership(
        db_session, user=current_user, lab_id=params.lab_id, manage=True
    )
    capability = await _validate_capability_and_executor(db_session, params)
    command = _create_command(params)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": {
            "lab_id": str(lab.id),
            "lab_uid": lab.uid,
            "lab_name": lab.name,
        },
        "capability": capability,
        "effects": [
            "Create a revisioned Lab Executor Binding",
            "Apply it only to future Research Environment snapshots",
            "Keep existing Research Runs pinned to their captured binding",
        ],
    }


@router.post("")
async def create_executor_binding(
    params: ExecutorBindingCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _membership(db_session, user=current_user, lab_id=params.lab_id, manage=True)
    await _validate_capability_and_executor(db_session, params)
    command = _create_command(params)
    digest = canonical_digest(command)
    if digest != params.preview_digest:
        raise HTTPException(status_code=409, detail="Executor Binding preview changed")
    existing = await ResearchExecutorBinding.find_by(
        db_session,
        [
            ResearchExecutorBinding.lab_id == params.lab_id,
            ResearchExecutorBinding.capability_key == params.capability_key,
            ResearchExecutorBinding.capability_version == params.capability_version,
            ResearchExecutorBinding.executor_type == params.executor_type,
            ResearchExecutorBinding.executor_ref_type == params.executor_ref_type,
            ResearchExecutorBinding.executor_ref_id == params.executor_ref_id,
        ],
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Executor Binding already exists")
    binding = ResearchExecutorBinding(
        lab_id=params.lab_id,
        capability_key=params.capability_key,
        capability_version=params.capability_version,
        executor_type=params.executor_type,
        executor_ref_type=params.executor_ref_type,
        executor_ref_id=params.executor_ref_id,
        mode=params.mode,
        approval_policy=params.approval_policy,
        constraints=params.constraints,
        priority=params.priority,
        enabled=params.enabled,
        created_by_user_id=current_user.id,
        updated_by_user_id=current_user.id,
    )
    db_session.add(binding)
    await db_session.flush()
    db_session.add(
        ResearchExecutorBindingAudit(
            binding_id=binding.id,
            lab_id=binding.lab_id,
            revision=binding.revision,
            action="created",
            snapshot=_audit_snapshot(binding),
            reason=params.reason,
            actor_user_id=current_user.id,
        )
    )
    await db_session.commit()
    return _binding_data(binding)


async def _binding_context(
    db_session: DBSession,
    current_user: User,
    binding_id: UUID,
    *,
    lock: bool,
) -> ResearchExecutorBinding:
    statement = select(ResearchExecutorBinding).where(
        ResearchExecutorBinding.id == binding_id,
        ResearchExecutorBinding.archived_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    binding = (await db_session.scalars(statement)).first()
    if binding is None:
        raise HTTPException(status_code=404, detail="Executor Binding not found")
    await _membership(db_session, user=current_user, lab_id=binding.lab_id, manage=True)
    return binding


@router.post("/{binding_id}/preview")
async def preview_executor_binding_update(
    binding_id: UUID,
    params: ExecutorBindingUpdateDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    binding = await _binding_context(db_session, current_user, binding_id, lock=False)
    if binding.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Executor Binding changed")
    _validate_updated_constraints(binding, params.constraints)
    command = _update_command(binding, params)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "binding": _binding_data(binding),
        "effects": [
            "Create a new binding audit revision",
            "Apply the policy only to future Research Environment snapshots",
            "Preserve existing Research Run behavior",
        ],
    }


@router.put("/{binding_id}")
async def update_executor_binding(
    binding_id: UUID,
    params: ExecutorBindingUpdate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    binding = await _binding_context(db_session, current_user, binding_id, lock=True)
    if binding.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Executor Binding changed")
    _validate_updated_constraints(binding, params.constraints)
    command = _update_command(binding, params)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="Executor Binding preview changed")
    binding.approval_policy = params.approval_policy
    binding.constraints = params.constraints
    binding.priority = params.priority
    binding.enabled = params.enabled
    binding.revision += 1
    binding.updated_by_user_id = current_user.id
    binding.updated_at = utcnow()
    db_session.add(
        ResearchExecutorBindingAudit(
            binding_id=binding.id,
            lab_id=binding.lab_id,
            revision=binding.revision,
            action="updated",
            snapshot=_audit_snapshot(binding),
            reason=params.reason,
            actor_user_id=current_user.id,
        )
    )
    await db_session.commit()
    return _binding_data(binding)
