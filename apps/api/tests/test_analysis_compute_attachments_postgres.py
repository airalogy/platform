"""Actual attachment receipts, governed transport and opt-in isolated CSV execution.

No permissions, signatures, database, storage, preview or approval is mocked.
Synthetic receiver cases are labelled; only COMPUTE_ENGINE_TEST executes code.
"""

import asyncio
import copy
import hashlib
import io
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, Response, UploadFile
from sqlalchemy import delete, func, select
from starlette.datastructures import Headers

from app.models.airalogy_file import AiralogyFile
from app.models.analysis import AnalysisRun
from app.models.analysis_compute import AnalysisCompute, AnalysisComputeInputFile
from app.models.knowledge import ResearchFileBlob
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.research_execution import ResearchComputeJobInput
from app.routers import airalogy_files, analyses, analysis_compute, research_tasks
from app.routers import research_compute_jobs as jobs
from app.services.analysis_compute import analysis_compute_input_bytes
from app.services.analysis_compute_contracts import AnalysisComputeDraft
from app.services.analysis_compute_files import manifest_bytes
from app.services.analysis_engine import canonical_digest
from app.services.workflow_definitions import WorkflowDraft
from app.services.workflow_file_contracts import parse_workflow_file_id
from app.services.workflow_files import upload_file
from tests.test_analysis_compute_runtime_postgres import (
    completion,
    fixture,
    submit_completion,
    upload,
)
from tests.test_record_analysis_compute_postgres import compute_draft, decision_params
from tests.test_record_analysis_postgres import add_record, database
from tests.test_workflow_compute_methods_postgres import (
    compute_graph,
    publish_compute_method,
)
from tests.test_workflow_compute_runtime_postgres import queued
from tests.test_workflow_definitions_postgres import (
    actions_by_node,
    edge,
    node,
    publish,
    start_workflow,
    submit_record,
)
from tests.test_workflow_definitions_postgres import (
    deterministic_no_ai as deterministic_no_ai,  # noqa: PLC0414 -- pytest fixture re-export
)
from tests.test_workflow_definitions_postgres import (
    pytestmark as pytestmark,  # noqa: PLC0414
)
from tests.test_workflow_files_postgres import binding, read_response

SOURCE = """import csv, io, json, os
from pathlib import Path
assert os.getuid() == 65532
root = Path(os.environ['AIRALOGY_INPUT_DIR'])
snapshot = json.loads((root / 'records.json').read_text())
manifest = json.loads((root / 'attachments.json').read_text())
assert {r['record_id'] for r in snapshot['records']} == {r['record_id'] for r in manifest['files']}
values = []
for item in manifest['files']:
    assert item['input_id'] == 'measurements'
    path = root / item['mount_name']
    values.extend(float(row['value']) for row in csv.DictReader(io.StringIO(path.read_text())))
    for operation in (lambda: path.write_text('bad'), lambda: path.unlink(), lambda: path.chmod(0o666)):
        try:
            operation()
        except OSError:
            pass
        else:
            raise RuntimeError('approved input could be modified')
try:
    (root / 'unapproved.csv').write_text('bad')
except OSError:
    pass
else:
    raise RuntimeError('input directory is writable')
result = {'mean': sum(values)/len(values), 'count': len(values), 'uid': os.getuid()}
Path(os.environ['AIRALOGY_RESULT_JSON']).write_text(json.dumps(result))
Path('/airalogy/output/files/summary.json').write_text(json.dumps(result))
"""


async def csv_upload(sessions, scope, *, content=b"value\n11\n17\n"):
    async with sessions() as db:
        result = await airalogy_files.upload_airalogy_file(
            db,
            scope.owner,
            UploadFile(
                file=io.BytesIO(content),
                filename="measurements.csv",
                size=len(content),
                headers=Headers({"content-type": "text/csv"}),
            ),
            scope.protocol.id,
        )
        return result, content


async def attach_record(sessions, scope, record, *, content=b"value\n11\n17\n"):
    uploaded, content = await csv_upload(sessions, scope, content=content)
    async with sessions() as db:
        row = await db.get(Record, (record.id, record.version))
        data = copy.deepcopy(row.data)
        data["var"]["attachment"] = uploaded["airalogy_file_id"]
        row.data = data
        row.hash = canonical_digest(data)
        await db.commit()
        return row, content


