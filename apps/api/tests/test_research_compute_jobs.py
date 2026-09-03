import asyncio
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.main import app
from app.models.research import ResearchAction, ResearchActionKind, ResearchRunStatus
from app.models.research_execution import (
    ResearchComputeJob,
    ResearchComputeJobInput,
    ResearchComputeJobOutput,
    ResearchComputeJobStatus,
)
from app.routers.research_compute_jobs import (
    ComputeActionDraft,
    ComputeOutputDraft,
    ComputeUsage,
    RunnerComplete,
    _completed_output_contract,
    _manifest_output_contract,
    _registered_output_results,
)
from app.services import knowledge, research_compute_jobs, research_runtime
from app.services.research_compute_contracts import MAX_SOURCE_BYTES
from app.services.research_compute_jobs import (
    compute_actual_cost,
    compute_estimated_cost,
    compute_job_snapshot,
    compute_lease_token_digest,
    compute_source_digest,
    generate_compute_lease_token,
    sign_compute_envelope,
)
from app.services.research_planner import AiraActionProposal


def compile_table(model) -> str:
    return str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))


def valid_action(**updates):
    payload = {
        "compute_environment_revision_id": uuid4(),
        "language": "python",
        "source_code": "print('hello')\n",
        "input_payload": {"question": "count rows"},
        "input_assets": [{"data_asset_version_id": uuid4(), "mount_name": "input.csv"}],
        "idempotency_key": "compute-job-001",
    }
    payload.update(updates)
    return ComputeActionDraft(**payload)


def test_compute_job_models_pin_execution_and_asset_versions():
    job_ddl = compile_table(ResearchComputeJob)
    input_ddl = compile_table(ResearchComputeJobInput)
    output_ddl = compile_table(ResearchComputeJobOutput)

    assert "uq_research_compute_job_action" in job_ddl
    assert "ck_research_compute_job_status" in job_ddl
    assert "ck_research_compute_job_source_digest" in job_ddl
    assert "compute_environment_revision_id" in job_ddl
    assert "data_asset_version_id" in input_ddl
    assert "uq_research_compute_job_input_asset_version" in input_ddl
    assert "uq_research_compute_job_output_mount_name" in output_ddl
    assert "data_asset_version_id" in output_ddl
    assert "ck_research_compute_job_output_max_bytes" in output_ddl


def test_compute_job_migration_follows_runner_governance():
    migration = import_module("migrations.versions.0032_research_compute_jobs")

    assert migration.down_revision == "0031_research_compute_runners"
    assert migration.TABLE_NAMES == (
        "research_compute_jobs",
        "research_compute_job_inputs",
    )

    output_migration = import_module(
        "migrations.versions.0033_research_compute_outputs"
    )
    assert output_migration.down_revision == "0032_research_compute_jobs"
    assert output_migration.TABLE_NAMES == ("research_compute_job_outputs",)


def test_compute_action_is_bounded_and_uses_safe_mount_names():
    action = valid_action()

    assert action.language == "python"
    with pytest.raises(ValidationError, match="mount name"):
        valid_action(
            input_assets=[{"data_asset_version_id": uuid4(), "mount_name": "../secret"}]
        )
    with pytest.raises(ValidationError, match="at most 200000"):
        valid_action(source_code="x" * (MAX_SOURCE_BYTES + 1))
    with pytest.raises(ValidationError, match="cannot be blank"):
        valid_action(source_code="   ")


def test_compute_usage_is_bounded():
    usage = ComputeUsage(wall_seconds=12, max_memory_mb=256, output_bytes=1024)

    assert usage.wall_seconds == 12
    with pytest.raises(ValidationError):
        ComputeUsage(wall_seconds=86_401)
    with pytest.raises(ValidationError):
        ComputeUsage(wall_seconds=1, cpu_seconds=float("nan"))


def test_compute_output_contract_is_typed_bounded_and_unique():
    output = ComputeOutputDraft(
        mount_name="analysis.csv",
        asset_name="Analysis table",
        kind="table",
        media_type="text/csv",
        max_bytes=4096,
    )

    assert output.required is True
    with pytest.raises(ValidationError, match="mount name"):
        ComputeOutputDraft(
            mount_name="../analysis.csv",
            asset_name="Analysis table",
            media_type="text/csv",
            max_bytes=4096,
        )
    with pytest.raises(ValidationError, match="media type"):
        ComputeOutputDraft(
            mount_name="analysis.csv",
            asset_name="Analysis table",
            media_type="not a media type",
            max_bytes=4096,
        )
    with pytest.raises(ValidationError, match="less than or equal"):
        ComputeOutputDraft(
            mount_name="analysis.bin",
            asset_name="Oversized result",
            media_type="application/octet-stream",
            max_bytes=2_147_483_648,
        )
    with pytest.raises(ValidationError, match="must be unique"):
        valid_action(output_files=[output, output])
    with pytest.raises(ValidationError, match="must be unique"):
        RunnerComplete(
            result={},
            usage={"wall_seconds": 1},
            outputs=[
                {
                    "output_id": uuid4(),
                    "checksum_sha256": "a" * 64,
                    "byte_size": 10,
                }
            ]
            * 2,
        )


