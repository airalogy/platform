"""Private Compute approval and pinning against real migrated PostgreSQL.

No permission, SQL, snapshot, quota or execution-contract code is mocked. These
tests do not claim a Runner or execute user code; they exercise its actual gate.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import delete, func, select

from app.config import config
from app.models.analysis import AnalysisPreview, AnalysisRun
from app.models.analysis_compute import AnalysisCompute, AnalysisComputeEvent
from app.models.lab import LabUser
from app.models.project import ProjectRole, ProjectUser
from app.models.record import Record
from app.models.research import ResearchAction, ResearchTask
from app.models.research_asset import DataAsset
from app.models.research_execution import (
    ResearchComputeEnvironment,
    ResearchComputeEnvironmentRevision,
    ResearchComputeJob,
    ResearchComputeJobInput,
    ResearchComputeJobOutput,
    ResearchComputeRunner,
    ResearchComputeRunnerEnvironment,
)
from app.routers.analyses import AnalysisConfirmRequest, cancel_record_analysis
from app.routers.analysis_compute import (
    cancel_analysis_compute,
    confirm_analysis_compute,
    decide_analysis_compute,
    download_analysis_compute_output,
    get_analysis_compute,
    get_analysis_compute_approval,
    list_analysis_compute_approvals,
    preview_analysis_compute,
)
from app.services.analysis_compute import (
    analysis_compute_input_bytes,
    analysis_runner_counts,
    authorize_compute_execution,
    compute_options,
    confirm_compute,
    owned_compute,
    preview_compute,
)
from app.services.analysis_compute_contracts import (
    ANALYSIS_JOB_SCHEMA,
    COMPUTE_ENGINE_VERSION,
    SOURCE_FILENAME,
    AnalysisComputeCancel,
    AnalysisComputeDecision,
    AnalysisComputeDraft,
)
from app.services.analysis_compute_runtime import finish_analysis_failure
from app.services.analysis_engine import canonical_digest
from app.services.record_analyses import AnalysisSelection
from tests.test_record_analysis_postgres import add_record, database, seed_analysis

pytestmark = pytest.mark.skipif(
    not os.environ.get("RESOURCE_TEST_DATABASE_URL"),
    reason="RESOURCE_TEST_DATABASE_URL is required for private Compute guarantees",
)


@pytest.fixture(autouse=True)
def deterministic_flat_mode(monkeypatch):
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")
    monkeypatch.setattr(config, "AI_ENABLED", False)


async def seed_compute(sessions, scope, *, supports_analysis=True):
    async with sessions() as db:
        environment = ResearchComputeEnvironment(
            lab_id=scope.lab.id,
            environment_key=f"synthetic-{uuid4().hex}",
            created_by_user_id=scope.owner.id,
        )
        db.add(environment)
        await db.flush()
        revision = ResearchComputeEnvironmentRevision(
            compute_environment_id=environment.id,
            revision=1,
            name="Synthetic private Compute",
            image_ref="synthetic.example.test/python@sha256:" + "a" * 64,
            runtime_version="synthetic-python-3.13",
            allowed_languages=["python"],
            resource_limits={
                "cpu_millis": 1000,
                "gpu_count": 0,
                "memory_mb": 256,
                "timeout_seconds": 60,
                "max_output_bytes": 65_536,
            },
            network_policy="none",
            input_schema={
                "type": "object",
                "properties": {"scale": {"type": "number"}},
                "required": ["scale"],
                "additionalProperties": False,
            },
            result_schema={
                "type": "object",
                "properties": {"mean": {"type": "number"}},
                "required": ["mean"],
                "additionalProperties": False,
            },
            estimated_cost_per_hour=Decimal("6"),
            currency="USD",
            created_by_user_id=scope.owner.id,
        )
        runner = ResearchComputeRunner(
            lab_id=scope.lab.id,
            name=f"synthetic-{uuid4().hex}",
            token_digest=uuid4().hex + uuid4().hex,
            token_hint="synthetic",
            last_seen_at=datetime.now(UTC),
            last_report={
                "protocol_version": "airalogy.compute-runner.v1",
                "job_schemas": [ANALYSIS_JOB_SCHEMA]
                if supports_analysis
                else ["airalogy.compute-job.v1"],
                "security": {
                    "non_root": True,
                    "read_only_root_filesystem": True,
                    "network_isolation": True,
                    "no_host_mounts": True,
                },
            },
            created_by_user_id=scope.owner.id,
            updated_by_user_id=scope.owner.id,
        )
        db.add_all([revision, runner])
        await db.flush()
        binding = ResearchComputeRunnerEnvironment(
            runner_id=runner.id,
            lab_id=scope.lab.id,
            compute_environment_id=environment.id,
            compute_environment_revision_id=revision.id,
            created_by_user_id=scope.owner.id,
        )
        db.add(binding)
        await db.commit()
        return SimpleNamespace(
            environment=environment, revision=revision, runner=runner, binding=binding
        )


def compute_draft(scope, compute, **changes):
    return AnalysisComputeDraft.model_validate(
        {
            "protocol_id": scope.protocol.id,
            "question": "Compute synthetic descriptive measurements",
            "approver_user_id": scope.owner.id,
            "recipe": {
                "environment_revision_id": compute.revision.id,
                "language": "python",
                "source_code": "import json\nprint(json.dumps({'mean': 0}))\n",
                "parameters": {"scale": 1},
                "output_files": [
                    {
                        "mount_name": "summary.json",
                        "asset_name": "Synthetic private summary",
                        "media_type": "application/json",
                        "max_bytes": 4096,
                    }
                ],
            },
            "max_cost": "0.10",
            "budget_currency": "USD",
            **changes,
        }
    )


async def preview(sessions, scope, params, *, user=None):
    async with sessions() as db:
        result = await preview_compute(db, params, user or scope.analyst)
        await db.commit()
        return result


async def confirm(sessions, scope, draft, *, user=None, key=None):
    async with sessions() as db:
        run = await confirm_compute(
            db,
            user or scope.analyst,
            preview_id=draft.id,
            preview_digest=draft.preview_digest,
            key=key or f"synthetic-{uuid4().hex}",
        )
        await db.commit()
        return run


async def count_runs_and_jobs(sessions, scope):
    async with sessions() as db:
        runs = await db.scalar(
            select(func.count())
            .select_from(AnalysisRun)
            .where(AnalysisRun.project_id == scope.project.id)
        )
        jobs = await db.scalar(
            select(func.count())
            .select_from(ResearchComputeJob)
            .join(AnalysisRun, AnalysisRun.id == ResearchComputeJob.analysis_run_id)
            .where(AnalysisRun.project_id == scope.project.id)
        )
        return runs, jobs


async def approved_fixture(sessions, scope, run):
    """Seed a prior persisted approval, then exercise the real execution gate.

    Decision endpoint behavior is tested separately; no approval API is replaced.
    """
    async with sessions() as db:
        details = await db.get(AnalysisCompute, run.id)
        details.approval_state = "approved"
        details.approval_revision += 1
        details.decided_by_user_id = scope.owner.id
        details.decided_at = datetime.now(UTC)
        details.decision_reason = "Synthetic prior approval"
        await db.commit()


def test_compute_preview_is_nonexecuting_and_confirm_is_idempotent_with_ai_off():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            source = await add_record(sessions, scope, 987654)
            compute = await seed_compute(sessions, scope)
            draft = await preview(sessions, scope, compute_draft(scope, compute))
            assert await count_runs_and_jobs(sessions, scope) == (0, 0)
            assert draft.summary["visibility"] == "private"
            assert draft.summary["compute"]["approval_required"] is True
            assert draft.summary["compute"]["ready_runner_count"] == 1
            assert draft.summary["compute"]["input"]["filename"] == SOURCE_FILENAME
            assert "987654" not in str(draft.summary)
            first = await confirm(sessions, scope, draft, key="synthetic-compute-one")
            same_key = await confirm(
                sessions, scope, draft, key="synthetic-compute-one"
            )
            another_key = await confirm(
                sessions, scope, draft, key="synthetic-compute-two"
            )
            assert first.id == same_key.id == another_key.id
            assert first.engine_version == COMPUTE_ENGINE_VERSION
            assert first.status == "pending" and first.result is None
            assert await count_runs_and_jobs(sessions, scope) == (1, 1)
            async with sessions() as db:
                run, details, job = await owned_compute(db, first.id, scope.analyst)
                assert details.approval_state == "pending"
                assert job.status == "awaiting_approval" and job.action_id is None
                assert job.runner_id is None and job.lease_token_digest is None
                assert (
                    hashlib.sha256(analysis_compute_input_bytes(run)).hexdigest()
                    == draft.summary["compute"]["input"]["sha256"]
                )
                assert canonical_digest(run.source_snapshot) == run.source_digest
                assert run.source_snapshot["records"][0]["record_id"] == str(source.id)
                source_input = await db.scalar(
                    select(ResearchComputeJobInput).where(
                        ResearchComputeJobInput.compute_job_id == job.id
                    )
                )
                assert source_input.analysis_run_id == run.id
                assert (
                    source_input.data_asset_id is None
                    and source_input.data_asset_version_id is None
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisComputeEvent)
                        .where(AnalysisComputeEvent.analysis_run_id == run.id)
                    )
                    == 1
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(ResearchTask)
                        .where(ResearchTask.project_id == scope.project.id)
                    )
                    == 0
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(ResearchAction)
                        .where(ResearchAction.id == job.action_id)
                    )
                    == 0
                )

    asyncio.run(exercise())


def test_concurrent_compute_confirmation_creates_one_job_and_one_request_event():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            compute = await seed_compute(sessions, scope)
            draft = await preview(sessions, scope, compute_draft(scope, compute))
            first, second = await asyncio.wait_for(
                asyncio.gather(
                    confirm(sessions, scope, draft, key="synthetic-concurrent"),
                    confirm(sessions, scope, draft, key="synthetic-concurrent"),
                ),
                timeout=10,
            )
            assert first.id == second.id
            assert await count_runs_and_jobs(sessions, scope) == (1, 1)
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisComputeEvent)
                        .where(AnalysisComputeEvent.analysis_run_id == first.id)
                    )
                    == 1
                )

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "change", ["expired", "new_record", "schema", "environment", "preview_recipe"]
)
def test_compute_confirmation_rejects_stale_preview_without_leaving_a_job(change):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            compute = await seed_compute(sessions, scope)
            draft = await preview(sessions, scope, compute_draft(scope, compute))
            if change == "new_record":
                await add_record(sessions, scope, 10, number=2)
            else:
                async with sessions() as db:
                    if change == "expired":
                        row = await db.get(AnalysisPreview, draft.id)
                        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                    elif change == "schema":
                        from app.models.protocol_version import ProtocolVersion

                        row = await db.get(ProtocolVersion, scope.version.id)
                        schema = copy.deepcopy(row.json_schema)
                        schema["vars"]["properties"]["value"]["unit"] = "g/L"
                        row.json_schema = schema
                    elif change == "environment":
                        row = await db.get(
                            ResearchComputeEnvironmentRevision, compute.revision.id
                        )
                        row.runtime_version = "synthetic-changed-runtime"
                    else:
                        row = await db.get(AnalysisPreview, draft.id)
                        row.recipe = {**row.recipe, "parameters": {"scale": 100}}
                    await db.commit()
            with pytest.raises(HTTPException) as stale:
                await confirm(sessions, scope, draft)
            assert stale.value.status_code == 409
            assert await count_runs_and_jobs(sessions, scope) == (0, 0)

    asyncio.run(exercise())


def test_selected_approver_can_review_but_cannot_read_or_publish_private_analysis():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions, public=True)
            source = await add_record(sessions, scope, 2, author=scope.analyst)
            compute = await seed_compute(sessions, scope)
            draft = await preview(sessions, scope, compute_draft(scope, compute))
            run = await confirm(sessions, scope, draft)
            async with sessions() as db:
                for user in (scope.owner, scope.recorder, scope.outsider):
                    with pytest.raises(HTTPException) as private:
                        await owned_compute(db, run.id, user)
                    assert private.value.status_code == 404
                _, _, job = await owned_compute(
                    db, run.id, scope.owner, approval_access=True
                )
                with pytest.raises(HTTPException) as approval_required:
                    await authorize_compute_execution(db, job)
                assert approval_required.value.status_code == 409
                for user in (scope.recorder, scope.outsider):
                    with pytest.raises(HTTPException) as not_selected:
                        await owned_compute(db, run.id, user, approval_access=True)
                    assert not_selected.value.status_code == 404
            await approved_fixture(sessions, scope, run)
            async with sessions() as db:
                _, _, job = await owned_compute(db, run.id, scope.analyst)
                authorized, _ = await authorize_compute_execution(db, job)
                assert authorized.id == run.id and authorized.result is None
                original = await db.get(Record, (source.id, source.version))
                assert original.data == source.data and original.hash == source.hash
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(DataAsset)
                        .where(DataAsset.project_id == scope.project.id)
                    )
                    == 0
                )
                with pytest.raises(HTTPException) as still_private:
                    await owned_compute(db, run.id, scope.owner)
                assert still_private.value.status_code == 404

    asyncio.run(exercise())


@pytest.mark.parametrize("revoke", ["owner", "approver", "source"])
def test_compute_execution_rechecks_live_owner_approver_and_source_authority(revoke):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            source = await add_record(sessions, scope, 2, author=scope.analyst)
            compute = await seed_compute(sessions, scope)
            run = await confirm(
                sessions,
                scope,
                await preview(sessions, scope, compute_draft(scope, compute)),
            )
            await approved_fixture(sessions, scope, run)
            async with sessions() as db:
                if revoke == "owner":
                    await db.execute(
                        delete(ProjectUser).where(
                            ProjectUser.project_id == scope.project.id,
                            ProjectUser.user_id == scope.analyst.id,
                        )
                    )
                elif revoke == "approver":
                    await db.execute(
                        delete(LabUser).where(
                            LabUser.lab_id == scope.lab.id,
                            LabUser.user_id == scope.owner.id,
                        )
                    )
                else:
                    row = await db.get(Record, (source.id, source.version))
                    row.deleted_at = datetime.now(UTC).replace(tzinfo=None)
                await db.commit()
            async with sessions() as db:
                job = await db.scalar(
                    select(ResearchComputeJob).where(
                        ResearchComputeJob.analysis_run_id == run.id
                    )
                )
                with pytest.raises(HTTPException) as denied:
                    await authorize_compute_execution(db, job)
                assert denied.value.status_code == 403
                assert job.runner_id is None and job.status == "awaiting_approval"

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "change",
    [
        "code",
        "job_environment",
        "parameters",
        "input_mount",
        "output",
        "approval_digest",
        "live_environment",
        "result_schema",
    ],
)
def test_compute_execution_rejects_changed_pinned_contract_before_dispatch(change):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            compute = await seed_compute(sessions, scope)
            run = await confirm(
                sessions,
                scope,
                await preview(sessions, scope, compute_draft(scope, compute)),
            )
            await approved_fixture(sessions, scope, run)
            async with sessions() as db:
                _, details, job = await owned_compute(db, run.id, scope.analyst)
                await authorize_compute_execution(db, job)
                if change == "code":
                    job.source_code += "print('changed')\n"
                elif change == "job_environment":
                    job.environment_snapshot = {
                        **job.environment_snapshot,
                        "name": "Changed environment",
                    }
                elif change == "parameters":
                    job.input_payload = {"scale": 100}
                elif change == "input_mount":
                    row = await db.scalar(
                        select(ResearchComputeJobInput).where(
                            ResearchComputeJobInput.compute_job_id == job.id
                        )
                    )
                    row.mount_name = "different.json"
                elif change == "output":
                    row = await db.scalar(
                        select(ResearchComputeJobOutput).where(
                            ResearchComputeJobOutput.compute_job_id == job.id
                        )
                    )
                    row.max_bytes += 1
                elif change == "approval_digest":
                    details.contract_digest = "0" * 64
                elif change == "live_environment":
                    row = await db.get(
                        ResearchComputeEnvironmentRevision, compute.revision.id
                    )
                    row.image_ref = "synthetic.example.test/python@sha256:" + "b" * 64
                else:
                    job.result_schema = {"type": "object"}
                await db.commit()
            async with sessions() as db:
                job = await db.scalar(
                    select(ResearchComputeJob).where(
                        ResearchComputeJob.analysis_run_id == run.id
                    )
                )
                with pytest.raises(HTTPException) as changed:
                    await authorize_compute_execution(db, job)
                assert changed.value.status_code == 409
                assert job.runner_id is None and job.lease_token_digest is None

    asyncio.run(exercise())


def test_private_analysis_requires_runner_schema_and_exact_environment_authorization():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            compute = await seed_compute(sessions, scope, supports_analysis=False)
            async with sessions() as db:
                assert await analysis_runner_counts(db, compute.revision.id) == (0, 0)
                options = await compute_options(
                    db, scope.analyst, scope.protocol.id, AnalysisSelection()
                )
                assert options["environments"][0]["authorized_runner_count"] == 0
            with pytest.raises(HTTPException) as unsupported:
                await preview(sessions, scope, compute_draft(scope, compute))
            assert unsupported.value.status_code == 409
            async with sessions() as db:
                runner = await db.get(ResearchComputeRunner, compute.runner.id)
                runner.last_report = {
                    **runner.last_report,
                    "job_schemas": [ANALYSIS_JOB_SCHEMA],
                }
                await db.commit()
            draft = await preview(sessions, scope, compute_draft(scope, compute))
            assert draft.summary["compute"]["authorized_runner_count"] == 1
            async with sessions() as db:
                binding = await db.get(
                    ResearchComputeRunnerEnvironment, compute.binding.id
                )
                binding.archived_at = datetime.now(UTC)
                await db.commit()
            with pytest.raises(HTTPException) as unauthorized:
                await confirm(sessions, scope, draft)
            assert unauthorized.value.status_code == 409
            assert await count_runs_and_jobs(sessions, scope) == (0, 0)

    asyncio.run(exercise())


@pytest.mark.parametrize("limit", ["count", "bytes"])
def test_compute_output_reservation_uses_real_private_file_quota(monkeypatch, limit):
    monkeypatch.setattr(
        config,
        "KNOWLEDGE_USER_FILE_COUNT_LIMIT"
        if limit == "count"
        else "KNOWLEDGE_USER_STORAGE_QUOTA_BYTES",
        0,
    )

    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            compute = await seed_compute(sessions, scope)
            with pytest.raises(HTTPException) as quota:
                await preview(sessions, scope, compute_draft(scope, compute))
            assert quota.value.status_code == 413
            assert await count_runs_and_jobs(sessions, scope) == (0, 0)

    asyncio.run(exercise())


async def routed_compute(sessions, scope, compute):
    """Use actual route functions and their commit boundaries, without ASGI mocks."""
    async with sessions() as db:
        response = Response()
        draft = await preview_analysis_compute(
            compute_draft(scope, compute), db, scope.analyst, response
        )
        assert response.headers["Cache-Control"] == "private, no-store"
    assert await count_runs_and_jobs(sessions, scope) == (0, 0)
    params = AnalysisConfirmRequest(
        preview_id=draft["id"],
        preview_digest=draft["preview_digest"],
        client_idempotency_key=f"synthetic-{uuid4().hex}",
    )
    async with sessions() as db:
        response = Response()
        run = await confirm_analysis_compute(params, db, scope.analyst, response)
        assert response.headers["Cache-Control"] == "private, no-store"
    async with sessions() as db:
        repeated = await confirm_analysis_compute(params, db, scope.analyst, Response())
        assert repeated["id"] == run["id"]
        details = await get_analysis_compute(run["id"], db, scope.analyst, Response())
    assert await count_runs_and_jobs(sessions, scope) == (1, 1)
    return run["id"], details


def decision_params(detail, *, decision="approved", reason="Reviewed synthetic code"):
    return AnalysisComputeDecision(
        decision=decision,
        expected_revision=detail["approval"]["revision"],
        contract_digest=detail["approval"]["contract_digest"],
        reason=reason,
    )


@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_compute_routes_approval_is_redacted_idempotent_and_terminal(decision):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions, public=True)
            await add_record(sessions, scope, 987654)
            compute = await seed_compute(sessions, scope)
            analysis_id, detail = await routed_compute(sessions, scope, compute)
            async with sessions() as db:
                job = await db.get(ResearchComputeJob, detail["job"]["id"])
                # Persist private runtime details: approval views must not expose them.
                job.result = {"private": 987654}
                job.usage = {"private": 987654}
                job.error = "Private runtime detail 987654"
                db.add(
                    AnalysisComputeEvent(
                        analysis_run_id=analysis_id,
                        kind="synthetic.private_evidence",
                        payload={"private": 987654},
                        idempotency_key="synthetic-evidence",
                    )
                )
                await db.commit()
            async with sessions() as db:
                response = Response()
                approval = await get_analysis_compute_approval(
                    analysis_id, db, scope.owner, response
                )
                assert response.headers["Cache-Control"] == "private, no-store"
                assert "source_snapshot" not in approval["run"]
                assert "result" not in approval["run"]
                assert approval["job"]["result"] == {}
                assert approval["job"]["usage"] == {}
                assert approval["job"]["output_manifest"] == []
                assert approval["job"]["error"] is None
                assert "987654" not in str(approval)
                assert approval["approval"]["can_approve"] is True
                assert approval["contract"]["source"]["code"]
                inbox = await list_analysis_compute_approvals(
                    db, scope.owner, Response(), scope.project.id, limit=30, offset=0
                )
                assert [item["analysis_id"] for item in inbox["items"]] == [analysis_id]
            params = decision_params(detail, decision=decision)
            async with sessions() as db:
                result = await decide_analysis_compute(
                    analysis_id, params, db, scope.owner, Response()
                )
                assert result["approval"]["state"] == decision
                assert result["approval"]["revision"] == 2
                assert result["approval"]["can_approve"] is False
                assert result["job"]["status"] == (
                    "queued" if decision == "approved" else "cancelled"
                )
                assert "987654" not in str(result)
            async with sessions() as db:
                repeated = await decide_analysis_compute(
                    analysis_id, params, db, scope.owner, Response()
                )
                assert repeated["approval"]["revision"] == 2
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisComputeEvent)
                        .where(
                            AnalysisComputeEvent.analysis_run_id == analysis_id,
                            AnalysisComputeEvent.kind == f"compute.{decision}",
                        )
                    )
                    == 1
                )
            async with sessions() as db:
                with pytest.raises(HTTPException) as conflict:
                    await decide_analysis_compute(
                        analysis_id,
                        params.model_copy(
                            update={
                                "decision": "rejected"
                                if decision == "approved"
                                else "approved"
                            }
                        ),
                        db,
                        scope.owner,
                        Response(),
                    )
                assert conflict.value.status_code == 409
            async with sessions() as db:
                inbox = await list_analysis_compute_approvals(
                    db, scope.owner, Response(), scope.project.id, limit=30, offset=0
                )
                assert inbox["items"] == []

    asyncio.run(exercise())


@pytest.mark.parametrize("same_decision", [True, False])
def test_compute_decision_concurrency_serializes_one_transition(same_decision):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            compute = await seed_compute(sessions, scope)
            analysis_id, detail = await routed_compute(sessions, scope, compute)

            async def decide(decision):
                async with sessions() as db:
                    return await decide_analysis_compute(
                        analysis_id,
                        decision_params(detail, decision=decision),
                        db,
                        scope.owner,
                        Response(),
                    )

            results = await asyncio.wait_for(
                asyncio.gather(
                    decide("approved"),
                    decide("approved" if same_decision else "rejected"),
                    return_exceptions=True,
                ),
                timeout=10,
            )
            successful = [result for result in results if isinstance(result, dict)]
            assert len(successful) == (2 if same_decision else 1)
            for result in results:
                if isinstance(result, Exception):
                    assert (
                        isinstance(result, HTTPException) and result.status_code == 409
                    )
            async with sessions() as db:
                details = await db.get(AnalysisCompute, analysis_id)
                assert details.approval_revision == 2
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisComputeEvent)
                        .where(
                            AnalysisComputeEvent.analysis_run_id == analysis_id,
                            AnalysisComputeEvent.kind.in_(
                                ["compute.approved", "compute.rejected"]
                            ),
                        )
                    )
                    == 1
                )

    asyncio.run(exercise())


@pytest.mark.parametrize("state", ["awaiting_approval", "queued", "running"])
def test_compute_cancel_after_source_revocation_returns_only_idempotent_receipt(state):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 987654)
            compute = await seed_compute(sessions, scope)
            analysis_id, detail = await routed_compute(sessions, scope, compute)
            async with sessions() as db:
                with pytest.raises(HTTPException) as generic:
                    await cancel_record_analysis(analysis_id, db, scope.analyst)
                assert generic.value.status_code == 409
            if state != "awaiting_approval":
                async with sessions() as db:
                    detail = await decide_analysis_compute(
                        analysis_id,
                        decision_params(detail),
                        db,
                        scope.owner,
                        Response(),
                    )
            async with sessions() as db:
                job = await db.get(ResearchComputeJob, detail["job"]["id"])
                if state == "running":
                    job.status = "running"
                    job.started_at = datetime.now(UTC)
                    run = await db.get(AnalysisRun, analysis_id)
                    run.status = "running"
                    run.started_at = datetime.now(UTC)
                params = AnalysisComputeCancel(
                    expected_revision=job.revision,
                    contract_digest=detail["approval"]["contract_digest"],
                    reason="Stop after source access was revoked",
                )
                await db.execute(
                    delete(ProjectUser).where(
                        ProjectUser.project_id == scope.project.id,
                        ProjectUser.user_id == scope.analyst.id,
                    )
                )
                await db.commit()
            async with sessions() as db:
                with pytest.raises(HTTPException) as inaccessible:
                    await get_analysis_compute(
                        analysis_id, db, scope.analyst, Response()
                    )
                assert inaccessible.value.status_code == 403
            async with sessions() as db:
                response = Response()
                receipt = await cancel_analysis_compute(
                    analysis_id, params, db, scope.analyst, response
                )
                assert response.headers["Cache-Control"] == "private, no-store"
                assert set(receipt) == {"analysis_id", "job_id", "status", "revision"}
                assert receipt["status"] == (
                    "cancel_requested" if state == "running" else "cancelled"
                )
                assert "987654" not in str(receipt)
            async with sessions() as db:
                repeated = await cancel_analysis_compute(
                    analysis_id, params, db, scope.analyst, Response()
                )
                assert repeated == receipt
                run = await db.get(AnalysisRun, analysis_id)
                assert run.status == ("running" if state == "running" else "cancelled")
                assert run.result is None
                details = await db.get(AnalysisCompute, analysis_id)
                assert details.approval_state == (
                    "cancelled" if state == "awaiting_approval" else "approved"
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisComputeEvent)
                        .where(
                            AnalysisComputeEvent.analysis_run_id == analysis_id,
                            AnalysisComputeEvent.kind.in_(
                                ["compute.cancelled", "compute.cancel_requested"]
                            ),
                        )
                    )
                    == 1
                )
            async with sessions() as db:
                with pytest.raises(HTTPException) as conflict:
                    await cancel_analysis_compute(
                        analysis_id,
                        params.model_copy(update={"reason": "Different stale request"}),
                        db,
                        scope.analyst,
                        Response(),
                    )
                assert conflict.value.status_code == 409

    asyncio.run(exercise())


@pytest.mark.parametrize("readonly_member", [False, True])
def test_compute_routes_hide_private_run_and_outputs_from_other_users(readonly_member):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions, public=True)
            await add_record(sessions, scope, 987654)
            compute = await seed_compute(sessions, scope)
            analysis_id, detail = await routed_compute(sessions, scope, compute)
            async with sessions() as db:
                if readonly_member:
                    db.add(
                        ProjectUser(
                            project_id=scope.project.id,
                            user_id=scope.outsider.id,
                            role=ProjectRole.VIEWER,
                            create_user_id=scope.owner.id,
                        )
                    )
                    await db.commit()
                output = await db.scalar(
                    select(ResearchComputeJobOutput).where(
                        ResearchComputeJobOutput.compute_job_id == detail["job"]["id"]
                    )
                )
                output_id = output.id
            cancel = AnalysisComputeCancel(
                expected_revision=detail["job"]["revision"],
                contract_digest=detail["approval"]["contract_digest"],
                reason="Synthetic unauthorized cancellation",
            )
            for actor in (scope.outsider, scope.recorder):
                for operation in ("get", "approval", "download", "cancel", "decide"):
                    async with sessions() as db:
                        with pytest.raises(HTTPException) as forbidden:
                            if operation == "get":
                                await get_analysis_compute(
                                    analysis_id, db, actor, Response()
                                )
                            elif operation == "approval":
                                await get_analysis_compute_approval(
                                    analysis_id, db, actor, Response()
                                )
                            elif operation == "download":
                                await download_analysis_compute_output(
                                    analysis_id, output_id, db, actor
                                )
                            elif operation == "cancel":
                                await cancel_analysis_compute(
                                    analysis_id, cancel, db, actor, Response()
                                )
                            else:
                                await decide_analysis_compute(
                                    analysis_id,
                                    decision_params(detail),
                                    db,
                                    actor,
                                    Response(),
                                )
                        assert forbidden.value.status_code == 404
            async with sessions() as db:
                with pytest.raises(HTTPException) as selected_approver_has_no_output:
                    await download_analysis_compute_output(
                        analysis_id, output_id, db, scope.owner
                    )
                assert selected_approver_has_no_output.value.status_code == 404
            async with sessions() as db:
                with pytest.raises(HTTPException) as not_completed:
                    await download_analysis_compute_output(
                        analysis_id, output_id, db, scope.analyst
                    )
                assert not_completed.value.status_code == 409
            async with sessions() as db:
                with pytest.raises(HTTPException) as creator_cannot_approve:
                    await decide_analysis_compute(
                        analysis_id,
                        decision_params(detail),
                        db,
                        scope.analyst,
                        Response(),
                    )
                assert creator_cannot_approve.value.status_code == 403

    asyncio.run(exercise())


@pytest.mark.parametrize("change", ["digest", "revision", "source_access"])
def test_compute_approval_route_rechecks_sealed_contract_and_live_source_access(change):
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 2)
            compute = await seed_compute(sessions, scope)
            analysis_id, detail = await routed_compute(sessions, scope, compute)
            params = decision_params(detail)
            if change == "digest":
                params = params.model_copy(update={"contract_digest": "0" * 64})
            elif change == "revision":
                params = params.model_copy(update={"expected_revision": 2})
            else:
                async with sessions() as db:
                    await db.execute(
                        delete(LabUser).where(
                            LabUser.lab_id == scope.lab.id,
                            LabUser.user_id == scope.owner.id,
                        )
                    )
                    await db.commit()
            async with sessions() as db:
                with pytest.raises(HTTPException) as rejected:
                    await decide_analysis_compute(
                        analysis_id, params, db, scope.owner, Response()
                    )
                assert rejected.value.status_code == (
                    403 if change == "source_access" else 409
                )
            async with sessions() as db:
                details = await db.get(AnalysisCompute, analysis_id)
                job = await db.get(ResearchComputeJob, detail["job"]["id"])
                assert details.approval_state == "pending"
                assert details.approval_revision == 1
                assert job.status == "awaiting_approval"

    asyncio.run(exercise())


def test_compute_approval_view_never_exposes_private_runner_failure_text():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            await add_record(sessions, scope, 987654)
            compute = await seed_compute(sessions, scope)
            analysis_id, detail = await routed_compute(sessions, scope, compute)
            async with sessions() as db:
                await decide_analysis_compute(
                    analysis_id, decision_params(detail), db, scope.owner, Response()
                )
            async with sessions() as db:
                job = await db.get(ResearchComputeJob, detail["job"]["id"])
                # This is the same terminal transition used by Runner failure receipts.
                await finish_analysis_failure(
                    db,
                    job,
                    error="Synthetic failure while parsing private value 987654",
                )
                await db.commit()
            async with sessions() as db:
                owner_view = await get_analysis_compute(
                    analysis_id, db, scope.analyst, Response()
                )
                assert "987654" in owner_view["run"]["error"]
                approval = await get_analysis_compute_approval(
                    analysis_id, db, scope.owner, Response()
                )
                assert approval["run"]["status"] == "failed"
                assert "987654" not in str(approval)
                assert approval["job"]["error"] is None

    asyncio.run(exercise())