async def attached_fixture(sessions, *, real_engine=False):
    f = await fixture(sessions, real_engine=real_engine)
    f.scope = SimpleNamespace(**{**vars(f.scope), "analyst": f.scope.owner})
    async with sessions() as db:
        version = await db.get(ProtocolVersion, f.scope.version.id)
        schema = copy.deepcopy(version.json_schema)
        schema["vars"]["properties"]["attachment"] = {
            "type": "string",
            "airalogy_type": "FileId",
            "file_extension": "csv",
        }
        version.json_schema = schema
        await db.commit()
        f.scope.version = version
    attached = [await attach_record(sessions, f.scope, record) for record in f.records]
    f.records = [record for record, _ in attached]
    return f


async def confirm_attached(sessions, f, *, approve=True):
    raw = compute_draft(f.scope, f.compute).model_dump(mode="json")
    raw["recipe"]["source_code"] = SOURCE
    raw["recipe"]["input_files"] = [
        {"input_id": "measurements", "field_path": ["var", "attachment"]}
    ]
    raw["selection"] = {
        "mode": "selected",
        "records": [
            {"id": str(record.id), "version": record.version} for record in f.records
        ],
    }
    async with sessions() as db:
        preview = await analysis_compute.preview_analysis_compute(
            AnalysisComputeDraft.model_validate(raw), db, f.scope.owner, Response()
        )
    async with sessions() as db:
        result = await analysis_compute.confirm_analysis_compute(
            analyses.AnalysisConfirmRequest(
                preview_id=preview["id"],
                preview_digest=preview["preview_digest"],
                client_idempotency_key=f"attachments-{uuid4().hex}",
            ),
            db,
            f.scope.owner,
            Response(),
        )
    identity = UUID(str(result["id"]))
    if approve:
        async with sessions() as db:
            detail = await analysis_compute.get_analysis_compute_approval(
                identity, db, f.scope.owner, Response()
            )
        async with sessions() as db:
            approved = await analysis_compute.decide_analysis_compute(
                identity, decision_params(detail), db, f.scope.owner, Response()
            )
            assert approved["job"]["status"] == "queued"
    return identity, preview


async def attachment_lease(sessions, f):
    from airalogy_compute_runner.models import ComputeJobEnvelope
    from airalogy_compute_runner.security import verify_job_signature

    async with sessions() as db:
        raw = await jobs.lease_compute_job(f.token, db)
    assert raw["job"] is not None
    verify_job_signature(raw["job"], raw["signature"], f.token)
    job = ComputeJobEnvelope.parse(raw["job"])
    assert len(job.inputs) == len(f.records) + 2
    assert [item.mount_name for item in job.inputs[:2]] == [
        "records.json",
        "attachments.json",
    ]
    return SimpleNamespace(raw=raw, job=job, token=raw["lease_token"])


async def download_inputs(sessions, f, delivery, *, start=True):
    payloads = {}
    for item in delivery.job.inputs:
        async with sessions() as db:
            response = await jobs.download_compute_input(
                UUID(delivery.job.job_id), UUID(item.id), f.token, delivery.token, db
            )
            payload = (
                response.body
                if hasattr(response, "body")
                else await read_response(response)
            )
        assert len(payload) == item.byte_size
        assert hashlib.sha256(payload).hexdigest() == item.checksum_sha256
        payloads[item.id] = payload
    async with sessions() as db:
        run = await db.get(AnalysisRun, UUID(delivery.job.analysis_id))
        details = await db.get(AnalysisCompute, run.id)
        assert payloads[delivery.job.inputs[0].id] == analysis_compute_input_bytes(run)
        assert payloads[delivery.job.inputs[1].id] == manifest_bytes(
            details.input_file_manifest
        )
        assert {item["record_id"] for item in details.input_file_manifest["files"]} == {
            str(record.id) for record in f.records
        }
    if start:
        async with sessions() as db:
            assert (
                await jobs.start_compute_job(
                    UUID(delivery.job.job_id), f.token, delivery.token, db
                )
            )["status"] == "running"
    return payloads