def test_compute_output_receipts_bind_registered_assets_exactly():
    output_id = uuid4()
    completion = RunnerComplete(
        result={"rows": 4},
        usage={"wall_seconds": 1, "output_bytes": 128},
        outputs=[
            {
                "output_id": output_id,
                "checksum_sha256": "a" * 64,
                "byte_size": 128,
            }
        ],
    )
    manifest = [
        {
            "id": str(output_id),
            "mount_name": "analysis.csv",
            "asset_name": "Analysis table",
            "kind": "table",
            "media_type": "text/csv",
            "status": "registered",
            "checksum_sha256": "a" * 64,
            "byte_size": 128,
            "research_file_id": str(uuid4()),
            "data_asset_id": str(uuid4()),
            "data_asset_version_id": str(uuid4()),
        }
    ]

    assert _completed_output_contract(completion.outputs) == _manifest_output_contract(
        manifest
    )
    result = _registered_output_results(manifest)
    assert result[0]["output_id"] == str(output_id)
    assert result[0]["data_asset_version_id"] == manifest[0]["data_asset_version_id"]


def test_compute_cost_is_deterministic_and_capped_by_timeout():
    revision = SimpleNamespace(
        estimated_cost_per_hour=Decimal("3.60"),
        resource_limits={"timeout_seconds": 100},
    )
    job = SimpleNamespace(
        environment_snapshot={"metadata": {"estimated_cost_per_hour": "3.6"}},
        timeout_seconds=100,
    )

    assert compute_estimated_cost(revision) == Decimal("0.10")
    assert compute_actual_cost(job, 40) == Decimal("0.04")
    assert compute_actual_cost(job, 200) == Decimal("0.10")


def test_compute_tokens_and_signed_envelopes_are_bound():
    token = generate_compute_lease_token()
    envelope = {"schema": "airalogy.compute-job.v1", "job_id": str(uuid4())}
    digest = "a" * 64

    assert token.startswith("aicl_")
    assert len(compute_lease_token_digest(token)) == 64
    assert sign_compute_envelope(envelope, digest) != sign_compute_envelope(
        {**envelope, "job_id": str(uuid4())}, digest
    )


def test_compute_snapshot_never_serializes_source_or_lease_secret():
    job = ResearchComputeJob(
        id=uuid4(),
        action_id=uuid4(),
        compute_environment_id=uuid4(),
        compute_environment_revision_id=uuid4(),
        compute_environment_revision=2,
        language="python",
        source_code="print('private')",
        source_sha256=compute_source_digest("print('private')"),
        input_payload={},
        input_schema={"type": "object"},
        result_schema={"type": "object"},
        environment_snapshot={},
        resource_limits={"timeout_seconds": 60},
        timeout_seconds=60,
        status=ResearchComputeJobStatus.QUEUED.value,
        lease_token_digest="b" * 64,
        created_by_user_id=uuid4(),
    )

    snapshot = compute_job_snapshot(job)

    assert "source_code" not in snapshot
    assert "lease_token_digest" not in snapshot
    assert snapshot["source_bytes"] == len(job.source_code)
    review_snapshot = compute_job_snapshot(job, include_source=True)
    assert review_snapshot["source_code"] == "print('private')"
    assert "lease_token_digest" not in review_snapshot


def test_compute_action_and_runtime_routes_are_registered():
    paths = {route.path for route in app.routes}

    assert "/research-tasks/{task_id}/compute-options" in paths
    assert "/research-tasks/{task_id}/compute-actions/preview" in paths
    assert "/research-tasks/{task_id}/compute-actions" in paths
    assert "/research-compute-jobs" in paths
    assert "/research-compute-jobs/{job_id}/cancel/preview" in paths
    assert "/compute-runner/v1/jobs/lease" in paths
    assert "/compute-runner/v1/jobs/{job_id}/inputs/{input_id}" in paths
    assert "/compute-runner/v1/jobs/{job_id}/outputs/{output_id}" in paths
    assert "/compute-runner/v1/jobs/{job_id}/complete" in paths


def test_compute_job_has_typed_orchestration_states():
    assert ResearchActionKind.COMPUTE_JOB.value == "compute_job"
    assert ResearchRunStatus.WAITING_FOR_COMPUTE.value == "waiting_for_compute"
    assert ResearchComputeJobStatus.AWAITING_APPROVAL.value == "awaiting_approval"
    assert ResearchComputeJobStatus.CANCEL_REQUESTED.value == "cancel_requested"


