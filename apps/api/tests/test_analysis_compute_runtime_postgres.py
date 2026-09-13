"""Real PostgreSQL/MinIO private Compute transport and opt-in OCI execution.

No authorization, SQL, signatures, input snapshots, storage or router is mocked.
The transport-only tests explicitly submit receiver fixtures; only the test gated
by COMPUTE_ENGINE_TEST runs the signed source in the actual ContainerEngine.
Both paths use real preview/confirmation/approval and immutable output receipts.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, Request, Response
from sqlalchemy import delete, func, select

from app.config import config
from app.models.analysis import AnalysisRun
from app.models.knowledge import ResearchFile
from app.models.lab import LabUser
from app.models.project import Project, ProjectType, ProjectUser
from app.models.research import ResearchTask
from app.models.research_asset import DataAsset
from app.models.research_execution import (
    ResearchComputeEnvironmentRevision,
    ResearchComputeJob,
    ResearchComputeJobOutput,
    ResearchComputeRunner,
)
from app.routers import analysis_compute as analyses
from app.routers import research_compute_jobs as jobs
from app.routers.analyses import AnalysisConfirmRequest
from app.routers.research_compute_runners import (
    ComputeRunnerReport,
    report_compute_runner_status,
)
from app.services.analysis_compute import analysis_compute_input_bytes
from app.services.analysis_compute_contracts import (
    ANALYSIS_JOB_SCHEMA,
    AnalysisComputeDraft,
)
from app.services.analysis_engine import canonical_digest
from app.services.research_compute_runners import (
    compute_runner_token_digest,
    generate_compute_runner_token,
)
from tests.test_record_analysis_compute_postgres import (
    compute_draft,
    decision_params,
    seed_compute,
)
from tests.test_record_analysis_postgres import add_record, database, seed_analysis

pytestmark = pytest.mark.skipif(
    not os.environ.get("RESOURCE_TEST_DATABASE_URL"),
    reason="Real migrated PostgreSQL and managed test storage are required",
)

SOURCE = """import json, os
from pathlib import Path
assert os.getuid() == 65532
try:
    Path('/must-not-write-root').write_text('unsafe')
except OSError:
    pass
else:
    raise RuntimeError('root filesystem is writable')
