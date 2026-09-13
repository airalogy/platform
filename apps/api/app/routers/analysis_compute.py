"""Private analysis adapter for the shared, approval-gated Compute runtime."""

from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.database import DBSession
from app.libs.file_storage import get_file_with_stream
from app.models.analysis import AnalysisRun
from app.models.analysis_compute import AnalysisCompute, AnalysisComputeEvent
from app.models.knowledge import ResearchFileBlob
from app.models.research_execution import ResearchComputeJob, ResearchComputeJobOutput
from app.models.user import User
from app.routers.analyses import AnalysisConfirmRequest, run_payload
from app.routers.depends import CurrentUser
from app.services.analysis_compute import (
    analysis_compute_input_bytes,
    analysis_runner_counts,
    authorize_approver,
    authorize_compute_execution,
    compute_options,
    confirm_compute,
    emit_analysis_compute_event,
    instant,
    money,
    owned_compute,
    preview_compute,
)
from app.services.analysis_compute_contracts import (
    AnalysisComputeCancel,
    AnalysisComputeDecision,
    AnalysisComputeDraft,
)
from app.services.analysis_engine import AnalysisError
from app.services.record_analyses import AnalysisSelection, analysis_scope, utcnow
from app.services.research_compute_jobs import (
    compute_job_snapshot,
    compute_source_digest,
)

router = APIRouter(tags=["analysis"])
FINAL_STATUSES = {"completed", "failed", "cancelled"}


async def compute_detail(db, user, run, details, job, *, approval_only=False):
    """Reconstruct the sealed contract; never depend on an expiring preview."""
    import hashlib

    authorized, ready = await analysis_runner_counts(
        db, job.compute_environment_revision_id
    )
    approver = await db.get(User, details.approver_user_id)
    can_approve = False
    if (
        details.approver_user_id == user.id
        and details.approval_state == "pending"
        and job.status == "awaiting_approval"
    ):
        try:
            _, project, _ = await analysis_scope(db, run.protocol_id, user)
            await authorize_approver(
                db, run.protocol_id, project, run.source_snapshot, user
            )
            if run.recipe.get("input_files"):
                from app.services.analysis_compute_files import authorize_input_files

                await authorize_input_files(db, run, user)
            can_approve = True
        except HTTPException as exc:
            if exc.status_code not in {403, 404}:
                raise
    source = analysis_compute_input_bytes(run)
    contract = {
        "environment": job.environment_snapshot,
        "source": {
            "language": job.language,
            "code": job.source_code,
            "sha256": compute_source_digest(job.source_code),
            "bytes": len(job.source_code.encode("utf-8")),
        },
        "input": {
            "filename": "records.json",
            "record_count": len(run.source_snapshot["records"]),
            "bytes": len(source),
            "sha256": hashlib.sha256(source).hexdigest(),
        },
        "parameters": job.input_payload,
        "output_files": run.recipe["output_files"],
        "approver": {
            "id": str(details.approver_user_id),
            "name": (approver.name or approver.username) if approver else "",
        },
        "cost": {
            "estimated_cost": money(job.estimated_cost),
            "currency": job.currency,
            "max_cost": money(details.max_cost),
            "budget_currency": details.budget_currency,
        },
        "deadline_at": instant(details.deadline_at),
        "authorized_runner_count": authorized,
        "ready_runner_count": ready,
        "approval_required": True,
    }
    if getattr(details, "input_file_manifest", None):
        contract["input_files"] = details.input_file_manifest
    events = (
        await db.scalars(
            select(AnalysisComputeEvent)
            .where(
                AnalysisComputeEvent.analysis_run_id == run.id,
            )
            .order_by(
                AnalysisComputeEvent.created_at.desc(), AnalysisComputeEvent.id.desc()
            )
            .limit(100)
        )
    ).all()
    job_data = compute_job_snapshot(job, include_source=True)
    if approval_only:
        # Approval grants neither a private report nor its computed artifacts.
        job_data.update(
            result={}, output_manifest=[], usage={}, error=None, cancel_reason=None
        )
    run_data = run_payload(run, summary=approval_only)
    if approval_only:
        run_data["error"] = None
        # The adopted code is reviewed in contract.source; original questions,
        # discarded AI proposals and inherited private draft history are not.
        run_data["ai_provenance"] = {}
    return {
        "run": run_data,
        "job": job_data,
        "contract": contract,
        "approval": {
            "state": details.approval_state,
            "revision": details.approval_revision,
            "approver_user_id": details.approver_user_id,
            "can_approve": can_approve,
            "contract_digest": details.contract_digest,
            "reason": details.decision_reason,
            "decided_at": details.decided_at,
            "requested_at": details.requested_at,
        },
        "events": [
            {
                "id": event.id,
                "kind": event.kind,
                "created_at": event.created_at,
                "details": {} if approval_only else event.payload,
            }
            for event in events
        ],
    }


