"""Focused signed transport and post-I/O authorization boundaries for attachments."""

import asyncio
import hashlib
import io
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers import airalogy_files
from app.routers import research_compute_jobs as routes
from app.services import analysis_compute_files as files
from app.services import analysis_compute_runtime as runtime
from app.services import workflow_compute_runtime, workflow_files
from app.services.analysis_compute import analysis_compute_input_bytes
from app.services.research_compute_contracts import (
    ComputeInputDraft,
    ComputeOutputDraft,
    validate_compute_action_payload,
)
from tests.test_analysis_compute_runtime import output, state


def inputs():
    run, job, details, runner, _, db = state()
    content = b"value\n11\n17\n"
    blob = SimpleNamespace(
        id=uuid4(),
        content_type="text/csv",
        size_bytes=len(content),
        checksum_sha256=hashlib.sha256(content).hexdigest(),
        storage_object_key="must-never-reach-runner",
    )
    source = {
        "input_id": "measurements",
        "field_path": ["var", "attachment"],
        "record_id": str(uuid4()),
        "record_version": 1,
        "record_hash": "a" * 64,
        "protocol_version": "1.0.0",
        "file_id": str(uuid4()),
        "filename": "measurements.csv",
        "media_type": blob.content_type,
        "byte_size": blob.size_bytes,
        "checksum_sha256": blob.checksum_sha256,
        "mount_name": "measurements_record_v1.csv",
        "file_metadata_digest": "b" * 64,
    }
    details.input_file_manifest = files._envelope([source])
    rows = [
        SimpleNamespace(
            id=uuid4(),
            position=position,
            compute_job_id=job.id,
            analysis_run_id=run.id,
            data_asset_id=None,
            data_asset_version_id=None,
            mount_name=name,
        )
        for position, name in enumerate(
            ("records.json", "attachments.json", source["mount_name"]), 1
        )
    ]
    return run, job, details, runner, db, rows, blob, content


def test_server_rejects_reserved_parameter_mount_but_allows_output_name():
    with pytest.raises(ValueError, match="reserved"):
        ComputeInputDraft(data_asset_version_id=uuid4(), mount_name=" input.json ")
    with pytest.raises(ValueError, match="reserved"):
        validate_compute_action_payload(
            source_code="print(1)",
            source_byte_limit=200_000,
            input_payload={},
            input_assets=[
                ComputeInputDraft.model_construct(
                    data_asset_version_id=uuid4(), mount_name="input.json"
                )
            ],
            output_files=[],
        )
    assert (
        ComputeOutputDraft(
            mount_name="input.json",
            asset_name="Result",
            media_type="application/json",
            max_bytes=1024,
        ).mount_name
        == "input.json"
    )


@pytest.mark.parametrize("bound", [False, True])
def test_file_rename_checks_analysis_receipt_under_source_lock(monkeypatch, bound):
    async def exercise():
        user = SimpleNamespace(id=uuid4())
        file = SimpleNamespace(
            id=uuid4(),
            user_id=user.id,
            filename="source.csv",
            content_type="text/csv",
            storage_backend="minio",
            local_url=AsyncMock(return_value="/safe/file"),
            reference_payload=lambda **kwargs: {"filename": "renamed.csv"},
        )
        monkeypatch.setattr(
            airalogy_files.AiralogyFile, "find", AsyncMock(return_value=file)
        )
        db = SimpleNamespace(
            scalar=AsyncMock(side_effect=[file, None, uuid4() if bound else None]),
            commit=AsyncMock(),
        )
        if bound:
            with pytest.raises(HTTPException) as caught:
                await airalogy_files.update_airalogy_file_url(
                    file.id, "renamed.csv", db, user
                )
            assert caught.value.status_code == 409
            assert file.filename == "source.csv"
            db.commit.assert_not_awaited()
        else:
            result = await airalogy_files.update_airalogy_file_url(
                file.id, "renamed.csv", db, user
            )
            assert result["filename"] == file.filename == "renamed.csv"
            db.commit.assert_awaited_once()
        assert "FOR UPDATE" in str(db.scalar.await_args_list[0].args[0])
        assert "analysis_compute_input_files.source_file_id" in str(
            db.scalar.await_args_list[-1].args[0]
        )

    asyncio.run(exercise())


def test_sealed_report_keeps_deep_copied_attachment_mapping(monkeypatch):
    async def exercise():
        run, job, details, _, db, _, _, _ = inputs()
        item, blob, receipt = output()
        expected = deepcopy(details.input_file_manifest)
        monkeypatch.setattr(runtime, "emit_analysis_compute_event", AsyncMock())
        monkeypatch.setattr(workflow_compute_runtime, "terminal_compute", AsyncMock())
        await runtime.seal_analysis_completion(
            db,
            job,
            run,
            details,
            result={"mean": 14},
            usage={"wall_seconds": 1, "output_bytes": 25},
            rows=[(item, blob)],
            outputs=[receipt],
        )
        assert run.result["input_files"] == expected
        details.input_file_manifest["files"][0]["filename"] = "later-changed"
        assert run.result["input_files"] == expected

    asyncio.run(exercise())


