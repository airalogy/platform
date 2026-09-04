"""Evidence-backed autonomy targets, evaluations, and pinned grant snapshots."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import ResearchAction, ResearchRun, ResearchTask
from app.models.research_execution import (
    ResearchAutonomyGrant,
    ResearchComputeJob,
    ResearchToolJob,
    ResearchWaitEvent,
)

AUTONOMY_LEVELS = ("bounded_autopilot", "autonomous_within_policy")
MINIMUM_SUPERVISED_SUCCESSES = 5
MAXIMUM_EVALUATION_SAMPLE = 10


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()


def autonomy_target(
    *,
    capability_key: str,
    capability_version: str,
    executor_type: str,
    executor_ref: dict[str, Any],
) -> dict[str, Any]:
    """Return the canonical, version-pinned boundary that may receive a grant."""

    normalized_ref = json.loads(
        json.dumps(executor_ref, ensure_ascii=False, sort_keys=True, default=str)
    )
    executor_digest = _digest(normalized_ref)
    target = {
        "schema": "airalogy.research-autonomy-target.v1",
        "capability_key": capability_key.strip(),
        "capability_version": str(capability_version).strip(),
        "executor_type": executor_type.strip(),
        "executor_ref": normalized_ref,
        "executor_digest": executor_digest,
    }
    if not target["capability_key"] or not target["capability_version"]:
        raise ValueError("Autonomy targets require a capability key and version")
    return {**target, "target_digest": _digest(target)}


def tool_autonomy_target(
    tool_key: str,
    tool_version: str,
    *,
    executor_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return autonomy_target(
        capability_key=f"tool:{tool_key}",
        capability_version=tool_version,
        executor_type="platform_tool",
        executor_ref=executor_ref or {"type": "platform_worker", "id": tool_key},
    )


def wait_autonomy_target(template_key: str) -> dict[str, Any]:
    return autonomy_target(
        capability_key=f"wait:{template_key}",
        capability_version="1",
        executor_type="external_event",
        executor_ref={"type": "platform_wait", "id": template_key},
    )


def compute_autonomy_target(revision_id: UUID | str, revision: int) -> dict[str, Any]:
    return autonomy_target(
        capability_key=f"compute:{revision_id}",
        capability_version=str(revision),
        executor_type="compute_runner",
        executor_ref={"type": "compute_environment_revision", "id": str(revision_id)},
    )


def grant_snapshot(grant: ResearchAutonomyGrant) -> dict[str, Any]:
    return {
        "schema": "airalogy.research-autonomy-grant.v1",
        "id": str(grant.id),
        "lab_id": str(grant.lab_id),
        "target": {
            "schema": "airalogy.research-autonomy-target.v1",
            "capability_key": grant.capability_key,
            "capability_version": grant.capability_version,
            "executor_type": grant.executor_type,
            "executor_ref": grant.executor_ref,
            "executor_digest": grant.executor_digest,
            "target_digest": grant.target_digest,
        },
        "revision": grant.revision,
        "enabled": grant.enabled,
        "allowed_levels": list(grant.allowed_levels or []),
        "evaluation": grant.evaluation_snapshot,
        "valid_until": grant.valid_until.isoformat(),
        "reason": grant.reason,
        "created_by_user_id": str(grant.created_by_user_id),
        "updated_by_user_id": str(grant.updated_by_user_id),
        "created_at": grant.created_at.isoformat(),
        "updated_at": grant.updated_at.isoformat(),
    }


async def current_autonomy_grant_snapshots(
    db_session: AsyncSession,
    *,
    lab_id: UUID,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    statement = select(ResearchAutonomyGrant).where(
        ResearchAutonomyGrant.lab_id == lab_id
    )
    if not include_inactive:
        statement = statement.where(ResearchAutonomyGrant.enabled.is_(True))
    rows = list(
        (
            await db_session.scalars(
                statement.order_by(
                    ResearchAutonomyGrant.capability_key,
                    ResearchAutonomyGrant.capability_version,
                )
            )
        ).all()
    )
    return [grant_snapshot(item) for item in rows]


def policy_snapshot_with_grants(
    policy_snapshot: dict[str, Any], grant_snapshots: list[dict[str, Any]]
) -> dict[str, Any]:
    """Pin exact evaluated grants and bind them into the policy digest."""

    snapshot = dict(policy_snapshot)
    snapshot["evaluated_grants"] = grant_snapshots
    digest_payload = {
        "policy": snapshot.get("policy") or {},
        "evaluated_grants": grant_snapshots,
    }
    snapshot["policy_digest"] = _digest(digest_payload)
    return snapshot


def matching_grant(
    *,
    policy_snapshot: dict[str, Any] | None,
    target: dict[str, Any] | None,
    autonomy_level: str,
    now: datetime | None = None,
) -> tuple[dict[str, Any] | None, str]:
    if not target or not target.get("target_digest"):
        return None, "The Action has no pinned autonomy target."
    try:
        canonical_target = autonomy_target(
            capability_key=str(target.get("capability_key") or ""),
            capability_version=str(target.get("capability_version") or ""),
            executor_type=str(target.get("executor_type") or ""),
            executor_ref=dict(target.get("executor_ref") or {}),
        )
    except (TypeError, ValueError):
        return None, "The Action has an invalid autonomy target."
    if canonical_target["target_digest"] != target.get("target_digest"):
        return None, "The Action autonomy target digest does not match its contract."
    current_time = now or datetime.now(UTC)
    for grant in list((policy_snapshot or {}).get("evaluated_grants") or []):
        if not grant.get("enabled"):
            continue
        if (grant.get("target") or {}).get("target_digest") != canonical_target.get(
            "target_digest"
        ):
            continue
        if autonomy_level not in list(grant.get("allowed_levels") or []):
            return None, "The evaluated grant does not allow this autonomy level."
        try:
            valid_until = datetime.fromisoformat(str(grant.get("valid_until")))
        except (TypeError, ValueError):
            return None, "The evaluated grant has an invalid expiry."
        if valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=UTC)
        if valid_until <= current_time:
            return None, "The evaluated autonomy grant has expired."
        return grant, ""
    return None, "No evaluated autonomy grant matches this capability and executor."


def _target_from_action(
    action: ResearchAction,
    *,
    tool_job: ResearchToolJob | None,
    compute_job: ResearchComputeJob | None,
    wait_event: ResearchWaitEvent | None,
) -> dict[str, Any] | None:
    pinned = dict((action.requirements or {}).get("autonomy_target") or {})
    if pinned.get("target_digest"):
        return pinned
    if tool_job is not None and action.executor_type == "platform_tool":
        binding = dict((action.requirements or {}).get("executor_binding") or {})
        executor_ref = binding.get("resolved_executor_ref") or binding.get(
            "executor_ref"
        )
        return tool_autonomy_target(
            tool_job.tool_key,
            tool_job.tool_version,
            executor_ref=executor_ref,
        )
    if compute_job is not None and action.executor_type == "compute_runner":
        return compute_autonomy_target(
            compute_job.compute_environment_revision_id,
            compute_job.compute_environment_revision,
        )
    if wait_event is not None and action.executor_type == "external_event":
        template_key = str((action.input_data or {}).get("wait_template_key") or "")
        if template_key:
            return wait_autonomy_target(template_key)
    return None


def _eligible_for_evaluation(action: ResearchAction) -> bool:
    requirements = action.requirements or {}
    if action.executor_type == "platform_tool":
        return (
            requirements.get("risk") == "read_only"
            and requirements.get("approval_policy") == "allow_read_only"
        )
    if action.executor_type == "compute_runner":
        return (
            requirements.get("risk") == "low"
            and requirements.get("network_policy") == "none"
        )
    return action.executor_type == "external_event"


def evaluate_action_sample(
    target: dict[str, Any], sampled: list[dict[str, Any]]
) -> dict[str, Any]:
    """Apply the deterministic supervised-history admission rule."""

    completed = sum(item["status"] == "completed" for item in sampled)
    failed = sum(item["status"] in {"failed", "cancelled"} for item in sampled)
    passed = completed >= MINIMUM_SUPERVISED_SUCCESSES and failed == 0
    evaluation = {
        "schema": "airalogy.research-autonomy-evaluation.v1",
        "target": target,
        # Derived from evidence, so preview/confirm is stable until history changes.
        "evaluated_at": next(
            (
                item["completed_at"]
                for item in sampled
                if item["completed_at"] is not None
            ),
            None,
        ),
        "criteria": {
            "minimum_supervised_successes": MINIMUM_SUPERVISED_SUCCESSES,
            "maximum_sample": MAXIMUM_EVALUATION_SAMPLE,
            "allowed_failures": 0,
        },
        "sample": sampled,
        "completed_count": completed,
        "failure_count": failed,
        "passed": passed,
    }
    return {**evaluation, "evaluation_digest": _digest(evaluation)}


async def evaluate_autonomy_candidates(
    db_session: AsyncSession,
    *,
    lab_id: UUID,
) -> list[dict[str, Any]]:
    """Evaluate exact targets only from real, supervised, resolved Actions."""

    actions = list(
        (
            await db_session.scalars(
                select(ResearchAction)
                .join(ResearchRun, ResearchRun.id == ResearchAction.run_id)
                .join(ResearchTask, ResearchTask.id == ResearchRun.task_id)
                .where(ResearchTask.lab_id == lab_id)
                .order_by(
                    ResearchAction.completed_at.desc().nullslast(),
                    ResearchAction.id.desc(),
                )
                .limit(500)
            )
        ).all()
    )
    action_ids = [item.id for item in actions]
    if not action_ids:
        return []
    tool_jobs = {
        item.action_id: item
        for item in (
            await db_session.scalars(
                select(ResearchToolJob).where(ResearchToolJob.action_id.in_(action_ids))
            )
        ).all()
    }
    compute_jobs = {
        item.action_id: item
        for item in (
            await db_session.scalars(
                select(ResearchComputeJob).where(
                    ResearchComputeJob.action_id.in_(action_ids)
                )
            )
        ).all()
    }
    wait_events = {
        item.action_id: item
        for item in (
            await db_session.scalars(
                select(ResearchWaitEvent).where(
                    ResearchWaitEvent.action_id.in_(action_ids)
                )
            )
        ).all()
    }
    grouped: dict[str, dict[str, Any]] = {}
    for action in actions:
        if action.status not in {"completed", "failed", "cancelled"}:
            continue
        if not _eligible_for_evaluation(action):
            continue
        # Manual Actions and Aira Actions that required approval are supervised.
        if (action.input_data or {}).get(
            "source"
        ) != "manual" and action.policy_decision != "ask":
            continue
        target = _target_from_action(
            action,
            tool_job=tool_jobs.get(action.id),
            compute_job=compute_jobs.get(action.id),
            wait_event=wait_events.get(action.id),
        )
        if target is None:
            continue
        bucket = grouped.setdefault(
            target["target_digest"], {"target": target, "actions": []}
        )
        if len(bucket["actions"]) >= MAXIMUM_EVALUATION_SAMPLE:
            continue
        bucket["actions"].append(
            {
                "action_id": str(action.id),
                "run_id": str(action.run_id),
                "status": action.status,
                "preview_digest": action.preview_digest,
                "output_digest": _digest(action.output_data or {}),
                "completed_at": (
                    action.completed_at.isoformat() if action.completed_at else None
                ),
            }
        )

    results = []
    for bucket in grouped.values():
        sampled = bucket["actions"]
        results.append(evaluate_action_sample(bucket["target"], sampled))
    return sorted(
        results,
        key=lambda item: (
            not item["passed"],
            item["target"]["capability_key"],
            item["target"]["capability_version"],
        ),
    )


async def evaluation_for_target(
    db_session: AsyncSession, *, lab_id: UUID, target_digest: str
) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in await evaluate_autonomy_candidates(db_session, lab_id=lab_id)
            if item["target"]["target_digest"] == target_digest
        ),
        None,
    )