def test_aira_compute_proposal_materializes_as_reviewable_typed_job(monkeypatch):
    class FakeSession:
        def __init__(self):
            self.added = []

        def add(self, value):
            if getattr(value, "id", None) is None:
                value.id = uuid4()
            self.added.append(value)

        async def flush(self):
            return None

        async def scalar(self, _statement):
            return 0

        async def get(self, model, _value):
            if model.__name__ == "Project":
                return SimpleNamespace(id=project_id, lab_id=lab_id)
            if model.__name__ == "User":
                return SimpleNamespace(id=requester_id)
            return None

    lab_id = uuid4()
    project_id = uuid4()
    requester_id = uuid4()
    environment_id = uuid4()
    environment_revision_id = uuid4()
    task = SimpleNamespace(
        id=uuid4(),
        lab_id=lab_id,
        project_id=project_id,
        owner_user_id=requester_id,
        autonomy_level="assistive",
        budget_limit=None,
        revision=2,
    )
    run = SimpleNamespace(
        id=uuid4(),
        requested_by_user_id=requester_id,
        environment_snapshot={"compute": []},
        plan_version=3,
    )
    task_environment = SimpleNamespace(
        snapshot={"name": "Pinned Python", "revision": 4}
    )
    environment = SimpleNamespace(id=environment_id)
    revision = SimpleNamespace(
        id=environment_revision_id,
        revision=4,
        name="Pinned Python",
        risk="medium",
        image_ref="registry.example/python@sha256:" + ("a" * 64),
        allowed_languages=["python"],
        input_schema={"type": "object", "additionalProperties": False},
        result_schema={"type": "object"},
        resource_limits={
            "cpu_millis": 1000,
            "memory_mb": 512,
            "timeout_seconds": 300,
            "max_output_bytes": 100_000,
        },
        network_policy="none",
        allowed_egress_hosts=[],
        estimated_cost_per_hour=None,
        currency=None,
    )
    proposal = AiraActionProposal.model_validate(
        {
            "decision": "compute",
            "thought": "Generate a reproducible summary",
            "compute_request": {
                "compute_environment_revision_id": str(environment_revision_id),
                "language": "python",
                "source_code": (
                    "from pathlib import Path\n"
                    "Path('/airalogy/output/files/summary.csv').write_text('x,y\\n1,2\\n')\n"
                ),
                "output_files": [
                    {
                        "mount_name": "summary.csv",
                        "asset_name": "Summary table",
                        "kind": "table",
                        "media_type": "text/csv",
                        "max_bytes": 4096,
                    }
                ],
                "title": "Summarize measurements",
            },
        }
    )
    session = FakeSession()

    monkeypatch.setattr(ResearchAction, "find_by", AsyncMock(return_value=None))

    async def create_plan(_db, *, run, **_kwargs):
        run.plan_version += 1

    monkeypatch.setattr(research_runtime, "create_plan_version", create_plan)
    monkeypatch.setattr(
        research_runtime, "has_research_capability", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        research_compute_jobs,
        "pinned_compute_environment",
        AsyncMock(return_value=(task_environment, environment, revision)),
    )
    monkeypatch.setattr(
        research_compute_jobs, "exact_compute_inputs", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        research_compute_jobs, "eligible_runner_count", AsyncMock(return_value=1)
    )
    quota = AsyncMock(return_value=None)
    monkeypatch.setattr(knowledge, "assert_research_file_upload_quota", quota)
    approval = SimpleNamespace(id=uuid4())
    request_approval = AsyncMock(return_value=approval)
    emit_event = AsyncMock(return_value=None)
    monkeypatch.setattr(research_runtime, "request_action_approval", request_approval)
    monkeypatch.setattr(research_runtime, "emit_research_event", emit_event)

    action = asyncio.run(
        research_runtime._materialize_aira_action(
            session,
            task=task,
            run=run,
            proposal=proposal,
            step_index=5,
        )
    )

    job = next(item for item in session.added if isinstance(item, ResearchComputeJob))
    output = next(
        item for item in session.added if isinstance(item, ResearchComputeJobOutput)
    )
    assert action.kind == ResearchActionKind.COMPUTE_JOB.value
    assert action.policy_decision == "ask"
    assert action.input_data["source"] == "aira"
    assert action.input_data["source_sha256"] == job.source_sha256
    assert job.source_code == proposal.compute_request.source_code
    assert job.compute_environment_revision_id == environment_revision_id
    assert output.mount_name == "summary.csv"
    assert job.output_manifest[0]["status"] == "declared"
    quota.assert_awaited_once_with(session, requester_id, 4096, incoming_count=1)
    request_approval.assert_awaited_once()
    assert "compute_job.requested" in [
        call.kwargs["kind"] for call in emit_event.await_args_list
    ]