def test_multi_input_signature_preserves_old_records_bytes_and_safe_manifest(
    monkeypatch,
):
    async def exercise():
        run, job, details, _, db, rows, blob, content = inputs()
        sealed = AsyncMock(
            return_value=(SimpleNamespace(snapshot={"media_type": "text/csv"}), blob)
        )
        blob.content_type = "application/octet-stream"
        monkeypatch.setattr(files, "sealed_input_file", sealed)
        manifests = await runtime.analysis_input_manifests(
            db, job, run, details, list(reversed(rows))
        )
        assert manifests[0] == runtime.analysis_input_manifest(job, run, rows[0])
        original = analysis_compute_input_bytes(run)
        assert manifests[0]["checksum_sha256"] == hashlib.sha256(original).hexdigest()
        manifest_payload = files.manifest_bytes(details.input_file_manifest)
        assert (
            manifests[1]["checksum_sha256"]
            == hashlib.sha256(manifest_payload).hexdigest()
        )
        assert manifests[2]["byte_size"] == len(content)
        assert manifests[2]["media_type"] == "text/csv"
        assert manifests[2]["checksum_sha256"] == hashlib.sha256(content).hexdigest()
        assert "storage_object_key" not in json.dumps(manifests)
        assert "must-never-reach-runner" not in manifest_payload.decode()
        assert [row["mount_name"] for row in manifests] == [
            row.mount_name for row in rows
        ]
        sealed.assert_awaited_once_with(db, run, rows[2])

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "change", ["missing", "extra", "position", "duplicate", "foreign", "reserved"]
)
def test_changed_input_set_is_rejected_before_transport(monkeypatch, change):
    async def exercise():
        run, job, details, _, db, rows, blob, _ = inputs()
        monkeypatch.setattr(
            files,
            "sealed_input_file",
            AsyncMock(
                return_value=(
                    SimpleNamespace(snapshot={"media_type": "text/csv"}),
                    blob,
                )
            ),
        )
        if change == "missing":
            rows.pop()
        elif change == "extra":
            rows.append(deepcopy(rows[-1]))
        elif change == "position":
            rows[-1].position = 4
        elif change == "duplicate":
            rows[-1].mount_name = rows[1].mount_name
        elif change == "foreign":
            rows[-1].analysis_run_id = uuid4()
        else:
            rows[-1].mount_name = "input.json"
        with pytest.raises(HTTPException) as caught:
            await runtime.analysis_input_manifests(db, job, run, details, rows)
        assert caught.value.status_code == 409

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "failure",
    [None, "revoked_after_io", "corrupted_bytes", "missing_receipt", "commit"],
)
def test_download_verifies_bytes_then_reauthorizes_before_disclosure(
    monkeypatch, failure
):
    async def exercise():
        run, job, details, runner, db, rows, blob, content = inputs()
        db.scalar.return_value = rows[2]
        monkeypatch.setattr(
            routes, "authenticate_compute_runner", AsyncMock(return_value=runner)
        )
        monkeypatch.setattr(
            routes,
            "_runner_job_context",
            AsyncMock(return_value=(job, None, None, None)),
        )
        authority = AsyncMock(
            side_effect=[(run, details), HTTPException(403, "Revoked")]
            if failure == "revoked_after_io"
            else None,
            return_value=(run, details),
        )
        monkeypatch.setattr(routes, "_authorize_analysis_request", authority)
        monkeypatch.setattr(routes, "emit_analysis_compute_event", AsyncMock())
        sealed = AsyncMock(
            return_value=(SimpleNamespace(snapshot={"media_type": "text/csv"}), blob)
        )
        if failure == "missing_receipt":
            sealed.side_effect = HTTPException(409, "Missing sealed receipt")
        monkeypatch.setattr(files, "sealed_input_file", sealed)
        handle = io.BytesIO(content)
        spool = AsyncMock(return_value=handle)
        if failure == "corrupted_bytes":
            spool.side_effect = HTTPException(409, "Stored bytes changed")
        monkeypatch.setattr(workflow_files, "verified_blob_spool", spool)
        if failure == "commit":
            db.commit.side_effect = RuntimeError("audit transaction failed")
        if failure:
            with pytest.raises((HTTPException, RuntimeError)):
                await routes.download_compute_input(
                    job.id, rows[2].id, "runner", "lease", db
                )
            if failure in {"revoked_after_io", "commit"}:
                assert handle.closed
            if failure == "missing_receipt":
                spool.assert_not_awaited()
            return
        response = await routes.download_compute_input(
            job.id, rows[2].id, "runner", "lease", db
        )
        assert authority.await_count == 2
        assert response.headers["X-Content-SHA256"] == blob.checksum_sha256
        assert response.headers["Content-Length"] == str(len(content))
        assert b"".join([chunk async for chunk in response.body_iterator]) == content
        assert handle.closed
        db.commit.assert_awaited_once()

    asyncio.run(exercise())