def execute_attachments(delivery, payloads):
    """Run exactly the signed source in the shipping pinned OCI engine."""
    from airalogy_compute_runner.config import RunnerConfig
    from airalogy_compute_runner.engine import ContainerEngine

    with tempfile.TemporaryDirectory(prefix="analysis-attachments-pg-") as temporary:
        root = Path(temporary)
        paths = {}
        for identity, payload in payloads.items():
            paths[identity] = root / identity
            paths[identity].write_bytes(payload)
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
            engine.populate_workspace(job, volume, paths)
            process = engine.start(job, container, volume)
            assert process.process.wait(timeout=60) == 0, engine.stderr_tail(process)
            result, _ = engine.read_result(job, volume)
            size, checksum = engine.output_metadata(job.outputs[0], volume)
            streamed = engine.open_output(job.outputs[0], volume)
            payload = streamed.stream.read(job.outputs[0].max_bytes + 1)
            engine.finish_output(streamed)
            assert (
                len(payload) == size and hashlib.sha256(payload).hexdigest() == checksum
            )
            assert json.loads(payload) == result
            return result, payload
        finally:
            engine.cleanup(container, volume)


async def complete_attachments(
    sessions, f, delivery, payloads, *, real_engine=False, mean=14.0, count=8
):
    if real_engine:
        result, payload = execute_attachments(delivery, payloads)
    else:
        # This branch validates receiver behavior, not execution of reviewed code.
        result = {"mean": mean, "count": count, "uid": 65532}
        payload = json.dumps(result).encode()
    assert result == {"mean": mean, "count": count, "uid": 65532}
    await upload(sessions, f, delivery, payload)
    receipt = completion(delivery, result, payload)
    assert (await submit_completion(sessions, f, delivery, receipt))[
        "status"
    ] == "completed"
    # A lost completion response must not produce a second computation or receipt.
    assert (await submit_completion(sessions, f, delivery, receipt))[
        "status"
    ] == "completed"
    async with sessions() as db:
        run = await db.get(AnalysisRun, UUID(delivery.job.analysis_id))
        details = await db.get(AnalysisCompute, run.id)
        report = await analyses.download_record_analysis(run.id, db, f.scope.owner)
        exported = json.loads(report.body)
        assert exported["result"]["input_files"] == details.input_file_manifest
        assert exported["result_digest"] == canonical_digest(exported["result"])
        assert all(
            key not in report.body.decode()
            for key in ("storage_object_key", "storage_backend", "blob_id")
        )
    return payload


def test_private_attachment_transport_and_export_preserve_exact_approved_inputs():
    async def exercise():
        async with database() as sessions:
            f = await attached_fixture(sessions)
            file_id, _ = parse_workflow_file_id(f.records[0].data["var"]["attachment"])
            async with sessions() as db:
                renamed = await airalogy_files.update_airalogy_file_url(
                    file_id, "editable_before_confirmation.csv", db, f.scope.owner
                )
                assert renamed["filename"] == "editable_before_confirmation.csv"
            identity, preview = await confirm_attached(sessions, f)
            async with sessions() as db:
                with pytest.raises(HTTPException) as immutable:
                    await airalogy_files.update_airalogy_file_url(
                        file_id, "cannot_change_approved_name.csv", db, f.scope.owner
                    )
                assert immutable.value.status_code == 409
                assert "Analysis-bound" in immutable.value.detail
                assert (
                    await db.get(AiralogyFile, file_id)
                ).filename == "editable_before_confirmation.csv"
            async with sessions() as db:
                details = await db.get(AnalysisCompute, identity)
                assert (
                    preview["summary"]["compute"]["input_files"]
                    == details.input_file_manifest
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisComputeInputFile)
                        .where(AnalysisComputeInputFile.analysis_run_id == identity)
                    )
                    == 4
                )
            delivery = await attachment_lease(sessions, f)
            payloads = await download_inputs(sessions, f, delivery)
            await complete_attachments(sessions, f, delivery, payloads)

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "fault", ["revoked_record", "changed_record", "missing_receipt"]
)
def test_sealed_attachment_source_loss_cannot_download_or_start(fault):
    async def exercise():
        async with database() as sessions:
            f = await attached_fixture(sessions)
            identity, _ = await confirm_attached(sessions, f)
            delivery = await attachment_lease(sessions, f)
            async with sessions() as db:
                if fault == "missing_receipt":
                    # Normal input cleanup cascades its receipt. A previously
                    # issued signed lease must not authorize now-missing inputs.
                    await db.execute(
                        delete(ResearchComputeJobInput).where(
                            ResearchComputeJobInput.id
                            == UUID(delivery.job.inputs[2].id)
                        )
                    )
                else:
                    record = await db.get(
                        Record, (f.records[0].id, f.records[0].version)
                    )
                    if fault == "revoked_record":
                        record.deleted_at = datetime.now(UTC).replace(tzinfo=None)
                    else:
                        record.data = {"var": {"value": -1}}
                        record.hash = canonical_digest(record.data)
                await db.commit()
            async with sessions() as db:
                with pytest.raises(HTTPException):
                    await jobs.download_compute_input(
                        UUID(delivery.job.job_id),
                        UUID(delivery.job.inputs[-1].id),
                        f.token,
                        delivery.token,
                        db,
                    )
            async with sessions() as db:
                with pytest.raises(HTTPException):
                    await jobs.start_compute_job(
                        UUID(delivery.job.job_id), f.token, delivery.token, db
                    )
            async with sessions() as db:
                assert (await db.get(AnalysisRun, identity)).result is None

    asyncio.run(exercise())


