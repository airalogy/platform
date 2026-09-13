"""Private adapter state/receipts and shared transport, without executing code.

Database/session doubles isolate lifecycle mechanics here; real source permissions
and actual container execution are covered by their separate integration suites.
"""

import asyncio
import hashlib
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.models.research_execution import ResearchComputeJobOutput
from app.routers import research_compute_jobs as routes
from app.services import analysis_compute_runtime as runtime
from app.services.analysis_compute import analysis_compute_input_bytes
from app.services.analysis_engine import canonical_digest
from app.services.record_analyses import utcnow
from app.services.research_compute_jobs import (
    compute_lease_token_digest,
    sign_compute_envelope,
)


@pytest.fixture(autouse=True)
def private_analysis_has_no_workflow_binding(monkeypatch):
    # These session doubles model standalone private runs; Workflow integration
    # and real database lookups are exercised in their own PostgreSQL suite.
    from app.services import workflow_compute_runtime

    monkeypatch.setattr(
        workflow_compute_runtime, "authorize_workflow_compute", AsyncMock()
    )
    monkeypatch.setattr(workflow_compute_runtime, "terminal_compute", AsyncMock())
    monkeypatch.setattr(workflow_compute_runtime, "started_compute", AsyncMock())
    monkeypatch.setattr(
        workflow_compute_runtime, "validate_workflow_compute_result", AsyncMock()
    )


def state(status="running"):
    run = SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        created_by_user_id=uuid4(),
        status="running" if status == "running" else "pending",
        result=None,
        source_snapshot={
            "records": [{"record_id": "private", "data": {"var": {"x": 13}}}]
        },
    )
    lab_id = uuid4()
    job = SimpleNamespace(
        id=uuid4(),
        analysis_run_id=run.id,
        action_id=None,
        status=status,
        result={},
        output_manifest=[],
        usage={},
        actual_cost=None,
        source_code="print('synthetic contract')",
        source_sha256="a" * 64,
        input_payload={"scale": 1},
        language="python",
        compute_environment_id=uuid4(),
        compute_environment_revision_id=uuid4(),
        compute_environment_revision=1,
        created_by_user_id=run.created_by_user_id,
        resource_limits={
            "cpu_millis": 1000,
            "memory_mb": 256,
            "gpu_count": 0,
            "timeout_seconds": 60,
            "max_output_bytes": 4096,
        },
        timeout_seconds=60,
        result_schema={"type": "object"},
        environment_snapshot={
            "metadata": {"lab_id": str(lab_id), "estimated_cost_per_hour": "6"}
        },
        estimated_cost=Decimal("0.1"),
        currency="USD",
        revision=1,
        attempt_count=0,
        lease_expires_at=utcnow() + timedelta(minutes=2),
        lease_token_digest="b" * 64,
        started_at=utcnow() if status == "running" else None,
        cancel_reason=None,
    )
    details = SimpleNamespace(max_cost=Decimal("0.1"), budget_currency="USD")
    runner = SimpleNamespace(
        id=uuid4(),
        lab_id=lab_id,
        enabled=True,
        revoked_at=None,
        runner_protocol_version="airalogy.compute-runner.v1",
        token_digest="c" * 64,
        max_concurrent_jobs=1,
        last_report={
            "available_slots": 1,
            "active_jobs": 0,
            "job_schemas": [runtime.ANALYSIS_JOB_SCHEMA],
        },
    )
    revision = SimpleNamespace(
        runner_protocol_version="airalogy.compute-runner.v1",
        image_ref="python@sha256:" + "d" * 64,
        runtime_version="3.13",
        network_policy="none",
        allowed_egress_hosts=[],
    )
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=run),
        get=AsyncMock(return_value=details),
        execute=AsyncMock(),
        commit=AsyncMock(),
    )
    return run, job, details, runner, revision, db


def output():
    item = ResearchComputeJobOutput(
        id=uuid4(),
        compute_job_id=uuid4(),
        position=1,
        mount_name="summary.json",
        asset_name="Private summary",
        description="",
        kind="file",
        media_type="application/json",
        max_bytes=1024,
        required=True,
        data_schema={},
        version_metadata={},
        blob_id=uuid4(),
        uploaded_at=utcnow(),
        registered_at=None,
    )
    blob = SimpleNamespace(
        checksum_sha256="e" * 64, content_type="application/json", size_bytes=14
    )
    receipt = routes.RunnerCompletedOutput(
        output_id=item.id, checksum_sha256=blob.checksum_sha256, byte_size=14
    )
    return item, blob, receipt