@router.post("/protocols/{protocol_id}/analysis-compute-context")
async def get_analysis_compute_context(
    protocol_id: UUID,
    selection: AnalysisSelection,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return await compute_options(db_session, current_user, protocol_id, selection)
    except AnalysisError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/analyses/compute/preview")
async def preview_analysis_compute(
    params: AnalysisComputeDraft,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    try:
        preview = await preview_compute(db_session, params, current_user)
    except AnalysisError as exc:
        raise HTTPException(422, str(exc)) from exc
    await db_session.commit()
    return preview.as_dict()


@router.post("/analyses/compute")
async def confirm_analysis_compute(
    params: AnalysisConfirmRequest,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    try:
        run = await confirm_compute(
            db_session,
            current_user,
            preview_id=params.preview_id,
            preview_digest=params.preview_digest,
            key=params.client_idempotency_key,
        )
    except AnalysisError as exc:
        raise HTTPException(422, str(exc)) from exc
    await db_session.commit()
    return run_payload(run)


@router.get("/analyses/{analysis_id}/compute")
async def get_analysis_compute(
    analysis_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    run, details, job = await owned_compute(db_session, analysis_id, current_user)
    return await compute_detail(db_session, current_user, run, details, job)


@router.get("/analyses/{analysis_id}/compute-approval")
async def get_analysis_compute_approval(
    analysis_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    run, details, job = await owned_compute(
        db_session, analysis_id, current_user, approval_access=True
    )
    return await compute_detail(
        db_session, current_user, run, details, job, approval_only=True
    )


@router.get("/analysis-compute-approvals")
async def list_analysis_compute_approvals(
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
    project_id: UUID,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    response.headers["Cache-Control"] = "private, no-store"
    rows = (
        await db_session.execute(
            select(AnalysisRun, AnalysisCompute)
            .join(
                AnalysisCompute,
                AnalysisCompute.analysis_run_id == AnalysisRun.id,
            )
            .where(
                AnalysisRun.project_id == project_id,
                AnalysisCompute.approver_user_id == current_user.id,
                AnalysisCompute.approval_state == "pending",
            )
            .order_by(AnalysisCompute.requested_at, AnalysisRun.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    items = []
    for run, details in rows:
        try:
            await owned_compute(db_session, run.id, current_user, approval_access=True)
        except HTTPException as exc:
            if exc.status_code in {403, 404}:
                continue
            raise
        items.append(
            {
                "analysis_id": run.id,
                "question": run.question,
                "requested_at": details.requested_at,
                "approval_state": details.approval_state,
                "approver_user_id": details.approver_user_id,
            }
        )
    return {"items": items}


@router.post("/analyses/{analysis_id}/compute-approval")
async def decide_analysis_compute(
    analysis_id: UUID,
    params: AnalysisComputeDecision,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    from app.services.workflow_compute_runtime import bound_compute

    # Authenticate the ordinary private reader before revealing a workflow binding.
    await owned_compute(db_session, analysis_id, current_user, approval_access=True)
    if await bound_compute(db_session, analysis_id):
        raise HTTPException(
            409, "Approve this Compute analysis through its Research Task"
        )
    run, details, job = await owned_compute(
        db_session, analysis_id, current_user, approval_access=True, lock=True
    )
    if details.approver_user_id != current_user.id:
        raise HTTPException(403, "Only the explicitly selected approver may decide")
    _, project, _ = await analysis_scope(db_session, run.protocol_id, current_user)
    await authorize_approver(
        db_session, run.protocol_id, project, run.source_snapshot, current_user
    )
    if params.contract_digest != details.contract_digest:
        raise HTTPException(409, "Approval contract changed; review again")
    if (
        details.approval_state == params.decision
        and details.approval_revision == params.expected_revision + 1
        and details.decision_reason == params.reason
        and details.decided_by_user_id == current_user.id
    ):
        return await compute_detail(
            db_session, current_user, run, details, job, approval_only=True
        )
    if (
        details.approval_state != "pending"
        or details.approval_revision != params.expected_revision
        or job.status != "awaiting_approval"
    ):
        raise HTTPException(409, "Approval changed; review again")
    now = utcnow()
    if params.decision == "approved":
        await authorize_compute_execution(db_session, job, require_approved=False)
        authorized, _ = await analysis_runner_counts(
            db_session, job.compute_environment_revision_id
        )
        if not authorized:
            raise HTTPException(409, "No authorized Runner supports private analysis")
        job.status = "queued"
        job.approved_at = now
        job.queued_at = now
    else:
        job.status = "cancelled"
        job.completed_at = now
        run.status = "cancelled"
        run.finished_at = now
        run.error = "Compute approval was rejected"
    details.approval_state = params.decision
    details.approval_revision += 1
    details.decided_by_user_id = current_user.id
    details.decided_at = now
    details.decision_reason = params.reason
    job.revision += 1
    await emit_analysis_compute_event(
        db_session,
        run.id,
        f"compute.{params.decision}",
        actor_user_id=current_user.id,
        payload={"reason": params.reason, "contract_digest": details.contract_digest},
        key=f"decision:{details.approval_revision}",
    )
    await db_session.commit()
    return await compute_detail(
        db_session, current_user, run, details, job, approval_only=True
    )


@router.post("/analyses/{analysis_id}/compute-cancel")
async def cancel_analysis_compute(
    analysis_id: UUID,
    params: AnalysisComputeCancel,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    owner_job = await db_session.scalar(
        select(ResearchComputeJob.id).where(
            ResearchComputeJob.analysis_run_id == analysis_id,
            ResearchComputeJob.created_by_user_id == current_user.id,
        )
    )
    if owner_job is None:
        raise HTTPException(404, "Private computation not found")
    from app.services.workflow_compute_runtime import bound_compute

    if await bound_compute(db_session, analysis_id):
        raise HTTPException(
            409, "Cancel this Compute analysis through its Research Task"
        )
    await db_session.scalar(
        select(AnalysisRun)
        .where(AnalysisRun.id == analysis_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    # A creator may STOP their own job even after Record access is revoked.
    # This endpoint returns only a cancellation receipt, never source/results.
    job = await db_session.scalar(
        select(ResearchComputeJob)
        .where(
            ResearchComputeJob.analysis_run_id == analysis_id,
            ResearchComputeJob.created_by_user_id == current_user.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    details = await db_session.get(AnalysisCompute, analysis_id, populate_existing=True)
    if job is None or details is None:
        raise HTTPException(404, "Private computation not found")
    if params.contract_digest != details.contract_digest:
        raise HTTPException(409, "Cancellation contract changed; review again")
    if (
        job.status in {"cancel_requested", "cancelled"}
        and job.revision == params.expected_revision + 1
        and job.cancel_reason == params.reason
    ):
        return {
            "analysis_id": analysis_id,
            "job_id": job.id,
            "status": job.status,
            "revision": job.revision,
        }
    if job.revision != params.expected_revision or job.status in FINAL_STATUSES:
        raise HTTPException(409, "Compute Job changed; review again")
    now = utcnow()
    previous = job.status
    job.cancel_reason = params.reason
    job.cancel_requested_at = now
    job.revision += 1
    run = await db_session.get(AnalysisRun, analysis_id, populate_existing=True)
    if previous in {"awaiting_approval", "queued"}:
        job.status = "cancelled"
        job.completed_at = now
        run.status = "cancelled"
        run.finished_at = now
        if details.approval_state == "pending":
            details.approval_state = "cancelled"
            details.approval_revision += 1
    else:
        job.status = "cancel_requested"
    run.error = (
        "Compute cancellation requested"
        if job.status == "cancel_requested"
        else "Compute cancelled"
    )
    await emit_analysis_compute_event(
        db_session,
        analysis_id,
        f"compute.{job.status}",
        actor_user_id=current_user.id,
        payload={"reason": params.reason, "previous_status": previous},
        key=f"cancel:{job.revision}",
    )
    await db_session.commit()
    return {
        "analysis_id": analysis_id,
        "job_id": job.id,
        "status": job.status,
        "revision": job.revision,
    }


@router.get("/analyses/{analysis_id}/compute/outputs/{output_id}")
async def download_analysis_compute_output(
    analysis_id: UUID, output_id: UUID, db_session: DBSession, current_user: CurrentUser
):
    run, _, job = await owned_compute(db_session, analysis_id, current_user)
    return await stream_analysis_compute_output(
        db_session, current_user, run, job, output_id
    )


async def stream_analysis_compute_output(db_session, current_user, run, job, output_id):
    """Shared receipt verification; the caller owns scope and source authorization."""
    if run.status != "succeeded" or job.status != "completed":
        raise HTTPException(409, "Compute output is not a completed analysis result")
    row = (
        await db_session.execute(
            select(ResearchComputeJobOutput, ResearchFileBlob)
            .join(
                ResearchFileBlob,
                ResearchFileBlob.id == ResearchComputeJobOutput.blob_id,
            )
            .where(
                ResearchComputeJobOutput.id == output_id,
                ResearchComputeJobOutput.compute_job_id == job.id,
                ResearchComputeJobOutput.registered_at.is_not(None),
            )
        )
    ).first()
    if row is None:
        raise HTTPException(404, "Private analysis output not found")
    output, blob = row
    # Compare actual storage receipts with the immutable successful report.
    sealed = next(
        (
            item
            for item in (run.result or {}).get("outputs", [])
            if item.get("id") == str(output.id)
        ),
        None,
    )
    if (
        sealed is None
        or sealed.get("checksum_sha256") != blob.checksum_sha256
        or sealed.get("byte_size") != blob.size_bytes
    ):
        raise HTTPException(409, "Private output integrity check failed")
    await emit_analysis_compute_event(
        db_session,
        run.id,
        "compute.output_downloaded",
        actor_user_id=current_user.id,
        payload={"output_id": str(output.id), "sha256": blob.checksum_sha256},
        key=f"download:{uuid4()}",
    )
    await db_session.commit()
    return StreamingResponse(
        get_file_with_stream(blob.storage_object_key, backend=blob.storage_backend),
        media_type=blob.content_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(output.mount_name)}",
            "Content-Length": str(blob.size_bytes),
            "X-Content-SHA256": blob.checksum_sha256,
        },
    )
