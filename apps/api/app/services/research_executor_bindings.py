"""Versioned, fail-closed executor policy resolution for Research Environments."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from fractions import Fraction
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.research import (
    HumanWorkItemStatus,
    ResearchAction,
    ResearchHumanWorkItem,
    ResearchRun,
)
from app.models.research_execution import (
    ResearchExecutorBinding,
    ResearchHumanExecutorProfile,
)
from app.models.user import User

ACTIVE_HUMAN_WORK_STATUSES = {
    HumanWorkItemStatus.OPEN.value,
    HumanWorkItemStatus.IN_PROGRESS.value,
    HumanWorkItemStatus.SUBMITTED.value,
    HumanWorkItemStatus.CHANGES_REQUESTED.value,
}


def executor_binding_snapshot(binding: ResearchExecutorBinding) -> dict[str, Any]:
    return {
        "id": str(binding.id),
        "revision": binding.revision,
        "source": "lab_policy",
        "capability_key": binding.capability_key,
        "capability_version": binding.capability_version,
        "executor_type": binding.executor_type,
        "executor_ref": {
            "type": binding.executor_ref_type,
            "id": binding.executor_ref_id,
        },
        "mode": binding.mode,
        "approval_policy": binding.approval_policy,
        "constraints": binding.constraints or {},
        "priority": binding.priority,
    }


def derived_executor_binding(
    *,
    capability: dict[str, Any],
    owner_user_id: UUID,
) -> dict[str, Any]:
    if capability["kind"] in {"protocol", "human"}:
        return {
            "id": None,
            "revision": 1,
            "source": "platform_default",
            "capability_key": capability["key"],
            "capability_version": capability["version"],
            "executor_type": "human",
            "executor_ref": {"type": "task_role", "id": "task.owner"},
            "resolved_executor_ref": {"type": "user", "id": str(owner_user_id)},
            "mode": (
                "protocol_record"
                if capability["kind"] == "protocol"
                else "structured_submission"
            ),
            "approval_policy": "always_ask",
            "constraints": {},
            "priority": 0,
        }
    if capability["kind"] == "tool":
        tool_key = str((capability.get("metadata") or {}).get("tool_key") or "")
        return {
            "id": None,
            "revision": 1,
            "source": "platform_default",
            "capability_key": capability["key"],
            "capability_version": capability["version"],
            "executor_type": "platform_tool",
            "executor_ref": {"type": "platform_worker", "id": tool_key},
            "mode": "durable_job",
            "approval_policy": "always_ask",
            "constraints": {},
            "priority": 0,
        }
    raise ValueError("Resource requirements cannot be used as executor bindings")


def resolve_human_executor_ref(
    binding: dict[str, Any],
    *,
    owner_user_id: UUID,
) -> dict[str, Any]:
    """Resolve a human binding to the exact user captured by the environment."""

    if binding.get("executor_type") != "human":
        return binding
    executor_ref = dict(binding.get("executor_ref") or {})
    if executor_ref.get("type") == "task_role":
        if executor_ref.get("id") != "task.owner":
            raise ValueError("Unsupported human executor task role")
        executor_user_id = owner_user_id
    elif executor_ref.get("type") == "user":
        try:
            executor_user_id = UUID(str(executor_ref.get("id") or ""))
        except ValueError as error:
            raise ValueError("Invalid human executor user reference") from error
    else:
        raise ValueError("Human Executor Binding did not reference a user")
    binding["resolved_executor_ref"] = {
        "type": "user",
        "id": str(executor_user_id),
    }
    return binding


def _as_utc(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    return (
        parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    )


def profile_is_available(
    profile: ResearchHumanExecutorProfile,
    *,
    now: datetime | None = None,
) -> bool:
    now = now or datetime.now(UTC)
    if profile.availability != "available":
        return False
    available_from = _as_utc(profile.available_from)
    available_until = _as_utc(profile.available_until)
    return not (
        (available_from is not None and now < available_from)
        or (available_until is not None and now >= available_until)
    )


def matching_profile_skills(
    profile: ResearchHumanExecutorProfile,
    *,
    required_skill_keys: list[str],
    minimum_skill_level: int,
    now: datetime | None = None,
) -> list[dict[str, Any]] | None:
    now = now or datetime.now(UTC)
    skill_index: dict[str, dict[str, Any]] = {}
    for item in list(profile.skills or []):
        try:
            level = int(item.get("level") or 0)
            expires_at = _as_utc(item.get("expires_at"))
        except (TypeError, ValueError):
            continue
        if (
            item.get("verified") is True
            and level >= minimum_skill_level
            and (expires_at is None or expires_at > now)
        ):
            skill_index[str(item.get("key") or "").lower()] = item
    if any(key not in skill_index for key in required_skill_keys):
        return None
    return [skill_index[key] for key in required_skill_keys]


async def human_executor_workloads(
    db_session: AsyncSession,
    *,
    user_ids: list[UUID] | None = None,
) -> dict[UUID, int]:
    statement = (
        select(
            ResearchHumanWorkItem.assignee_user_id,
            func.count(ResearchHumanWorkItem.id),
        )
        .where(ResearchHumanWorkItem.status.in_(ACTIVE_HUMAN_WORK_STATUSES))
        .group_by(ResearchHumanWorkItem.assignee_user_id)
    )
    if user_ids is not None:
        if not user_ids:
            return {}
        statement = statement.where(
            ResearchHumanWorkItem.assignee_user_id.in_(user_ids)
        )
    return {
        user_id: int(count)
        for user_id, count in (await db_session.execute(statement)).all()
    }


def _profile_resolution_snapshot(
    profile: ResearchHumanExecutorProfile,
    *,
    matched_skills: list[dict[str, Any]],
    workload: int,
) -> dict[str, Any]:
    snapshot = {
        "profile_id": str(profile.id),
        "profile_revision": profile.revision,
        "user_id": str(profile.user_id),
        "availability": profile.availability,
        "available_from": (
            profile.available_from.isoformat() if profile.available_from else None
        ),
        "available_until": (
            profile.available_until.isoformat() if profile.available_until else None
        ),
        "max_concurrent_items": profile.max_concurrent_items,
        "workload_at_resolution": workload,
        "matched_skills": matched_skills,
    }
    snapshot["profile_digest"] = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return snapshot


async def resolve_skill_pool_executor(
    db_session: AsyncSession,
    *,
    binding: dict[str, Any],
    lab_id: UUID,
    project_id: UUID,
) -> dict[str, Any]:
    constraints = dict(binding.get("constraints") or {})
    required_skill_keys = [
        str(item).lower() for item in constraints.get("required_skill_keys") or []
    ]
    minimum_skill_level = int(constraints.get("minimum_skill_level") or 1)
    if not required_skill_keys:
        raise ValueError("Skill-pool Executor Binding requires at least one skill")
    project = await db_session.get(Project, project_id)
    if project is None or project.lab_id != lab_id or project.deleted_at is not None:
        raise ValueError("Skill-pool Executor Binding Project is unavailable")
    rows = list(
        (
            await db_session.execute(
                select(ResearchHumanExecutorProfile, User)
                .join(User, User.id == ResearchHumanExecutorProfile.user_id)
                .where(ResearchHumanExecutorProfile.lab_id == lab_id)
            )
        ).all()
    )
    workloads = await human_executor_workloads(
        db_session, user_ids=[profile.user_id for profile, _user in rows]
    )
    from app.services.research_runtime import has_research_capability

    now = datetime.now(UTC)
    candidates: list[
        tuple[Fraction, int, str, ResearchHumanExecutorProfile, list[dict[str, Any]]]
    ] = []
    for profile, user in rows:
        if not profile_is_available(profile, now=now):
            continue
        matched_skills = matching_profile_skills(
            profile,
            required_skill_keys=required_skill_keys,
            minimum_skill_level=minimum_skill_level,
            now=now,
        )
        if matched_skills is None:
            continue
        workload = workloads.get(profile.user_id, 0)
        if workload >= profile.max_concurrent_items:
            continue
        if not await has_research_capability(
            db_session,
            user=user,
            project=project,
            capability="research.run",
        ):
            continue
        candidates.append(
            (
                Fraction(workload, profile.max_concurrent_items),
                workload,
                str(profile.user_id),
                profile,
                matched_skills,
            )
        )
    if not candidates:
        raise ValueError(
            "No available human executor satisfies the pinned skill requirements"
        )
    _load_ratio, workload, _user_id, profile, matched_skills = min(candidates)
    binding["resolved_executor_ref"] = {
        "type": "user",
        "id": str(profile.user_id),
    }
    binding["executor_resolution"] = {
        "type": "skill_pool",
        "required_skill_keys": required_skill_keys,
        "minimum_skill_level": minimum_skill_level,
        **_profile_resolution_snapshot(
            profile,
            matched_skills=matched_skills,
            workload=workload,
        ),
    }
    return binding


async def validate_pinned_skill_pool_executor(
    db_session: AsyncSession,
    *,
    binding: dict[str, Any],
    lab_id: UUID,
    assignee_user_id: UUID,
) -> None:
    executor_ref = dict(binding.get("executor_ref") or {})
    if executor_ref.get("type") != "skill_pool":
        return
    resolution = dict(binding.get("executor_resolution") or {})
    try:
        profile_id = UUID(str(resolution.get("profile_id") or ""))
    except ValueError as error:
        raise ValueError("Pinned skill-pool resolution is invalid") from error
    profile = (
        await db_session.scalars(
            select(ResearchHumanExecutorProfile)
            .where(ResearchHumanExecutorProfile.id == profile_id)
            .with_for_update()
        )
    ).first()
    if (
        profile is None
        or profile.lab_id != lab_id
        or profile.user_id != assignee_user_id
    ):
        raise ValueError("Pinned skill-pool executor profile is unavailable")
    now = datetime.now(UTC)
    required_skill_keys = [
        str(item).lower() for item in resolution.get("required_skill_keys") or []
    ]
    if not required_skill_keys:
        raise ValueError("Pinned skill-pool resolution has no skill requirements")
    minimum_skill_level = int(resolution.get("minimum_skill_level") or 1)
    if (
        not profile_is_available(profile, now=now)
        or matching_profile_skills(
            profile,
            required_skill_keys=required_skill_keys,
            minimum_skill_level=minimum_skill_level,
            now=now,
        )
        is None
    ):
        raise ValueError(
            "Pinned skill-pool executor is no longer available or qualified"
        )
    workloads = await human_executor_workloads(db_session, user_ids=[assignee_user_id])
    if workloads.get(assignee_user_id, 0) >= profile.max_concurrent_items:
        raise ValueError("Pinned skill-pool executor has reached current work capacity")


async def resolve_executor_binding(
    db_session: AsyncSession,
    *,
    lab_id: UUID,
    capability: dict[str, Any],
    owner_user_id: UUID,
    project_id: UUID,
    autonomy_level: str,
) -> dict[str, Any]:
    bindings = list(
        (
            await db_session.scalars(
                select(ResearchExecutorBinding)
                .where(
                    ResearchExecutorBinding.lab_id == lab_id,
                    ResearchExecutorBinding.capability_key == capability["key"],
                    ResearchExecutorBinding.capability_version == capability["version"],
                    ResearchExecutorBinding.enabled.is_(True),
                    ResearchExecutorBinding.archived_at.is_(None),
                )
                .order_by(
                    ResearchExecutorBinding.priority.desc(),
                    ResearchExecutorBinding.updated_at.desc(),
                    ResearchExecutorBinding.id,
                )
            )
        ).all()
    )
    for binding in bindings:
        snapshot = executor_binding_snapshot(binding)
        try:
            enforce_environment_binding_scope(
                snapshot,
                project_id=project_id,
                autonomy_level=autonomy_level,
            )
        except ValueError:
            continue
        if snapshot.get("executor_ref", {}).get("type") == "skill_pool":
            return await resolve_skill_pool_executor(
                db_session,
                binding=snapshot,
                lab_id=lab_id,
                project_id=project_id,
            )
        return resolve_human_executor_ref(snapshot, owner_user_id=owner_user_id)
    return derived_executor_binding(
        capability=capability,
        owner_user_id=owner_user_id,
    )


def environment_executor_binding(
    environment_snapshot: dict[str, Any],
    capability_key: str,
    capability_version: str,
    *,
    legacy_capability: dict[str, Any] | None = None,
    owner_user_id: UUID | None = None,
) -> dict[str, Any]:
    binding = next(
        (
            item
            for item in list(environment_snapshot.get("executor_bindings") or [])
            if item.get("capability_key") == capability_key
            and str(item.get("capability_version") or "") == capability_version
        ),
        None,
    )
    if binding is None:
        if (
            "executor_bindings" not in environment_snapshot
            and legacy_capability is not None
            and owner_user_id is not None
        ):
            return derived_executor_binding(
                capability=legacy_capability,
                owner_user_id=owner_user_id,
            )
        raise ValueError("Executor Binding is missing from the Research Environment")
    if binding.get("approval_policy") == "deny":
        raise ValueError("This capability is denied by the pinned Lab policy")
    return binding


def enforce_environment_binding_scope(
    binding: dict[str, Any],
    *,
    project_id: UUID,
    autonomy_level: str,
) -> None:
    constraints = dict(binding.get("constraints") or {})
    allowed_projects = {
        str(item) for item in constraints.get("allowed_project_ids") or []
    }
    if allowed_projects and str(project_id) not in allowed_projects:
        raise ValueError("Executor Binding does not allow this Project")
    allowed_autonomy = set(constraints.get("allowed_autonomy_levels") or [])
    if allowed_autonomy and autonomy_level not in allowed_autonomy:
        raise ValueError("Executor Binding does not allow this autonomy level")


async def enforce_environment_binding_action_limit(
    db_session: AsyncSession,
    *,
    run: ResearchRun,
    binding: dict[str, Any],
) -> None:
    maximum = (binding.get("constraints") or {}).get("max_actions_per_run")
    if maximum is None:
        return
    actions = list(
        (
            await db_session.scalars(
                select(ResearchAction).where(ResearchAction.run_id == run.id)
            )
        ).all()
    )
    capability_key = binding["capability_key"]
    count = sum(
        1
        for action in actions
        if (action.requirements or {}).get("executor_binding", {}).get("capability_key")
        == capability_key
    )
    if count >= int(maximum):
        raise ValueError(
            f"Executor Binding limits {capability_key} to {maximum} Action(s) per Run"
        )