def test_input_is_exact_private_snapshot_without_dataasset_or_blob():
    run, job, *_ = state()
    row = SimpleNamespace(
        id=uuid4(),
        analysis_run_id=run.id,
        compute_job_id=job.id,
        mount_name="records.json",
        data_asset_id=None,
        data_asset_version_id=None,
    )
    manifest = runtime.analysis_input_manifest(job, run, row)
    payload = analysis_compute_input_bytes(run)
    assert manifest["checksum_sha256"] == hashlib.sha256(payload).hexdigest()
    assert manifest["byte_size"] == len(payload)
    assert (
        manifest["download_path"] == f"/compute-runner/v1/jobs/{job.id}/inputs/{row.id}"
    )
    assert (
        not {"data_asset_id", "data_asset_version_id", "storage_object_key", "blob_id"}
        & manifest.keys()
    )
    row.data_asset_id = uuid4()
    with pytest.raises(HTTPException, match="binding"):
        runtime.analysis_input_manifest(job, run, row)
    with pytest.raises(HTTPException, match="binding"):
        runtime.analysis_input_manifest(job, run, None)


@pytest.mark.parametrize(
    "change", ["missing", "unknown", "checksum", "size", "type", "limit", "duplicate"]
)
def test_shared_receipts_reject_changed_or_missing_uploads(change):
    item, blob, receipt = output()
    receipts = [receipt]
    if change == "missing":
        receipts = []
    elif change == "unknown":
        receipt.output_id = uuid4()
    elif change == "checksum":
        receipt.checksum_sha256 = "f" * 64
    elif change == "size":
        receipt.byte_size += 1
    elif change == "type":
        blob.content_type = "text/plain"
    elif change == "limit":
        item.max_bytes = 1
    else:
        receipts *= 2
    with pytest.raises(HTTPException) as caught:
        runtime.verified_output_receipts([(item, blob)], receipts)
    assert caught.value.status_code == 422


def test_output_stays_private_after_registration_and_cannot_gain_shared_binding():
    item, blob, receipt = output()
    assert runtime.verified_output_receipts([(item, blob)], [receipt]) == [(item, blob)]
    assert runtime.private_output_manifest([(item, blob)])[0]["status"] == "uploaded"
    item.registered_at = utcnow()
    manifest = runtime.private_output_manifest([(item, blob)])
    assert manifest[0]["status"] == "registered"
    assert "research_file_id" not in manifest[0]
    assert "data_asset_id" not in manifest[0]
    for field in ("research_file_id", "data_asset_id", "data_asset_version_id"):
        setattr(item, field, uuid4())
        with pytest.raises(HTTPException, match="shared asset"):
            runtime.private_output_manifest([(item, blob)])
        setattr(item, field, None)
    with pytest.raises(HTTPException, match="missing"):
        runtime.private_output_manifest([(item, None)])


def test_completion_seals_private_result_and_only_private_event():
    async def check():
        run, job, details, _, _, db = state()
        item, blob, receipt = output()
        await runtime.seal_analysis_completion(
            db,
            job,
            run,
            details,
            result={"mean": 13},
            usage={"wall_seconds": 30, "output_bytes": 25},
            rows=[(item, blob)],
            outputs=[receipt],
        )
        assert job.status == "completed" and run.status == "succeeded"
        assert job.actual_cost == Decimal("0.05")
        assert run.result["computed_result"] == {"mean": 13}
        assert run.result_digest == canonical_digest(run.result)
        assert run.result["outputs"][0]["status"] == "registered"
        assert (
            item.research_file_id
            is item.data_asset_id
            is item.data_asset_version_id
            is None
        )
        assert job.lease_expires_at is None
        assert str(db.execute.call_args.args[0].table) == "analysis_compute_events"
        with pytest.raises(HTTPException, match="cannot be replaced"):
            await runtime.seal_analysis_completion(
                db,
                job,
                run,
                details,
                result={"mean": 99},
                usage={},
                rows=[],
                outputs=[],
            )
        assert run.result["computed_result"] == {"mean": 13}

    asyncio.run(check())


@pytest.mark.parametrize(
    "status", ["cancel_requested", "cancelled", "failed", "completed"]
)
def test_late_results_cannot_overwrite_final_or_cancelling_job(status):
    async def check():
        run, job, details, _, _, db = state(status)
        with pytest.raises(HTTPException, match="cannot be replaced"):
            await runtime.seal_analysis_completion(
                db, job, run, details, result={}, usage={}, rows=[], outputs=[]
            )
        assert run.result is None
        db.execute.assert_not_called()

    asyncio.run(check())


def test_nonfinite_results_and_excess_cost_cannot_be_sealed():
    async def check():
        run, job, details, _, _, db = state()
        item, blob, receipt = output()
        with pytest.raises(HTTPException, match="finite"):
            await runtime.seal_analysis_completion(
                db,
                job,
                run,
                details,
                result={"x": float("nan")},
                usage={"wall_seconds": 1},
                rows=[(item, blob)],
                outputs=[receipt],
            )
        assert item.registered_at is None
        assert run.result is None
        details.max_cost = Decimal("0.01")
        with pytest.raises(HTTPException, match="ceiling"):
            runtime.private_actual_cost(job, details, 30)

    asyncio.run(check())


