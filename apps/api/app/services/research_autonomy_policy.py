"""Versioned Lab policy for bounded automatic Research Action execution."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_execution import ResearchAutonomyPolicy


class AutonomyRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auto_approve_read_only_tools: bool = True
    auto_create_wait_events: bool = False
    auto_approve_isolated_compute: bool = False


class AutomaticComputeLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_estimated_cost: Decimal | None = Field(default=None, ge=0, le=1_000_000)
    currency: str | None = None
    max_timeout_seconds: int = Field(default=3600, ge=1, le=86_400)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("Currency must be a three-letter ISO-style code")
        return normalized

    @model_validator(mode="after")
    def require_cost_pair(self):
        if (self.max_estimated_cost is None) != (self.currency is None):
            raise ValueError("Automatic Compute cost and currency must be set together")
        return self


class ResearchAutonomyPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: str = Field(
        default="airalogy.research-autonomy-policy.v1", alias="schema"
    )
    bounded_autopilot: AutonomyRule = Field(default_factory=AutonomyRule)
    autonomous_within_policy: AutonomyRule = Field(default_factory=AutonomyRule)
    automatic_compute_limits: AutomaticComputeLimits = Field(
        default_factory=AutomaticComputeLimits
    )

    @field_validator("schema_version")
    @classmethod
    def require_schema(cls, value: str) -> str:
        if value != "airalogy.research-autonomy-policy.v1":
            raise ValueError("Unsupported Research autonomy policy schema")
        return value

    @model_validator(mode="after")
    def require_compute_ceiling(self):
        enabled = (
            self.bounded_autopilot.auto_approve_isolated_compute
            or self.autonomous_within_policy.auto_approve_isolated_compute
        )
        if enabled and self.automatic_compute_limits.max_estimated_cost is None:
            raise ValueError(
                "Automatic Compute requires an explicit cost ceiling and currency"
            )
        return self


DEFAULT_RESEARCH_AUTONOMY_POLICY = ResearchAutonomyPolicyConfig()


def normalize_policy(value: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(value, ensure_ascii=False)
    if len(encoded) > 20_000:
        raise ValueError("Research autonomy policy is too large")
    return ResearchAutonomyPolicyConfig.model_validate(value).model_dump(
        mode="json", exclude_none=True, by_alias=True
    )


def policy_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def autonomy_policy_snapshot(
    policy: ResearchAutonomyPolicy | None,
) -> dict[str, Any]:
    config = normalize_policy(
        policy.policy
        if policy is not None
        else DEFAULT_RESEARCH_AUTONOMY_POLICY.model_dump(
            mode="json", exclude_none=True, by_alias=True
        )
    )
    return {
        "schema": "airalogy.research-autonomy-policy-snapshot.v1",
        "id": str(policy.id) if policy is not None else None,
        "revision": policy.revision if policy is not None else 0,
        "source": "lab_policy" if policy is not None else "platform_default",
        "policy": config,
        "policy_digest": policy_digest(config),
        "updated_at": policy.updated_at.isoformat() if policy is not None else None,
    }


async def current_autonomy_policy_snapshot(
    db_session: AsyncSession,
    *,
    lab_id,
    lock: bool = False,
) -> tuple[ResearchAutonomyPolicy | None, dict[str, Any]]:
    statement = select(ResearchAutonomyPolicy).where(
        ResearchAutonomyPolicy.lab_id == lab_id
    )
    if lock:
        statement = statement.with_for_update()
    policy = await db_session.scalar(statement)
    return policy, autonomy_policy_snapshot(policy)


def _rule_for_level(
    policy_snapshot: dict[str, Any] | None,
    autonomy_level: str,
) -> tuple[ResearchAutonomyPolicyConfig, AutonomyRule | None]:
    raw = dict((policy_snapshot or {}).get("policy") or {})
    config = ResearchAutonomyPolicyConfig.model_validate(
        raw
        or DEFAULT_RESEARCH_AUTONOMY_POLICY.model_dump(
            mode="json", exclude_none=True, by_alias=True
        )
    )
    if autonomy_level == "bounded_autopilot":
        return config, config.bounded_autopilot
    if autonomy_level == "autonomous_within_policy":
        return config, config.autonomous_within_policy
    return config, None


def evaluate_automatic_action(
    *,
    policy_snapshot: dict[str, Any] | None,
    autonomy_level: str,
    executor_type: str,
    requirements: dict[str, Any],
) -> tuple[str, str]:
    """Evaluate only auto-execution. Explicit denial/manual confirmation live above it."""

    config, rule = _rule_for_level(policy_snapshot, autonomy_level)
    if rule is None:
        return "ask", "Assisted Research requires confirmation for every Aira Action."

    from app.services.research_autonomy_evaluations import matching_grant

    autonomy_target = dict(requirements.get("autonomy_target") or {})
    if autonomy_target.get("executor_type") != executor_type:
        return "ask", "The autonomy target does not match the Action executor type."
    _grant, grant_reason = matching_grant(
        policy_snapshot=policy_snapshot,
        target=autonomy_target,
        autonomy_level=autonomy_level,
    )
    if _grant is None:
        return "ask", grant_reason

    if executor_type == "platform_tool":
        if (
            requirements.get("risk") == "read_only"
            and requirements.get("approval_policy") == "allow_read_only"
            and rule.auto_approve_read_only_tools
        ):
            return (
                "allow",
                "The pinned Lab policy, Executor Binding, and evaluated grant allow this internal read-only Tool.",
            )
        return "ask", "This Tool is outside the pinned automatic-execution policy."

    if executor_type == "external_event":
        if rule.auto_create_wait_events:
            return (
                "allow",
                "The pinned Lab policy and evaluated grant allow opening a passive external-event wait.",
            )
        return "ask", "The pinned Lab policy requires confirmation before waiting."

    if executor_type == "compute_runner":
        if not rule.auto_approve_isolated_compute:
            return "ask", "Automatic Compute is disabled for this autonomy level."
        if requirements.get("risk") != "low":
            return "ask", "Only low-risk Compute is eligible for automatic execution."
        if requirements.get("network_policy") != "none":
            return "ask", "Automatic Compute must run without network access."
        limits = config.automatic_compute_limits
        timeout_seconds = int(
            dict(requirements.get("resource_limits") or {}).get(
                "timeout_seconds", limits.max_timeout_seconds + 1
            )
        )
        if timeout_seconds > limits.max_timeout_seconds:
            return "ask", "Compute timeout exceeds the pinned automatic limit."
        estimated_cost = requirements.get("estimated_cost")
        currency = requirements.get("currency")
        if (
            estimated_cost is None
            or currency != limits.currency
            or limits.max_estimated_cost is None
            or Decimal(str(estimated_cost)) > limits.max_estimated_cost
        ):
            return (
                "ask",
                "Compute cost is missing or exceeds the pinned automatic limit.",
            )
        return (
            "allow",
            "The pinned Lab policy and evaluated grant allow this isolated low-risk Compute within its cost and time ceilings.",
        )

    if executor_type == "human":
        return (
            "ask",
            "Aira-proposed human execution requires approval before assignment.",
        )
    return "ask", "This executor type is outside the pinned automatic-execution policy."
