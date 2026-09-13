"""Private lifecycle adapter for the existing isolated Compute Job transport.

This module never executes source, publishes a ResearchFile/DataAsset, or writes
to a Research Task. Runner authentication, leases and transport stay shared.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from app.models.analysis import AnalysisRun
from app.models.analysis_compute import AnalysisCompute
from app.models.research_execution import (
    ResearchComputeEnvironmentRevision,
    ResearchComputeRunnerEnvironment,
)
from app.services.analysis_compute import (
    analysis_compute_input_bytes,
    authorize_compute_execution,
    emit_analysis_compute_event,
    money,
)
from app.services.analysis_compute_contracts import (
    ANALYSIS_JOB_SCHEMA,
    ATTACHMENT_MANIFEST_FILENAME,
    MAX_ANALYSIS_INPUT_FILES,
    SOURCE_FILENAME,
)
from app.services.analysis_engine import canonical_digest
from app.services.record_analyses import utcnow
from app.services.research_compute_jobs import (
    compute_actual_cost,
    compute_output_snapshot,
)

RESEARCH_JOB_SCHEMA = "airalogy.compute-job.v1"


def runner_job_schemas(runner) -> list[str]:
    return (runner.last_report or {}).get("job_schemas", [RESEARCH_JOB_SCHEMA])


async def analysis_runtime_context(db, job):
    """Load lifecycle state without source permissions, so revocation can stop work."""
    if job.analysis_run_id is None or job.action_id is not None:
        raise HTTPException(409, "Private Compute context is invalid")
    run = await db.scalar(
        select(AnalysisRun)
        .where(AnalysisRun.id == job.analysis_run_id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if run is None:
        raise HTTPException(409, "Private Compute context is missing")
    return run


async def authorize_analysis_runtime(db, job, runner, *, check_deadline=True):
    run, details = await authorize_compute_execution(
        db, job, check_deadline=check_deadline
    )
    from app.services.workflow_compute_runtime import authorize_workflow_compute

    await authorize_workflow_compute(db, job)
    metadata = (job.environment_snapshot or {}).get("metadata") or {}
    revision = await db.get(
        ResearchComputeEnvironmentRevision,
        job.compute_environment_revision_id,
        populate_existing=True,
    )
    binding = await db.scalar(
        select(ResearchComputeRunnerEnvironment.id).where(
            ResearchComputeRunnerEnvironment.runner_id == runner.id,
            ResearchComputeRunnerEnvironment.compute_environment_revision_id
            == job.compute_environment_revision_id,
            ResearchComputeRunnerEnvironment.lab_id == runner.lab_id,
            ResearchComputeRunnerEnvironment.archived_at.is_(None),
        )
    )
    if (
        ANALYSIS_JOB_SCHEMA not in runner_job_schemas(runner)
        or not runner.enabled
        or runner.revoked_at is not None
        or str(runner.lab_id) != metadata.get("lab_id")
        or binding is None
        or revision is None
        or revision.runner_protocol_version != runner.runner_protocol_version
    ):
        raise HTTPException(
            403, "Compute Runner no longer has analysis execution authority"
        )
    return run, details


def analysis_input_manifest(job, run, input_row):
    if (
        input_row is None
        or input_row.analysis_run_id != run.id
        or input_row.compute_job_id != job.id
        or input_row.data_asset_id is not None
        or input_row.data_asset_version_id is not None
        or input_row.mount_name != SOURCE_FILENAME
    ):
        raise HTTPException(409, "Private Compute source binding changed")
    payload = analysis_compute_input_bytes(run)
    return {
        "id": str(input_row.id),
        "mount_name": SOURCE_FILENAME,
        "filename": SOURCE_FILENAME,
        "media_type": "application/json",
        "byte_size": len(payload),
        "checksum_sha256": hashlib.sha256(payload).hexdigest(),
        "download_path": f"/compute-runner/v1/jobs/{job.id}/inputs/{input_row.id}",
    }


async def additional_analysis_input(db, job, run, details, input_row):
    """Resolve one sealed attachment input; never authorize by a storage key."""
    from app.services.analysis_compute_files import manifest_bytes, sealed_input_file

    envelope = details.input_file_manifest
    if (
        not envelope
        or input_row is None
        or input_row.analysis_run_id != run.id
        or input_row.compute_job_id != job.id
        or input_row.data_asset_id is not None
        or input_row.data_asset_version_id is not None
    ):
        raise HTTPException(409, "Compute attachment source binding changed")
    if input_row.position == 2 and input_row.mount_name == ATTACHMENT_MANIFEST_FILENAME:
        payload = manifest_bytes(envelope)
        blob = None
        media_type = "application/json"
        size = len(payload)
        checksum = hashlib.sha256(payload).hexdigest()
    elif input_row.position >= 3 and input_row.mount_name not in {
        SOURCE_FILENAME,
        ATTACHMENT_MANIFEST_FILENAME,
        "input.json",
    }:
        receipt, blob = await sealed_input_file(db, run, input_row)
        payload = None
        # Deduplicated physical storage does not own logical file metadata.
        # Serve the exact MIME type approved for this attachment occurrence.
        media_type = receipt.snapshot["media_type"]
        size = blob.size_bytes
        checksum = blob.checksum_sha256
    else:
        raise HTTPException(409, "Compute attachment position or name changed")
    manifest = {
        "id": str(input_row.id),
        "mount_name": input_row.mount_name,
        "filename": input_row.mount_name,
        "media_type": media_type,
        "byte_size": size,
        "checksum_sha256": checksum,
        "download_path": f"/compute-runner/v1/jobs/{job.id}/inputs/{input_row.id}",
    }
    return manifest, payload, blob


async def analysis_input_manifests(db, job, run, details, input_rows):
    """Extend the existing signed multi-input transport without changing v1 JSON."""
    envelope = details.input_file_manifest
    rows = sorted(input_rows, key=lambda item: item.position)
    if (
        not isinstance(envelope, dict)
        or not isinstance(envelope.get("files"), list)
        or not 1 <= len(envelope["files"]) <= MAX_ANALYSIS_INPUT_FILES
        or len(rows) != len(envelope["files"]) + 2
        or [item.position for item in rows] != list(range(1, len(rows) + 1))
        or len({item.mount_name for item in rows}) != len(rows)
    ):
        raise HTTPException(409, "Compute attachment input set changed")
    manifests = [analysis_input_manifest(job, run, rows[0])]
    for row in rows[1:]:
        manifest, _payload, _blob = await additional_analysis_input(
            db, job, run, details, row
        )
        manifests.append(manifest)
    return manifests


def verified_output_receipts(rows, completed_outputs):
    """The same exact upload receipts gate both public and private completion."""
    provided = {item.output_id: item for item in completed_outputs}
    if len(provided) != len(completed_outputs):
        raise HTTPException(422, "Completed Compute outputs must be unique")
    if set(provided) - {output.id for output, _ in rows}:
        raise HTTPException(422, "Compute output was not declared")
    uploaded = []
    for output, blob in rows:
        completion = provided.get(output.id)
        if blob is None:
            if output.required:
                raise HTTPException(
                    422, f"Required Compute output {output.mount_name} was not uploaded"
                )
            if completion is not None:
                raise HTTPException(
                    422, "Compute completion references an output that was not uploaded"
                )
            continue
        if completion is None:
            raise HTTPException(
                422,
                f"Uploaded Compute output {output.mount_name} is missing from completion",
            )
        if (
            completion.checksum_sha256 != blob.checksum_sha256
            or completion.byte_size != blob.size_bytes
            or blob.content_type != output.media_type
            or blob.size_bytes > output.max_bytes
        ):
            raise HTTPException(
                422, f"Compute output {output.mount_name} changed after upload"
            )
        uploaded.append((output, blob))
    return uploaded


def private_output_manifest(rows):
    manifest = []
    for output, blob in rows:
        if any(
            (
                output.research_file_id,
                output.data_asset_id,
                output.data_asset_version_id,
            )
        ):
            raise HTTPException(
                409, "Private Compute output acquired a shared asset binding"
            )
        item = compute_output_snapshot(output, blob)
        for key in ("research_file_id", "data_asset_id", "data_asset_version_id"):
            item.pop(key)
        if output.registered_at is not None:
            if blob is None:
                raise HTTPException(409, "Private Compute registered output is missing")
            item["status"] = "registered"
        manifest.append(item)
    return manifest


def private_actual_cost(job, details, wall_seconds):
    actual = compute_actual_cost(job, wall_seconds)
    if actual is not None:
        if not actual.is_finite() or actual < 0:
            raise HTTPException(422, "Compute cost is invalid")
        actual = Decimal(money(actual))
        if job.estimated_cost is None or actual > Decimal(job.estimated_cost):
            raise HTTPException(422, "Compute cost exceeds the approved estimate")
    if details.max_cost is not None and (
        actual is None
        or job.currency != details.budget_currency
        or actual > details.max_cost
    ):
        raise HTTPException(422, "Compute cost exceeds its approved ceiling")
    return actual


async def invalidate_analysis_execution(db, job, *, reason):
    """Stop further reads/runs after revocation without requiring revoked grants."""
    if job.status in {"completed", "failed", "cancelled", "cancel_requested"}:
        return
    if job.status in {"leased", "running"}:
        job.status = "cancel_requested"
        job.cancel_reason = reason
        job.cancel_requested_at = utcnow()
        job.revision += 1
        await emit_analysis_compute_event(
            db,
            job.analysis_run_id,
            "compute.cancel_requested",
            payload={"reason": reason},
            key=f"runtime-cancel:{job.revision}",
        )
    else:
        await finish_analysis_failure(db, job, error=reason)


async def finish_analysis_failure(
    db, job, *, error, usage=None, cancelled=False, uncertain=False
):
    if job.status in {"completed", "failed", "cancelled"}:
        raise HTTPException(409, "Private Compute Job is already final")
    run = await analysis_runtime_context(db, job)
    if run.result is not None or run.status == "succeeded":
        raise HTTPException(409, "Private Compute result is already sealed")
    details = await db.get(AnalysisCompute, run.id, populate_existing=True)
    if usage is not None and details is not None:
        job.actual_cost = private_actual_cost(job, details, usage["wall_seconds"])
    job.usage = usage or {}
    job.status = "cancelled" if cancelled else "failed"
    job.error = None if cancelled else error
    if cancelled:
        job.cancel_reason = error
    job.completed_at = utcnow()
    job.lease_expires_at = None
    job.revision += 1
    run.status = job.status
    run.error = error
    run.finished_at = job.completed_at
    await emit_analysis_compute_event(
        db,
        run.id,
        f"compute.{job.status}",
        payload={"reason": error, "uncertain": uncertain, "usage": job.usage},
        key=f"terminal:{job.status}",
    )
    from app.services.workflow_compute_runtime import terminal_compute

    await terminal_compute(db, job, run, usage=usage, uncertain=uncertain)


async def seal_analysis_completion(
    db, job, run, details, *, result, usage, rows, outputs
):
    if job.status != "running" or run.status != "running" or run.result is not None:
        raise HTTPException(409, "Private Compute result cannot be replaced")
    try:
        canonical_digest(result)
        canonical_digest(usage)
    except (TypeError, ValueError) as error:
        raise HTTPException(
            422, "Compute result must contain finite JSON values"
        ) from error
    uploaded = verified_output_receipts(rows, outputs)
    # Validate destination bindings before changing any output state.
    private_output_manifest(rows)
    cost = private_actual_cost(job, details, usage["wall_seconds"])
    now = utcnow()
    for output, _ in uploaded:
        output.registered_at = now
    manifest = private_output_manifest(rows)
    sealed = {
        "computed_result": result,
        "outputs": manifest,
        "usage": usage,
        "actual_cost": str(cost) if cost is not None else None,
        "currency": job.currency,
    }
    if getattr(details, "input_file_manifest", None):
        # This is the approved public mapping, not storage keys or blob lineage.
        # Keep it in the canonical report so ordinary exports preserve inputs.
        sealed["input_files"] = deepcopy(details.input_file_manifest)
    digest = canonical_digest(sealed)
    job.status = "completed"
    job.result = result
    job.usage = usage
    job.actual_cost = cost
    job.output_manifest = manifest
    job.error = None
    job.completed_at = now
    job.lease_expires_at = None
    job.revision += 1
    run.status = "succeeded"
    run.result = sealed
    run.result_digest = digest
    run.error = None
    run.finished_at = now
    await emit_analysis_compute_event(
        db,
        run.id,
        "compute.completed",
        payload={"compute_job_id": str(job.id), "result_digest": digest},
        key="completed",
    )
    from app.services.workflow_compute_runtime import terminal_compute

    await terminal_compute(db, job, run, usage=usage)