def test_cost_rounding_matches_the_persisted_numeric_estimate():
    _, job, details, *_ = state()
    job.environment_snapshot["metadata"]["estimated_cost_per_hour"] = "1"
    job.timeout_seconds = 60
    job.estimated_cost = details.max_cost = Decimal("0.016666666666666667")
    assert runtime.private_actual_cost(job, details, 60) == job.estimated_cost
    job.timeout_seconds = 61
    job.estimated_cost = details.max_cost = Decimal("0.016944444444444444")
    assert runtime.private_actual_cost(job, details, 61) == job.estimated_cost


@pytest.mark.parametrize("callback", ["complete", "fail", "cancelled"])
def test_all_private_callbacks_reject_invalid_lease_before_source_access(
    monkeypatch, callback
):
    async def check():
        _, job, _, runner, _, db = state("cancel_requested")
        db.scalars = AsyncMock(return_value=SimpleNamespace(first=lambda: job))
        monkeypatch.setattr(
            routes, "authenticate_compute_runner", AsyncMock(return_value=runner)
        )
        handlers = {
            "complete": (
                routes.complete_compute_job,
                routes.RunnerComplete(result={}, usage={"wall_seconds": 1}),
            ),
            "fail": (routes.fail_compute_job, routes.RunnerFail(error="stopped")),
            "cancelled": (
                routes.acknowledge_compute_cancellation,
                routes.RunnerCancelled(reason="stopped"),
            ),
        }
        handler, params = handlers[callback]
        with pytest.raises(HTTPException) as caught:
            await handler(job.id, params, "runner-token", "wrong-lease", db)
        assert caught.value.status_code == 401
        db.scalar.assert_not_awaited()
        assert job.status == "cancel_requested"

    asyncio.run(check())


def test_completed_retry_checks_authority_but_not_new_deadline_and_is_immutable(
    monkeypatch,
):
    async def check():
        run, job, details, runner, _, db = state("completed")
        job.result = {"mean": 13}
        params = routes.RunnerComplete(result=job.result, usage={"wall_seconds": 1})
        job.usage = params.usage.model_dump(mode="json")
        monkeypatch.setattr(
            routes, "authenticate_compute_runner", AsyncMock(return_value=runner)
        )
        monkeypatch.setattr(
            routes,
            "_runner_job_context",
            AsyncMock(return_value=(job, None, run, None)),
        )
        authority = AsyncMock(return_value=(run, details))
        monkeypatch.setattr(routes, "_authorize_analysis_request", authority)
        assert await routes.complete_compute_job(
            job.id, params, "token", "lease", db
        ) == {"status": "completed"}
        authority.assert_awaited_once_with(db, job, runner, check_deadline=False)
        params.result = {"mean": 99}
        with pytest.raises(HTTPException, match="different result"):
            await routes.complete_compute_job(job.id, params, "token", "lease", db)
        assert job.result == {"mean": 13}

    asyncio.run(check())


def test_source_revocation_requests_cancellation_and_does_not_publish(monkeypatch):
    async def check():
        run, job, _, runner, _, db = state()
        monkeypatch.setattr(
            routes,
            "authorize_analysis_runtime",
            AsyncMock(side_effect=HTTPException(403, "revoked")),
        )
        with pytest.raises(HTTPException) as caught:
            await routes._authorize_analysis_request(db, job, runner)
        assert caught.value.status_code == 409
        assert job.status == "cancel_requested"
        assert run.result is None
        assert job.lease_token_digest == "b" * 64
        assert str(db.execute.call_args.args[0].table) == "analysis_compute_events"
        db.commit.assert_awaited_once()

    asyncio.run(check())


@pytest.mark.parametrize("cancelled", [False, True])
def test_revoked_source_still_accepts_stop_receipt(monkeypatch, cancelled):
    async def check():
        run, job, _, runner, _, db = state("cancel_requested")
        job.cancel_reason = "source access revoked"
        monkeypatch.setattr(
            routes, "authenticate_compute_runner", AsyncMock(return_value=runner)
        )
        monkeypatch.setattr(
            routes,
            "_runner_job_context",
            AsyncMock(return_value=(job, None, run, None)),
        )
        authority = AsyncMock(
            side_effect=AssertionError(
                "stop receipt must not require revoked source access"
            )
        )
        monkeypatch.setattr(routes, "authorize_analysis_runtime", authority)
        kwargs = {
            "job_id": job.id,
            "runner_token": "token",
            "lease_token": "lease",
            "db_session": db,
        }
        if cancelled:
            await routes.acknowledge_compute_cancellation(
                **kwargs, params=routes.RunnerCancelled(reason="stopped")
            )
        else:
            await routes.fail_compute_job(
                **kwargs, params=routes.RunnerFail(error="local stopped")
            )
        assert job.status == run.status == ("cancelled" if cancelled else "failed")
        assert run.result is None
        assert job.lease_expires_at is None
        authority.assert_not_called()

    asyncio.run(check())


