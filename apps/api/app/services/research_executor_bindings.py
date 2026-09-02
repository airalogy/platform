"""Versioned, fail-closed executor policy resolution for Research Environments."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import ResearchAction, ResearchRun
from app.models.research_execution import ResearchExecutorBinding


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
    if capability["kind"] == "protocol":
        return {
            "id": None,
            "revision": 1,
            "source": "platform_default",
            "capability_key": capability["key"],
            "capability_version": capability["version"],
            "executor_type": "human",
            "executor_ref": {"type": "task_role", "id": "task.owner"},
            "resolved_executor_ref": {"type": "user", "id": str(owner_user_id)},
            "mode": "protocol_record",
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
