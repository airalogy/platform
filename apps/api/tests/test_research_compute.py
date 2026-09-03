from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.main import app
from app.models.research import ResearchTaskComputeEnvironment
from app.models.research_execution import (
    ResearchComputeEnvironment,
    ResearchComputeEnvironmentRevision,
)
from app.routers.research_compute import ComputeEnvironmentDraft
from app.services.access_control import ROLE_CAPABILITIES
from app.services.research_compute import compute_environment_snapshot


def compile_table(model) -> str:
    return str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))


def valid_environment(**updates):
    payload = {
        "lab_id": uuid4(),
        "environment_key": "python.analysis",
        "name": "Python analysis",
        "image_ref": ("registry.example.test/airalogy/python@sha256:" + "a" * 64),
        "runtime_version": "python-3.13",
        "allowed_languages": ["python"],
        "input_schema": {
            "type": "object",
            "properties": {"data_asset_ids": {"type": "array"}},
            "required": ["data_asset_ids"],
            "additionalProperties": False,
        },
        "result_schema": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        },
    }
    payload.update(updates)
    return ComputeEnvironmentDraft(**payload)


def test_compute_models_are_versioned_and_task_pinned():
    environment_ddl = compile_table(ResearchComputeEnvironment)
    revision_ddl = compile_table(ResearchComputeEnvironmentRevision)
    task_link_ddl = compile_table(ResearchTaskComputeEnvironment)

    assert "uq_research_compute_environment_key" in environment_ddl
    assert "uq_research_compute_environment_revision" in revision_ddl
    assert "ck_research_compute_environment_network_policy" in revision_ddl
    assert "ck_research_compute_environment_cost_pair" in revision_ddl
    assert "compute_environment_revision_id" in task_link_ddl
    assert "uq_research_task_compute_environment" in task_link_ddl


def test_compute_migration_follows_service_jobs():
    migration = import_module("migrations.versions.0030_research_compute_environments")

    assert migration.down_revision == "0029_research_service_jobs"
    assert migration.TABLE_NAMES == (
        "research_compute_environments",
        "research_compute_environment_revisions",
        "research_task_compute_environments",
    )


def test_compute_contract_requires_immutable_image_and_bounded_network():
    draft = valid_environment(estimated_cost_per_hour=Decimal("0.50"), currency="usd")

    assert draft.currency == "USD"
    assert draft.resource_limits.timeout_seconds == 3600
    with pytest.raises(ValidationError, match="immutable OCI sha256 digest"):
        valid_environment(image_ref="registry.example.test/python:" + "latest" * 12)
    with pytest.raises(ValidationError, match="immutable OCI sha256 digest"):
        valid_environment(image_ref="file:///tmp/python@sha256:" + "a" * 64)
    with pytest.raises(ValidationError, match="cannot allow egress"):
        valid_environment(allowed_egress_hosts=["api.example.test:443"])
    with pytest.raises(ValidationError, match="requires at least one host"):
        valid_environment(network_policy="egress_allowlist")
    with pytest.raises(ValidationError, match="Invalid egress port"):
        valid_environment(
            network_policy="egress_allowlist",
            allowed_egress_hosts=["api.example.test:65536"],
        )
    with pytest.raises(ValidationError, match="provided together"):
        valid_environment(estimated_cost_per_hour=Decimal("0.50"))


def test_compute_snapshot_preserves_exact_execution_contract():
    environment = SimpleNamespace(
        id=uuid4(),
        lab_id=uuid4(),
        environment_key="python.analysis",
        archived_at=None,
    )
    revision = SimpleNamespace(
        id=uuid4(),
        revision=3,
        name="Python analysis",
        description="Validated analysis environment",
        runner_protocol_version="airalogy.compute-runner.v1",
        image_ref="registry.example.test/python@sha256:" + "a" * 64,
        runtime_version="python-3.13",
        allowed_languages=["python"],
        resource_limits={"cpu_millis": 2000, "memory_mb": 4096},
        network_policy="egress_allowlist",
        allowed_egress_hosts=["api.example.test:443"],
        input_schema={"type": "object"},
        result_schema={"type": "object"},
        software_manifest={"python": "3.13.6"},
        estimated_cost_per_hour=Decimal("0.5000"),
        currency="USD",
        risk="medium",
        enabled=True,
        reason="Quarterly image refresh",
    )

    snapshot = compute_environment_snapshot(environment, revision)

    assert snapshot["source_revision_id"] == str(revision.id)
    assert snapshot["executor_types"] == ["compute_runner"]
    assert snapshot["metadata"]["image_ref"].endswith("a" * 64)
    assert snapshot["metadata"]["network_policy"] == "egress_allowlist"
    assert snapshot["metadata"]["estimated_cost_per_hour"] == "0.5"


def test_compute_capabilities_are_explicit_and_grantable():
    assert "research.compute.use" in ROLE_CAPABILITIES["contributor"]
    assert "research.compute.manage" not in ROLE_CAPABILITIES["contributor"]
    assert ROLE_CAPABILITIES["research_compute_manager"] == {
        "research.read",
        "research.compute.use",
        "research.compute.manage",
    }


def test_compute_catalog_routes_are_registered():
    paths = {route.path for route in app.routes}

    assert "/research-compute-environments" in paths
    assert "/research-compute-environments/preview" in paths
    assert "/research-compute-environments/{environment_id}/revisions/preview" in paths