def test_analysis_delivery_reuses_signed_lease_without_fake_task_context():
    async def check():
        run, job, _, runner, revision, db = state("queued")
        delivered = await routes._deliver_compute_lease(
            db,
            job=job,
            runner=runner,
            revision=revision,
            context={
                "schema": runtime.ANALYSIS_JOB_SCHEMA,
                "context": {
                    "kind": "analysis",
                    "analysis_id": str(run.id),
                    "project_id": str(run.project_id),
                    "lab_id": str(runner.lab_id),
                },
            },
            inputs=[],
            output_rows=[],
        )
        assert delivered["signature"] == sign_compute_envelope(
            delivered["job"], runner.token_digest
        )
        assert job.lease_token_digest == compute_lease_token_digest(
            delivered["lease_token"]
        )
        assert job.status == "leased" and job.attempt_count == 1
        assert not {"action_id", "task_id", "run_id"} & delivered["job"].keys()
        assert delivered["job"]["environment"]["resource_limits"] == job.resource_limits
        assert delivered["job"]["environment"]["network_policy"] == "none"

    asyncio.run(check())


@pytest.mark.parametrize("analysis_support", [False, True])
def test_lease_filters_unsupported_analysis_before_selecting_job(
    monkeypatch, analysis_support
):
    async def check():
        _, _, _, runner, _, db = state()
        db.scalar.return_value = runner
        if not analysis_support:
            runner.last_report.pop("job_schemas")
        db.scalars = AsyncMock(
            side_effect=[
                SimpleNamespace(all=list),
                SimpleNamespace(all=list),
            ]
        )
        monkeypatch.setattr(
            routes, "authenticate_compute_runner", AsyncMock(return_value=runner)
        )
        monkeypatch.setattr(routes, "runner_report_is_execution_ready", lambda _: True)
        monkeypatch.setattr(
            routes, "runner_active_job_count", AsyncMock(return_value=0)
        )
        assert (await routes.lease_compute_job("token", db))["job"] is None
        candidate = db.scalars.call_args.args[0]
        sql = str(
            candidate.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        assert "LEFT OUTER JOIN research_actions" in sql
        # Candidate discovery must not take Job locks ahead of a Workflow Task.
        assert "FOR UPDATE" not in sql
        assert ("analysis_run_id IS NOT NULL" in sql) is analysis_support

    asyncio.run(check())


def test_expired_running_analysis_is_uncertain_not_requeued(monkeypatch):
    async def check():
        run, job, _, runner, _, db = state()
        db.scalar.side_effect = [runner, run]
        job.runner_id = runner.id
        job.lease_expires_at = utcnow() - timedelta(seconds=1)
        db.scalars = AsyncMock(
            side_effect=[
                SimpleNamespace(all=lambda: [job]),
                SimpleNamespace(all=list),
            ]
        )
        monkeypatch.setattr(
            routes, "authenticate_compute_runner", AsyncMock(return_value=runner)
        )
        monkeypatch.setattr(routes, "runner_report_is_execution_ready", lambda _: True)
        monkeypatch.setattr(
            routes, "runner_active_job_count", AsyncMock(return_value=0)
        )
        monkeypatch.setattr(
            routes,
            "_lock_compute_job_context",
            AsyncMock(return_value=(job, None, run, None)),
        )
        assert (await routes.lease_compute_job("token", db))["job"] is None
        assert job.status == run.status == "failed"
        assert "uncertain" in job.error
        assert job.attempt_count == 0
        params = db.execute.call_args.args[0].compile().params
        assert params["payload"]["uncertain"] is True

    asyncio.run(check())


def test_authority_gate_requires_exact_runner_binding_and_analysis_capability(
    monkeypatch,
):
    async def check():
        run, job, details, runner, revision, db = state()
        authority = AsyncMock(return_value=(run, details))
        monkeypatch.setattr(runtime, "authorize_compute_execution", authority)
        db.get.return_value = revision
        db.scalar.return_value = uuid4()
        assert await runtime.authorize_analysis_runtime(db, job, runner) == (
            run,
            details,
        )
        authority.assert_awaited_once_with(db, job, check_deadline=True)
        db.scalar.return_value = None
        with pytest.raises(HTTPException, match="execution authority"):
            await runtime.authorize_analysis_runtime(db, job, runner)
        db.scalar.return_value = uuid4()
        runner.last_report.pop("job_schemas")
        with pytest.raises(HTTPException, match="execution authority"):
            await runtime.authorize_analysis_runtime(db, job, runner)

    asyncio.run(check())