def test_attachment_approval_rechecks_actual_record_permission():
    async def exercise():
        async with database() as sessions:
            f = await attached_fixture(sessions)
            identity, _ = await confirm_attached(sessions, f, approve=False)
            async with sessions() as db:
                detail = await analysis_compute.get_analysis_compute_approval(
                    identity, db, f.scope.owner, Response()
                )
            async with sessions() as db:
                record = await db.get(Record, (f.records[0].id, f.records[0].version))
                record.deleted_at = datetime.now(UTC).replace(tzinfo=None)
                await db.commit()
            async with sessions() as db:
                with pytest.raises(HTTPException):
                    await analysis_compute.decide_analysis_compute(
                        identity, decision_params(detail), db, f.scope.owner, Response()
                    )
            async with sessions() as db:
                assert (
                    await db.get(AnalysisCompute, identity)
                ).approval_state == "pending"
                assert (await db.get(AnalysisRun, identity)).result is None

    asyncio.run(exercise())


def test_attachment_storage_bytes_are_verified_before_any_download_response():
    async def exercise():
        async with database() as sessions:
            f = await attached_fixture(sessions)
            content = f"value\n{uuid4().int}\n".encode()
            record, _ = await attach_record(
                sessions, f.scope, f.records[0], content=content
            )
            f.records = [record]
            identity, _ = await confirm_attached(sessions, f)
            delivery = await attachment_lease(sessions, f)
            async with sessions() as db:
                receipt = await db.get(
                    AnalysisComputeInputFile, UUID(delivery.job.inputs[2].id)
                )
                blob = await db.get(ResearchFileBlob, receipt.blob_id)
            # Mutate this test's unique managed object, never a user blob. The
            # immutable receipt remains unchanged, exercising actual byte hash.
            try:
                await upload_file(
                    blob.storage_object_key,
                    io.BytesIO(b"x" * len(content)),
                    content_type=blob.content_type,
                    length=len(content),
                )
                async with sessions() as db:
                    with pytest.raises(HTTPException) as caught:
                        await jobs.download_compute_input(
                            UUID(delivery.job.job_id),
                            UUID(delivery.job.inputs[2].id),
                            f.token,
                            delivery.token,
                            db,
                        )
                    assert caught.value.status_code == 409
                async with sessions() as db:
                    assert (await db.get(AnalysisRun, identity)).result is None
            finally:
                await upload_file(
                    blob.storage_object_key,
                    io.BytesIO(content),
                    content_type=blob.content_type,
                    length=len(content),
                )

    asyncio.run(exercise())


