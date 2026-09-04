from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.main import app
from app.models.research_execution import (
    ResearchAutonomyPolicy,
    ResearchAutonomyPolicyAudit,
)
from app.services.research_autonomy_policy import (
    ResearchAutonomyPolicyConfig,
    autonomy_policy_snapshot,
    evaluate_automatic_action,
)
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable


def compile_table(model) -> str:
    return str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))


def test_policy_models_are_lab_scoped_revisioned_and_audited():
    policy_ddl = compile_table(ResearchAutonomyPolicy)
    audit_ddl = compile_table(ResearchAutonomyPolicyAudit)

    assert "uq_research_autonomy_policies_lab" in policy_ddl
    assert "ck_research_autonomy_policies_revision" in policy_ddl
    assert "uq_research_autonomy_policy_audits_revision" in audit_ddl


def test_policy_migration_follows_dependency_guard():
    migration = import_module("migrations.versions.0040_research_autonomy_policy")

    assert migration.down_revision == "0039_research_action_dependency_guard"
    assert migration.TABLE_NAMES == (
        "research_autonomy_policies",
        "research_autonomy_policy_audits",
    )


def test_default_policy_is_conservative_and_snapshot_is_reproducible():
    snapshot = autonomy_policy_snapshot(None)

    assert snapshot["revision"] == 0
    assert snapshot["source"] == "platform_default"
    assert len(snapshot["policy_digest"]) == 64
    assert snapshot["policy"]["bounded_autopilot"]["auto_approve_read_only_tools"]
    assert not snapshot["policy"]["autonomous_within_policy"][
        "auto_approve_isolated_compute"
    ]


def test_automatic_compute_requires_an_explicit_cost_ceiling():
    with pytest.raises(ValidationError, match="cost ceiling"):
        ResearchAutonomyPolicyConfig.model_validate(
            {"autonomous_within_policy": {"auto_approve_isolated_compute": True}}
        )
    with pytest.raises(ValidationError, match="set together"):
        ResearchAutonomyPolicyConfig.model_validate(
            {"automatic_compute_limits": {"max_estimated_cost": "2.00"}}
        )


def test_assisted_never_auto_executes_and_physical_work_remains_gated():
    snapshot = autonomy_policy_snapshot(None)
    tool_requirements = {
        "risk": "read_only",
        "approval_policy": "allow_read_only",
    }

    assert (
        evaluate_automatic_action(
            policy_snapshot=snapshot,
            autonomy_level="assisted",
            executor_type="platform_tool",
            requirements=tool_requirements,
        )[0]
        == "ask"
    )
    assert (
        evaluate_automatic_action(
            policy_snapshot=snapshot,
            autonomy_level="autonomous_within_policy",
            executor_type="instrument_gateway",
            requirements={"risk": "low"},
        )[0]
        == "ask"
    )


def test_read_only_tool_needs_both_policy_and_executor_binding():
    snapshot = autonomy_policy_snapshot(None)

    assert (
        evaluate_automatic_action(
            policy_snapshot=snapshot,
            autonomy_level="bounded_autopilot",
            executor_type="platform_tool",
            requirements={"risk": "read_only", "approval_policy": "allow_read_only"},
        )[0]
        == "allow"
    )
    assert (
        evaluate_automatic_action(
            policy_snapshot=snapshot,
            autonomy_level="bounded_autopilot",
            executor_type="platform_tool",
            requirements={"risk": "read_only", "approval_policy": "always_ask"},
        )[0]
        == "ask"
    )


def test_isolated_compute_enforces_risk_network_cost_currency_and_timeout():
    config = ResearchAutonomyPolicyConfig.model_validate(
        {
            "autonomous_within_policy": {"auto_approve_isolated_compute": True},
            "automatic_compute_limits": {
                "max_estimated_cost": Decimal("2.50"),
                "currency": "usd",
                "max_timeout_seconds": 600,
            },
        }
    )
    row = SimpleNamespace(
        id=uuid4(),
        revision=4,
        policy=config.model_dump(mode="json", exclude_none=True, by_alias=True),
        updated_at=SimpleNamespace(isoformat=lambda: "2026-09-04T00:00:00+00:00"),
    )
    snapshot = autonomy_policy_snapshot(row)
    requirements = {
        "risk": "low",
        "network_policy": "none",
        "resource_limits": {"timeout_seconds": 300},
        "estimated_cost": "2.00",
        "currency": "USD",
    }

    assert (
        evaluate_automatic_action(
            policy_snapshot=snapshot,
            autonomy_level="autonomous_within_policy",
            executor_type="compute_runner",
            requirements=requirements,
        )[0]
        == "allow"
    )
    assert (
        evaluate_automatic_action(
            policy_snapshot=snapshot,
            autonomy_level="autonomous_within_policy",
            executor_type="compute_runner",
            requirements={**requirements, "network_policy": "egress_allowlist"},
        )[0]
        == "ask"
    )
    assert (
        evaluate_automatic_action(
            policy_snapshot=snapshot,
            autonomy_level="autonomous_within_policy",
            executor_type="compute_runner",
            requirements={**requirements, "estimated_cost": "2.51"},
        )[0]
        == "ask"
    )
    assert (
        evaluate_automatic_action(
            policy_snapshot=snapshot,
            autonomy_level="autonomous_within_policy",
            executor_type="compute_runner",
            requirements={
                **requirements,
                "resource_limits": {"timeout_seconds": 601},
            },
        )[0]
        == "ask"
    )


def test_policy_routes_are_publicly_declared():
    paths = {route.path for route in app.routes}

    assert "/research-autonomy-policies" in paths
    assert "/research-autonomy-policies/preview" in paths
    assert "/research-autonomy-policies/audits" in paths