snapshot = json.loads((Path(os.environ['AIRALOGY_INPUT_DIR']) / 'records.json').read_text())
values = [record['data']['var']['value'] for record in snapshot['records']]
result = {'mean': sum(values) / len(values), 'count': len(values), 'uid': os.getuid()}
Path(os.environ['AIRALOGY_RESULT_JSON']).write_text(json.dumps(result))
Path('/airalogy/output/files/summary.json').write_text(json.dumps(result))
"""


@pytest.fixture(autouse=True)
def no_ai_or_role_stubs(monkeypatch):
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")
    monkeypatch.setattr(config, "AI_ENABLED", False)


async def report_runner(sessions, token, *, schemas=None, slots=1):
    params = {
        "protocol_version": "airalogy.compute-runner.v1",
        "runner_version": "0.1.0",
        "executor_backend": "docker",
        "active_jobs": 0,
        "available_slots": slots,
        "security": {
            "non_root": True,
            "read_only_root_filesystem": True,
            "network_isolation": True,
            "no_host_mounts": True,
        },
    }
    if schemas is not None:
        params["job_schemas"] = schemas
    async with sessions() as db:
        result = await report_compute_runner_status(
            ComputeRunnerReport(**params), token, db
        )
        assert result["execution_ready"] is True


async def fixture(sessions, *, real_engine=False):
    scope = await seed_analysis(sessions, public=True)
    records = [
        await add_record(sessions, scope, value, author=scope.analyst, number=index)
        for index, value in enumerate((2, 4, 6, 8), 1)
    ]
    compute = await seed_compute(sessions, scope)
    token = generate_compute_runner_token()
    async with sessions() as db:
        runner = await db.get(ResearchComputeRunner, compute.runner.id)
        runner.token_digest = compute_runner_token_digest(token)
        runner.max_concurrent_jobs = 1
        revision = await db.get(ResearchComputeEnvironmentRevision, compute.revision.id)
        revision.resource_limits = {
            "cpu_millis": 1000,
            "memory_mb": 256,
            "gpu_count": 0,
            "timeout_seconds": 60,
            "max_output_bytes": 65536,
        }
        revision.result_schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "mean": {"type": "number"},
                "count": {"type": "integer"},
                "uid": {"type": "integer"},
            },
            "required": ["mean", "count", "uid"],
        }
        if real_engine:
            revision.image_ref = os.environ["COMPUTE_TEST_IMAGE"]
        await db.commit()
    await report_runner(
        sessions, token, schemas=["airalogy.compute-job.v1", ANALYSIS_JOB_SCHEMA]
    )
    return SimpleNamespace(scope=scope, compute=compute, token=token, records=records)


async def confirmed(sessions, f, *, question="Synthetic transport contract"):
    raw = compute_draft(f.scope, f.compute).model_dump(mode="json")
    raw["recipe"]["source_code"] = SOURCE
    raw["question"] = question
    async with sessions() as db:
        draft = await analyses.preview_analysis_compute(
            AnalysisComputeDraft.model_validate(raw), db, f.scope.analyst, Response()
        )
    async with sessions() as db:
        run = await analyses.confirm_analysis_compute(
            AnalysisConfirmRequest(
                preview_id=draft["id"],
                preview_digest=draft["preview_digest"],
                client_idempotency_key=f"runtime-{uuid4().hex}",
            ),
            db,
            f.scope.analyst,
            Response(),
        )
    analysis_id = UUID(str(run["id"]))
    async with sessions() as db:
        detail = await analyses.get_analysis_compute_approval(
            analysis_id, db, f.scope.owner, Response()
        )
    async with sessions() as db:
        approved = await analyses.decide_analysis_compute(
            analysis_id, decision_params(detail), db, f.scope.owner, Response()
        )
        assert approved["job"]["status"] == "queued"
    return analysis_id


async def lease(sessions, f):
    from airalogy_compute_runner.models import ComputeJobEnvelope
    from airalogy_compute_runner.security import verify_job_signature

    async with sessions() as db:
        result = await jobs.lease_compute_job(f.token, db)
    assert result["job"] is not None
    verify_job_signature(result["job"], result["signature"], f.token)
    parsed = ComputeJobEnvelope.parse(result["job"])
    assert parsed.action_id is parsed.task_id is parsed.run_id is None
    assert parsed.project_id == str(f.scope.project.id)
    assert parsed.lab_id == str(f.scope.lab.id)
    assert len(parsed.inputs) == len(parsed.outputs) == 1
    return SimpleNamespace(raw=result, job=parsed, token=result["lease_token"])


async def download_and_start(sessions, f, delivery):
    job = delivery.job
    async with sessions() as db:
        downloaded = await jobs.download_compute_input(
            UUID(job.job_id),
            UUID(job.inputs[0].id),
            f.token,
            delivery.token,
            db,
        )
        assert downloaded.headers["Cache-Control"] == "no-store"
        persisted = await db.get(AnalysisRun, UUID(job.analysis_id))
        assert downloaded.body == analysis_compute_input_bytes(persisted)
    assert hashlib.sha256(downloaded.body).hexdigest() == job.inputs[0].checksum_sha256
    assert len(downloaded.body) == job.inputs[0].byte_size
    assert {item["record_id"] for item in json.loads(downloaded.body)["records"]} == {
        str(r.id) for r in f.records
    }
    async with sessions() as db:
        started = await jobs.start_compute_job(
            UUID(job.job_id), f.token, delivery.token, db
        )
        assert started["status"] == "running"
    return downloaded.body


def byte_request(payload, *, barrier=None):
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        if barrier is not None:
            await asyncio.wait_for(barrier.wait(), timeout=15)
        return {"type": "http.request", "body": payload, "more_body": False}

    return Request(
        {"type": "http", "method": "PUT", "path": "/synthetic-output", "headers": []},
        receive,
    )


async def upload(sessions, f, delivery, payload, *, checksum=None, barrier=None):
    async with sessions() as db:
        return await jobs.upload_compute_output(
            job_id=UUID(delivery.job.job_id),
            output_id=UUID(delivery.job.outputs[0].id),
            request=byte_request(payload, barrier=barrier),
            runner_token=f.token,
            lease_token=delivery.token,
            content_length=len(payload),
            checksum_sha256=checksum or hashlib.sha256(payload).hexdigest(),
            content_type="application/json",
            db_session=db,
        )


def completion(delivery, result, payload):
    # Usage here represents test execution or an explicitly hand-submitted receipt.
    result_bytes = len(
        json.dumps(
            result, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    )
    return jobs.RunnerComplete(
        result=result,
        usage={"wall_seconds": 1, "output_bytes": len(payload) + result_bytes},
        outputs=[
            {
                "output_id": delivery.job.outputs[0].id,
                "checksum_sha256": hashlib.sha256(payload).hexdigest(),
                "byte_size": len(payload),
            }
        ],
    )


async def submit_completion(sessions, f, delivery, params):
    async with sessions() as db:
        return await jobs.complete_compute_job(
            UUID(delivery.job.job_id), params, f.token, delivery.token, db
        )


async def read_completed(sessions, f, delivery, result, payload):
    analysis_id, output_id = (
        UUID(delivery.job.analysis_id),
        UUID(delivery.job.outputs[0].id),
    )
    async with sessions() as db:
        response = Response()
        report = await analyses.get_analysis_compute(
            analysis_id, db, f.scope.analyst, response
        )
        assert response.headers["Cache-Control"] == "private, no-store"
        assert report["run"]["result"]["computed_result"] == result
        assert report["run"]["result_digest"] == canonical_digest(
            report["run"]["result"]
        )
        output = await db.get(ResearchComputeJobOutput, output_id)
        assert output.blob_id is not None and output.registered_at is not None
        assert (
            output.research_file_id
            is output.data_asset_id
            is output.data_asset_version_id
            is None
        )
        for model in (DataAsset, ResearchFile, ResearchTask):
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.project_id == f.scope.project.id)
                )
                == 0
            )
        downloaded = await analyses.download_analysis_compute_output(
            analysis_id, output_id, db, f.scope.analyst
        )
        chunks = [chunk async for chunk in downloaded.body_iterator]
        assert b"".join(chunks) == payload
        assert (
            downloaded.headers["X-Content-SHA256"]
            == hashlib.sha256(payload).hexdigest()
        )
    for user in (f.scope.owner, f.scope.outsider):
        async with sessions() as db:
            with pytest.raises(HTTPException) as denied:
                await analyses.download_analysis_compute_output(
                    analysis_id, output_id, db, user
                )
            assert denied.value.status_code == 404
    async with sessions() as db:
        with pytest.raises(HTTPException) as private_job:
            await jobs._user_job_context(
                db, f.scope.owner, UUID(delivery.job.job_id), lock=False
            )
        assert private_job.value.status_code == 404


def execute_container(delivery, input_bytes):
    """Execute the actual approved Python source in the shipping OCI engine."""
    from airalogy_compute_runner.config import RunnerConfig
    from airalogy_compute_runner.engine import ContainerEngine

    with tempfile.TemporaryDirectory(prefix="analysis-runtime-pg-") as directory:
        root = Path(directory)
        input_file = root / "records.json"
        input_file.write_bytes(input_bytes)
        engine = ContainerEngine(
            RunnerConfig(
                platform_url="http://127.0.0.1:4000",
                runner_token="aicr_" + "synthetic" * 8,
                state_file=root / "state.json",
                backend=os.environ.get("COMPUTE_TEST_BACKEND", "docker"),
                helper_image=os.environ["COMPUTE_TEST_HELPER_IMAGE"],
                egress_networks={},
                stop_timeout_seconds=1,
                max_workspace_bytes=64 * 1024 * 1024,
            )
        )
        job = delivery.job
        container, volume = engine.names(job.job_id)
        try:
            engine.verify()
            engine.create_workspace(job)
            engine.populate_workspace(job, volume, {job.inputs[0].id: input_file})
            process = engine.start(job, container, volume)
            assert process.process.wait(timeout=60) == 0
            result, _size = engine.read_result(job, volume)
            size, digest = engine.output_metadata(job.outputs[0], volume)
            streamed = engine.open_output(job.outputs[0], volume)
            payload = streamed.stream.read(job.outputs[0].max_bytes + 1)
            engine.finish_output(streamed)
            assert len(payload) == size
            assert hashlib.sha256(payload).hexdigest() == digest
            assert json.loads(payload) == result
            return result, payload
        finally:
            engine.cleanup(container, volume)


async def successful_flow(*, real_engine=False):
    async with database() as sessions:
        f = await fixture(sessions, real_engine=real_engine)
        analysis_id = await confirmed(sessions, f)
        delivery = await lease(sessions, f)
        assert delivery.job.analysis_id == str(analysis_id)
        inputs = await download_and_start(sessions, f, delivery)
        if real_engine:
            result, payload = execute_container(delivery, inputs)
            assert result == {"mean": 5.0, "count": 4, "uid": 65532}
        else:
            # Receiver-contract fixture: not evidence of executing approved source.
            result = {"mean": 17.25, "count": 99, "uid": 65532}
            payload = json.dumps(result).encode()
        receipt = await upload(sessions, f, delivery, payload)
        assert receipt["checksum_sha256"] == hashlib.sha256(payload).hexdigest()
        assert (await upload(sessions, f, delivery, payload))["output_id"] == receipt[
            "output_id"
        ]
        params = completion(delivery, result, payload)
        assert await submit_completion(sessions, f, delivery, params) == {
            "status": "completed"
        }
        assert await submit_completion(sessions, f, delivery, params) == {
            "status": "completed"
        }
        changed = params.model_copy(
            update={"result": {"mean": -999, "count": 1, "uid": 65532}}
        )
        with pytest.raises(HTTPException) as immutable:
            await submit_completion(sessions, f, delivery, changed)
        assert immutable.value.status_code == 409
        await read_completed(sessions, f, delivery, result, payload)
        # Removing membership alone does not revoke a public Project's default
        # EXPLORER source access. Preserve that legitimate read behavior first.
        async with sessions() as db:
            await db.execute(
                delete(ProjectUser).where(
                    ProjectUser.project_id == f.scope.project.id,
                    ProjectUser.user_id == f.scope.analyst.id,
                )
            )
            await db.commit()
        async with sessions() as db:
            still_readable = await analyses.download_analysis_compute_output(
                analysis_id, UUID(delivery.job.outputs[0].id), db, f.scope.analyst
            )
            assert (
                b"".join([chunk async for chunk in still_readable.body_iterator])
                == payload
            )
        # Making this synthetic Project private then removes the former
        # member's actual source permission, including already computed outputs.
        async with sessions() as db:
            project = await db.get(Project, f.scope.project.id)
            project.type = ProjectType.PRIVATE
            await db.commit()
        async with sessions() as db:
            with pytest.raises(HTTPException) as revoked:
                await analyses.download_analysis_compute_output(
                    analysis_id, UUID(delivery.job.outputs[0].id), db, f.scope.analyst
                )
            assert revoked.value.status_code == 403
        with pytest.raises(HTTPException):
            await submit_completion(sessions, f, delivery, params)


def test_real_pg_storage_and_runtime_accept_hand_submitted_receipts_without_shared_assets():
    asyncio.run(successful_flow())


@pytest.mark.skipif(
    os.environ.get("COMPUTE_ENGINE_TEST") != "1",
    reason="Explicit real OCI engine opt-in required",
)
def test_real_pg_approved_source_runs_in_isolated_container_and_seals_actual_result():
    asyncio.run(successful_flow(real_engine=True))


@pytest.mark.parametrize("revoke", ["owner", "approver"])
def test_runtime_source_revocation_stops_reads_and_outputs_but_accepts_cancel_receipt(
    revoke,
):
    async def exercise():
        async with database() as sessions:
            f = await fixture(sessions)
            analysis_id = await confirmed(sessions, f)
            delivery = await lease(sessions, f)
            await download_and_start(sessions, f, delivery)
            async with sessions() as db:
                model, scope_column, scope_id, user_id = (
                    (
                        ProjectUser,
                        ProjectUser.project_id,
                        f.scope.project.id,
                        f.scope.analyst.id,
                    )
                    if revoke == "owner"
                    else (LabUser, LabUser.lab_id, f.scope.lab.id, f.scope.owner.id)
                )
                await db.execute(
                    delete(model).where(
                        scope_column == scope_id, model.user_id == user_id
                    )
                )
                await db.commit()
            async with sessions() as db:
                stopped = await jobs.heartbeat_compute_job(
                    UUID(delivery.job.job_id), f.token, delivery.token, db
                )
                assert stopped["cancel_requested"] is True
            async with sessions() as db:
                with pytest.raises(HTTPException):
                    await jobs.download_compute_input(
                        UUID(delivery.job.job_id),
                        UUID(delivery.job.inputs[0].id),
                        f.token,
                        delivery.token,
                        db,
                    )
            payload = b'{"mean":5,"count":4,"uid":65532}'
            with pytest.raises(HTTPException):
                await upload(sessions, f, delivery, payload)
            async with sessions() as db:
                with pytest.raises(HTTPException) as wrong_lease:
                    await jobs.acknowledge_compute_cancellation(
                        UUID(delivery.job.job_id),
                        jobs.RunnerCancelled(reason="stopped"),
                        f.token,
                        "aicl_wrong",
                        db,
                    )
                assert wrong_lease.value.status_code == 401
            async with sessions() as db:
                receipt = await jobs.acknowledge_compute_cancellation(
                    UUID(delivery.job.job_id),
                    jobs.RunnerCancelled(reason="stopped"),
                    f.token,
                    delivery.token,
                    db,
                )
                assert receipt == {"status": "cancelled"}
            with pytest.raises(HTTPException):
                await submit_completion(
                    sessions,
                    f,
                    delivery,
                    completion(delivery, json.loads(payload), payload),
                )
            async with sessions() as db:
                run = await db.get(AnalysisRun, analysis_id)
                item = await db.get(
                    ResearchComputeJobOutput, UUID(delivery.job.outputs[0].id)
                )
                assert run.status == "cancelled" and run.result is None
                assert item.blob_id is item.data_asset_id is None

    asyncio.run(exercise())


def test_legacy_runner_cannot_lease_private_analysis_until_it_advertises_support():
    async def exercise():
        async with database() as sessions:
            f = await fixture(sessions)
            await confirmed(sessions, f)
            await report_runner(sessions, f.token)  # old SDK omits job_schemas
            async with sessions() as db:
                assert (await jobs.lease_compute_job(f.token, db))["job"] is None
            await report_runner(sessions, f.token, schemas=[ANALYSIS_JOB_SCHEMA])
            assert (await lease(sessions, f)).job.analysis_id is not None

    asyncio.run(exercise())


def test_concurrent_lease_requests_cannot_exceed_one_runner_slot():
    async def exercise():
        async with database() as sessions:
            f = await fixture(sessions)
            await confirmed(sessions, f, question="First approved synthetic run")
            await confirmed(sessions, f, question="Second approved synthetic run")

            async def attempt():
                async with sessions() as db:
                    return await jobs.lease_compute_job(f.token, db)

            deliveries = await asyncio.gather(attempt(), attempt())
            assert sum(item["job"] is not None for item in deliveries) == 1
            async with sessions() as db:
                active = await db.scalar(
                    select(func.count())
                    .select_from(ResearchComputeJob)
                    .where(
                        ResearchComputeJob.runner_id == f.compute.runner.id,
                        ResearchComputeJob.status == "leased",
                    )
                )
                assert active == 1

    asyncio.run(exercise())


def test_concurrent_streams_recheck_owner_quota_before_binding_private_blobs(
    monkeypatch,
):
    async def exercise():
        async with database() as sessions:
            f = await fixture(sessions)
            async with sessions() as db:
                runner = await db.get(ResearchComputeRunner, f.compute.runner.id)
                runner.max_concurrent_jobs = 2
                await db.commit()
            await report_runner(
                sessions, f.token, schemas=[ANALYSIS_JOB_SCHEMA], slots=2
            )
            await confirmed(sessions, f, question="First concurrent output")
            await confirmed(sessions, f, question="Second concurrent output")
            deliveries = [await lease(sessions, f), await lease(sessions, f)]
            for delivery in deliveries:
                await download_and_start(sessions, f, delivery)
            monkeypatch.setattr(config, "KNOWLEDGE_USER_FILE_COUNT_LIMIT", 1)
            barrier = asyncio.Barrier(2)
            payload = b'{"mean":3,"count":7,"uid":65532}'
            # Both real endpoints pass their first check before either consumes
            # the request stream; only the final binding lock can prevent overflow.
            outcomes = await asyncio.gather(
                *(
                    upload(sessions, f, item, payload, barrier=barrier)
                    for item in deliveries
                ),
                return_exceptions=True,
            )
            assert sum(isinstance(item, dict) for item in outcomes) == 1
            denied = [item for item in outcomes if isinstance(item, HTTPException)]
            assert len(denied) == 1 and denied[0].status_code == 413
            async with sessions() as db:
                count = await db.scalar(
                    select(func.count())
                    .select_from(ResearchComputeJobOutput)
                    .join(
                        ResearchComputeJob,
                        ResearchComputeJob.id
                        == ResearchComputeJobOutput.compute_job_id,
                    )
                    .where(
                        ResearchComputeJob.created_by_user_id == f.scope.analyst.id,
                        ResearchComputeJobOutput.blob_id.is_not(None),
                    )
                )
                assert count == 1

    asyncio.run(exercise())