async def attachment_workflow(sessions, *, real_engine=False):
    f = await attached_fixture(sessions, real_engine=real_engine)
    identity, _ = await confirm_attached(sessions, f)
    delivery = await attachment_lease(sessions, f)
    payloads = await download_inputs(sessions, f, delivery)
    # Persisted prior method: explicitly synthetic receiver, not a model or code run.
    await complete_attachments(sessions, f, delivery, payloads)
    async with sessions() as db:
        saved = await analyses.create_analysis_pipeline(
            analyses.PipelineCreateRequest(
                run_id=identity, title="Exact CSV attachment method"
            ),
            db,
            f.scope.owner,
        )
    declarations = [{"input_id": "measurements", "field_path": ["var", "attachment"]}]
    assert saved["current_recipe"]["input_files"] == declarations
    assert saved["revisions"][0]["recipe"]["input_files"] == declarations
    method, _ = await publish_compute_method(sessions, f, saved)
    assert method["recipe"]["input_files"] == declarations
    async with sessions() as db:
        target = Protocol(
            id=uuid4(),
            project_id=f.scope.project.id,
            user_id=f.scope.owner.id,
            uid=f"csv_target_{uuid4().hex}",
            name="Attachment computation receiver",
            latest_version="1.0.0",
        )
        db.add(target)
        await db.flush()
        version = ProtocolVersion(
            id=uuid4(),
            protocol_id=target.id,
            version="1.0.0",
            json_schema={
                "vars": {
                    "type": "object",
                    "properties": {
                        "attachment": {
                            "type": "string",
                            "airalogy_type": "FileId",
                            "file_extension": "json",
                        }
                    },
                }
            },
            fields={},
            assigners={},
            assigner_graph={},
            aimd="Computed attachment receipt",
            meta_data={"id": target.uid, "version": "1.0.0", "name": target.name},
        )
        db.add(version)
        await db.commit()
    target_scope = SimpleNamespace(
        **{**vars(f.scope), "protocol": target, "version": version}
    )
    graph = compute_graph(f, method)
    graph["schema_version"] = 4
    graph["nodes"][1]["compute_file_outputs"] = [
        {"output_id": "summary_file", "mount_name": "summary.json"}
    ]
    graph["nodes"].append(node(target_scope, "next"))
    graph["edges"].append(edge("analysis", "next"))
    graph["bindings"] = [
        binding("analysis", "next", source_field="summary_file", kind="analysis")
    ]
    workflow, _ = await publish(
        sessions,
        f.scope,
        WorkflowDraft(
            project_id=f.scope.project.id,
            title="Record CSV to computed file",
            graph=graph,
        ),
    )
    params = research_tasks.ResearchTaskDraft(
        project_id=f.scope.project.id,
        title="Explicit attachment chain",
        goal="Read only the declared source CSV and hand verified output to a Protocol",
        success_criteria=["Exact output file and original input lineage"],
        protocol_ids=[f.scope.protocol.id, target.id],
        compute_environment_revision_ids=[f.compute.revision.id],
        budget_limit="1",
        budget_currency="USD",
    )
    async with sessions() as db:
        preview = await research_tasks.preview_research_task(params, f.scope.owner, db)
        task = await research_tasks.create_research_task(
            research_tasks.ResearchTaskCreate(
                **params.model_dump(), preview_digest=preview["preview_digest"]
            ),
            f.scope.owner,
            db,
        )
    started, _ = await start_workflow(sessions, f.scope, workflow, task)
    actions = await actions_by_node(sessions, started["run_id"])
    record = await add_record(sessions, f.scope, 9000, author=f.scope.owner, number=5)
    record, _ = await attach_record(
        sessions, f.scope, record, content=b"value\n40\n44\n"
    )
    f.records = [record]
    await submit_record(sessions, f.scope, actions["source"].id, record)
    return f, started, await actions_by_node(sessions, started["run_id"])


@pytest.mark.parametrize(
    "real_engine",
    [
        False,
        pytest.param(
            True,
            marks=pytest.mark.skipif(
                os.environ.get("COMPUTE_ENGINE_TEST") != "1",
                reason="Requires fixed Python OCI environment",
            ),
        ),
    ],
)
def test_record_csv_to_compute_to_downstream_protocol_has_readonly_inputs_and_lineage(
    real_engine,
):
    async def exercise():
        async with database() as sessions:
            sessions.configure(autoflush=False)
            f, started, actions = await attachment_workflow(
                sessions, real_engine=real_engine
            )
            await queued(sessions, f, actions)
            delivery = await attachment_lease(sessions, f)
            payloads = await download_inputs(sessions, f, delivery)
            output = await complete_attachments(
                sessions,
                f,
                delivery,
                payloads,
                real_engine=real_engine,
                mean=42.0,
                count=2,
            )
            actions = await actions_by_node(sessions, started["run_id"])
            assert actions["next"].status == "proposed"
            alias, _ = parse_workflow_file_id(
                actions["next"].input_data["initial_values"]["attachment"]
            )
            async with sessions() as db:
                response = await airalogy_files.download_airalogy_file(
                    alias, db, f.scope.owner
                )
                assert await read_response(response) == output
            # The output alias is not a new grant to its original CSV sources.
            async with sessions() as db:
                record = await db.get(Record, (f.records[0].id, f.records[0].version))
                record.deleted_at = datetime.now(UTC).replace(tzinfo=None)
                await db.commit()
            async with sessions() as db:
                with pytest.raises(HTTPException):
                    await airalogy_files.download_airalogy_file(
                        alias, db, f.scope.owner
                    )

    asyncio.run(exercise())
