from datetime import UTC, datetime, timedelta
from importlib import import_module
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.main import app
from app.models.research_execution import (
    ResearchComputeRunner,
    ResearchComputeRunnerAudit,
    ResearchComputeRunnerEnvironment,
)
from app.routers.research_compute_runners import ComputeRunnerReport
from app.services.research_compute_runners import (
    compute_runner_snapshot,
    compute_runner_token_digest,
    generate_compute_runner_token,
    runner_report_is_execution_ready,
)


def compile_table(model) -> str:
    return str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))


def test_compute_runner_models_keep_credentials_private_and_bind_exact_revisions():
    runner_ddl = compile_table(ResearchComputeRunner)
    binding_ddl = compile_table(ResearchComputeRunnerEnvironment)
    audit_ddl = compile_table(ResearchComputeRunnerAudit)

    assert "token_digest VARCHAR(64) NOT NULL" in runner_ddl
    assert "ck_research_compute_runner_concurrency" in runner_ddl
    assert "compute_environment_revision_id" in binding_ddl
    assert "uq_research_compute_runner_environment" in binding_ddl
    assert "snapshot JSON" in audit_ddl
    assert "uq_research_compute_runner_audit_revision" in audit_ddl

    runner = ResearchComputeRunner(
        id=uuid4(),
        lab_id=uuid4(),
        name="Isolated Runner",
        description="Local container execution plane",
        runner_protocol_version="airalogy.compute-runner.v1",
        max_concurrent_jobs=2,
        token_digest="a" * 64,
        token_hint="12345678",
        enabled=True,
        revision=1,
        last_report={},
        created_by_user_id=uuid4(),
        updated_by_user_id=uuid4(),
    )

    assert "token_digest" not in runner.as_dict()
    assert "token_digest" not in compute_runner_snapshot(runner)


def test_compute_runner_migration_follows_compute_environments():
    migration = import_module("migrations.versions.0031_research_compute_runners")

    assert migration.down_revision == "0030_research_compute_environments"
    assert migration.TABLE_NAMES == (
        "research_compute_runners",
        "research_compute_runner_environments",
        "research_compute_runner_audits",
    )


def test_compute_runner_credentials_are_high_entropy_and_digest_only():
    first = generate_compute_runner_token()
    second = generate_compute_runner_token()

    assert first.startswith("aicr_")
    assert len(first) > 40
    assert first != second
    assert len(compute_runner_token_digest(first)) == 64
    assert first not in compute_runner_token_digest(first)


def test_compute_runner_report_requires_bounded_declared_runtime():
    report = ComputeRunnerReport(
        protocol_version="airalogy.compute-runner.v1",
        runner_version="0.1.0",
        executor_backend="podman",
        active_jobs=1,
        available_slots=1,
        security={
            "non_root": True,
            "read_only_root_filesystem": True,
            "network_isolation": True,
            "no_host_mounts": True,
        },
    )

    assert report.executor_backend == "podman"
    with pytest.raises(ValidationError, match="Input should be"):
        ComputeRunnerReport(
            protocol_version="airalogy.compute-runner.v1",
            runner_version="0.1.0",
            executor_backend="shell",
            active_jobs=0,
            available_slots=1,
            security={
                "non_root": True,
                "read_only_root_filesystem": True,
                "network_isolation": True,
                "no_host_mounts": True,
            },
        )


def test_compute_runner_is_not_ready_without_every_isolation_control():
    runner = SimpleNamespace(
        runner_protocol_version="airalogy.compute-runner.v1",
        last_seen_at=datetime.now(UTC),
        last_report={
            "protocol_version": "airalogy.compute-runner.v1",
            "security": {
                "non_root": True,
                "read_only_root_filesystem": True,
                "network_isolation": True,
                "no_host_mounts": True,
            },
        },
    )
    assert runner_report_is_execution_ready(runner) is True

    runner.last_report["security"]["no_host_mounts"] = False
    assert runner_report_is_execution_ready(runner) is False

    runner.last_report["security"]["no_host_mounts"] = True
    runner.last_seen_at = datetime.now(UTC) - timedelta(minutes=4)
    assert runner_report_is_execution_ready(runner) is False


def test_compute_runner_management_and_runtime_routes_are_registered():
    paths = {route.path for route in app.routes}

    assert "/research-compute-runners" in paths
    assert "/research-compute-runners/preview" in paths
    assert "/research-compute-runners/items/{runner_id}/rotate" in paths
    assert "/research-compute-runners/bindings" in paths
    assert "/research-compute-runners/bindings/{binding_id}/archive" in paths
    assert "/compute-runner/v1/status" in paths
    assert "/research-compute-environments/revisions" in paths
