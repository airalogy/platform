"""Private Analysis ownership/approval adapter for the shared Compute runtime.

No ResearchTask, Project DataAsset, executable process or model is created here.
The approved job is delivered by the existing isolated Compute Runner protocol.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, timedelta
from decimal import ROUND_HALF_UP, Decimal, localcontext

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert

from app.models.analysis import AnalysisPipelineRevision, AnalysisPreview, AnalysisRun
from app.models.analysis_compute import AnalysisCompute, AnalysisComputeEvent
from app.models.lab import LabRole, LabUser
from app.models.project import ProjectUser
from app.models.research_execution import (
    ResearchComputeEnvironment,
    ResearchComputeEnvironmentRevision,
    ResearchComputeJob,
    ResearchComputeJobInput,
    ResearchComputeJobOutput,
    ResearchComputeRunner,
    ResearchComputeRunnerEnvironment,
)
from app.models.user import User
from app.services.analysis_compute_contracts import (
    ANALYSIS_JOB_SCHEMA,
    COMPUTE_ENGINE_VERSION,
    SOURCE_FILENAME,
    AnalysisComputeDraft,
    AnalysisComputeRecipe,
)
from app.services.analysis_engine import canonical_digest
from app.services.knowledge import assert_research_file_upload_quota
from app.services.record_analyses import (
    analysis_scope,
    authorize_source_manifest,
    capture_sources,
    owned_pipeline,
    owned_run,
    preview_identity_digest,
    utcnow,
    verify_revision_integrity,
)
from app.services.research_compute import (
    all_compute_environment_revision_rows,
    compute_environment_snapshot,
)
from app.services.research_compute_contracts import (
    MAX_SOURCE_BYTES,
    validate_compute_output_budget,
)
from app.services.research_compute_jobs import (
    compute_estimated_cost,
    compute_output_snapshot,
    compute_source_digest,
)
from app.services.research_compute_runners import runner_report_is_execution_ready
from app.services.research_instruments import validate_schema_payload
from app.services.research_runtime import require_research_capability


def money(value: Decimal | None) -> str | None:
    # Match PostgreSQL NUMERIC(38,18) before sealing a proposal. Otherwise a
    # repeating hourly-rate division changes its digest after a database reload.
    if value is None:
        return None
    with localcontext() as context:
        context.prec = 60
        return format(
            value.quantize(Decimal("1e-18"), rounding=ROUND_HALF_UP).normalize(), "f"
        )


def instant(value):
    return value.astimezone(UTC).isoformat() if value else None


def analysis_compute_input_bytes(run_or_snapshot) -> bytes:
    snapshot = (
        run_or_snapshot
        if isinstance(run_or_snapshot, dict)
        else run_or_snapshot.source_snapshot
    )
    return json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


async def emit_analysis_compute_event(
    db, analysis_id, kind, *, payload=None, actor_user_id=None, key
):
    await db.execute(
        insert(AnalysisComputeEvent)
        .values(
            analysis_run_id=analysis_id,
            kind=kind,
            payload=payload or {},
            actor_user_id=actor_user_id,
            idempotency_key=key,
        )
        .on_conflict_do_nothing(index_elements=["analysis_run_id", "idempotency_key"])
    )


async def analysis_runner_counts(db, revision_id) -> tuple[int, int]:
    rows = (
        await db.scalars(
            select(ResearchComputeRunner)
            .join(
                ResearchComputeRunnerEnvironment,
                ResearchComputeRunnerEnvironment.runner_id == ResearchComputeRunner.id,
            )
            .join(
                ResearchComputeEnvironmentRevision,
                ResearchComputeEnvironmentRevision.id
                == ResearchComputeRunnerEnvironment.compute_environment_revision_id,
            )
            .join(
                ResearchComputeEnvironment,
                ResearchComputeEnvironment.id
                == ResearchComputeEnvironmentRevision.compute_environment_id,
            )
            .where(
                ResearchComputeRunnerEnvironment.compute_environment_revision_id
                == revision_id,
                ResearchComputeRunnerEnvironment.archived_at.is_(None),
                ResearchComputeRunnerEnvironment.lab_id
                == ResearchComputeEnvironment.lab_id,
                ResearchComputeRunner.lab_id == ResearchComputeEnvironment.lab_id,
                ResearchComputeRunnerEnvironment.compute_environment_id
                == ResearchComputeEnvironment.id,
                ResearchComputeRunner.runner_protocol_version
                == "airalogy.compute-runner.v1",
                ResearchComputeRunner.enabled.is_(True),
                ResearchComputeRunner.revoked_at.is_(None),
            )
        )
    ).all()
    eligible = [
        r
        for r in rows
        if ANALYSIS_JOB_SCHEMA in (r.last_report or {}).get("job_schemas", [])
    ]
    return len(eligible), sum(runner_report_is_execution_ready(r) for r in eligible)


async def authorize_approver(db, protocol_id, project, snapshot, user):
    await require_research_capability(
        db, user=user, project=project, capability="research.approve"
    )
    _, scope, own_only = await analysis_scope(db, protocol_id, user)
    if scope.id != project.id:
        raise HTTPException(409, "Analysis approval scope changed")
    await authorize_source_manifest(
        db, protocol_id, user, snapshot["records"], own_only=own_only
    )


async def authorized_analysis_environment(db, project, revision_id, language):
    """Resolve exact Lab scope/language without pretending parameters exist.

    Draft generation is allowed before required parameters have been proposed;
    environment_for_recipe remains the deterministic schema/execution gate.
    """
    row = (
        await db.execute(
            select(ResearchComputeEnvironment, ResearchComputeEnvironmentRevision)
            .join(
                ResearchComputeEnvironmentRevision,
                ResearchComputeEnvironmentRevision.compute_environment_id
                == ResearchComputeEnvironment.id,
            )
            .where(
                ResearchComputeEnvironmentRevision.id == revision_id,
                ResearchComputeEnvironment.lab_id == project.lab_id,
                ResearchComputeEnvironment.archived_at.is_(None),
                ResearchComputeEnvironmentRevision.enabled.is_(True),
            )
            .execution_options(populate_existing=True)
        )
    ).first()
    if row is None:
        raise HTTPException(409, "The exact Compute Environment is unavailable")
    environment, revision = row
    if language not in revision.allowed_languages:
        raise HTTPException(422, "Language is not allowed by the Compute Environment")
    return environment, revision


async def environment_for_recipe(db, project, recipe):
    environment, revision = await authorized_analysis_environment(
        db, project, recipe.environment_revision_id, recipe.language
    )
    try:
        validate_schema_payload(
            revision.input_schema, recipe.parameters, "compute input"
        )
        validate_compute_output_budget(recipe.output_files, revision.resource_limits)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return environment, revision


async def compute_options(db, user, protocol_id, selection):
    snapshot, protocol, project = await capture_sources(
        db, protocol_id=protocol_id, user=user, selection=selection
    )
    await require_research_capability(
        db, user=user, project=project, capability="research.compute.use"
    )
    environments = []
    for environment, revision in await all_compute_environment_revision_rows(
        db, lab_id=project.lab_id, enabled_only=True
    ):
        authorized, ready = await analysis_runner_counts(db, revision.id)
        environments.append(
            {
                "id": environment.id,
                "revision_id": revision.id,
                "revision": revision.revision,
                "name": revision.name,
                "image_ref": revision.image_ref,
                "allowed_languages": revision.allowed_languages,
                "resource_limits": revision.resource_limits,
                "network_policy": revision.network_policy,
                "allowed_egress_hosts": revision.allowed_egress_hosts,
                "input_schema": revision.input_schema,
                "result_schema": revision.result_schema,
                "estimated_cost": money(compute_estimated_cost(revision)),
                "currency": revision.currency,
                "authorized_runner_count": authorized,
                "ready_runner_count": ready,
            }
        )
    project_members = select(ProjectUser.user_id).where(
        ProjectUser.project_id == project.id
    )
    lab_managers = select(LabUser.user_id).where(
        LabUser.lab_id == project.lab_id, LabUser.role <= LabRole.MANAGER
    )
    candidates = (
        await db.scalars(
            select(User)
            .where(
                or_(
                    User.id.in_(project_members),
                    User.id.in_(lab_managers),
                    User.id == user.id,
                )
            )
            .order_by(User.name, User.id)
        )
    ).all()
    approvers = []
    for candidate in candidates:
        try:
            await authorize_approver(db, protocol.id, project, snapshot, candidate)
        except HTTPException as exc:
            if exc.status_code in {403, 404}:
                continue
            raise
        approvers.append(
            {"id": candidate.id, "name": candidate.name or candidate.username}
        )
    return {
        "environments": environments,
        "approvers": approvers,
        "source": {
            "record_count": len(snapshot["records"]),
            "source_digest": canonical_digest(snapshot),
            "filename": SOURCE_FILENAME,
        },
        "max_source_bytes": MAX_SOURCE_BYTES,
    }


async def validate_compute_method(
    db,
    user,
    protocol_id,
    recipe,
    selection,
    *,
    pipeline_revision_id=None,
    rerun_of_id=None,
):
    if pipeline_revision_id:
        previous = await db.get(AnalysisPipelineRevision, pipeline_revision_id)
        if previous is None:
            raise HTTPException(404, "Analysis method revision not found")
        pipeline = await owned_pipeline(db, previous.pipeline_id, user)
        verify_revision_integrity(previous)
        if (
            pipeline.protocol_id != protocol_id
            or previous.provenance.get("engine_version") != COMPUTE_ENGINE_VERSION
            or previous.recipe != recipe.model_dump(mode="json")
        ):
            raise HTTPException(409, "An edited Compute method requires a new revision")
    if rerun_of_id:
        original = await owned_run(db, rerun_of_id, user)
        if (
            original.protocol_id != protocol_id
            or original.engine_version != COMPUTE_ENGINE_VERSION
        ):
            raise HTTPException(
                409, "Compute rerun must remain in the original Protocol"
            )


async def preview_compute(db, params: AnalysisComputeDraft, user, *, persist=True):
    await validate_compute_method(
        db,
        user,
        params.protocol_id,
        params.recipe,
        params.selection,
        pipeline_revision_id=params.pipeline_revision_id,
        rerun_of_id=params.rerun_of_id,
    )
    snapshot, protocol, project = await capture_sources(
        db, protocol_id=params.protocol_id, user=user, selection=params.selection
    )
    await require_research_capability(
        db, user=user, project=project, capability="research.compute.use"
    )
    environment, revision = await environment_for_recipe(db, project, params.recipe)
    authorized, ready = await analysis_runner_counts(db, revision.id)
    if not authorized:
        raise HTTPException(
            409,
            "No Compute Runner supports private analysis for this exact environment revision",
        )
    approver = await db.get(User, params.approver_user_id)
    if approver is None:
        raise HTTPException(422, "Select an eligible analysis approver")
    await authorize_approver(db, protocol.id, project, snapshot, approver)
    estimate = compute_estimated_cost(revision)
    if params.max_cost is not None and (
        estimate is None
        or revision.currency != params.budget_currency
        or estimate > params.max_cost
    ):
        raise HTTPException(
            409,
            "Compute estimate is unknown, uses another currency, or exceeds the cost ceiling",
        )
    if params.deadline_at and params.deadline_at <= utcnow():
        raise HTTPException(409, "Compute deadline has passed")
    if params.recipe.output_files:
        await assert_research_file_upload_quota(
            db,
            user.id,
            sum(o.max_bytes for o in params.recipe.output_files),
            incoming_count=len(params.recipe.output_files),
        )
    source_bytes = analysis_compute_input_bytes(snapshot)
    from app.services.analysis_generation import (
        authorize_ai_provenance,
        draft_provenance,
        inherited_provenance,
    )

    ai_provenance = {}
    if params.ai_draft_id:
        ai_provenance = await draft_provenance(
            db,
            params.ai_draft_id,
            user,
            protocol_id=protocol.id,
            source_digest=canonical_digest(snapshot),
            recipe=params.recipe,
            question=params.question,
            environment=compute_environment_snapshot(environment, revision),
        )
    elif params.pipeline_revision_id:
        previous = await db.get(AnalysisPipelineRevision, params.pipeline_revision_id)
        ai_provenance = inherited_provenance(
            previous.provenance.get("ai_provenance", {}), params.recipe
        )
    elif params.rerun_of_id:
        previous = await owned_run(db, params.rerun_of_id, user)
        ai_provenance = inherited_provenance(previous.ai_provenance, params.recipe)
    if ai_provenance:
        await authorize_ai_provenance(db, ai_provenance, user)
    summary = {
        "counts": {
            "total": len(snapshot["records"]),
            "included": len(snapshot["records"]),
            "filtered_out": 0,
        },
        "visibility": "private",
        "engine_version": COMPUTE_ENGINE_VERSION,
        "source_digest": canonical_digest(snapshot),
        "protocol_name": protocol.name,
        "project_name": project.name,
        "fields": snapshot["fields"],
        "sources": [
            {key: value for key, value in r.items() if key != "data"}
            for r in snapshot["records"]
        ],
        "compute": {
            "environment": compute_environment_snapshot(environment, revision),
            "source": {
                "language": params.recipe.language,
                "code": params.recipe.source_code,
                "sha256": compute_source_digest(params.recipe.source_code),
                "bytes": len(params.recipe.source_code.encode("utf-8")),
            },
            "input": {
                "filename": SOURCE_FILENAME,
                "bytes": len(source_bytes),
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
                "record_count": len(snapshot["records"]),
            },
            "parameters": params.recipe.parameters,
            "output_files": [
                o.model_dump(mode="json") for o in params.recipe.output_files
            ],
            "approver": {
                "id": str(approver.id),
                "name": approver.name or approver.username,
            },
            "cost": {
                "estimated_cost": money(estimate),
                "currency": revision.currency,
                "max_cost": money(params.max_cost),
                "budget_currency": params.budget_currency,
            },
            "deadline_at": instant(params.deadline_at),
            "authorized_runner_count": authorized,
            "ready_runner_count": ready,
            "approval_required": True,
        },
    }
    recipe = params.recipe.model_dump(mode="json")
    preview = AnalysisPreview(
        project_id=project.id,
        protocol_id=protocol.id,
        created_by_user_id=user.id,
        pipeline_revision_id=params.pipeline_revision_id,
        rerun_of_id=params.rerun_of_id,
        question=params.question,
        recipe=recipe,
        source_selection=params.selection.model_dump(mode="json", exclude_none=True),
        source_digest=canonical_digest(snapshot),
        recipe_digest=canonical_digest(recipe),
        ai_provenance=ai_provenance,
        summary=summary,
        expires_at=utcnow() + timedelta(minutes=15),
    )
    preview.preview_digest = preview_identity_digest(preview)
    if persist:
        db.add(preview)
        await db.flush()
    return preview


def compute_contract_digest(run, details, job):
    return canonical_digest(
        {
            "analysis_id": str(run.id),
            "owner": str(run.created_by_user_id),
            "project_id": str(run.project_id),
            "protocol_id": str(run.protocol_id),
            "source_digest": run.source_digest,
            "recipe_digest": run.recipe_digest,
            "preview_digest": run.preview_digest,
            "environment": job.environment_snapshot,
            "input_schema": job.input_schema,
            "result_schema": job.result_schema,
            "limits": job.resource_limits,
            "language": job.language,
            "source_sha256": job.source_sha256,
            "parameters": job.input_payload,
            "environment_id": str(job.compute_environment_id),
            "environment_revision_id": str(job.compute_environment_revision_id),
            "environment_revision": job.compute_environment_revision,
            "timeout_seconds": job.timeout_seconds,
            "estimate": money(job.estimated_cost),
            "currency": job.currency,
            "approver": str(details.approver_user_id),
            "max_cost": money(details.max_cost),
            "budget_currency": details.budget_currency,
            "deadline_at": instant(details.deadline_at),
        }
    )


async def confirm_compute(db, user, *, preview_id, preview_digest, key):
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    existing = await db.scalar(
        select(AnalysisRun).where(
            AnalysisRun.created_by_user_id == user.id,
            AnalysisRun.client_idempotency_key == key,
        )
    )
    if existing:
        if (
            existing.preview_digest != preview_digest
            or existing.engine_version != COMPUTE_ENGINE_VERSION
        ):
            raise HTTPException(409, "Idempotency key belongs to another analysis")
        return await owned_run(db, existing.id, user)
    preview = await db.get(AnalysisPreview, preview_id, populate_existing=True)
    if preview is None or preview.created_by_user_id != user.id:
        raise HTTPException(404, "Analysis preview not found")
    if (
        preview.preview_digest != preview_digest
        or preview.expires_at <= utcnow()
        or preview_identity_digest(preview) != preview.preview_digest
        or canonical_digest(preview.recipe) != preview.recipe_digest
    ):
        raise HTTPException(409, "Compute preview changed or expired")
    original = await db.scalar(
        select(AnalysisRun).where(
            AnalysisRun.created_by_user_id == user.id,
            AnalysisRun.preview_digest == preview_digest,
        )
    )
    if original:
        return await owned_run(db, original.id, user)
    compute = preview.summary.get("compute", {})
    if preview.ai_provenance:
        from app.services.analysis_generation import authorize_ai_provenance

        await authorize_ai_provenance(db, preview.ai_provenance, user)
    try:
        params = AnalysisComputeDraft(
            protocol_id=preview.protocol_id,
            recipe=preview.recipe,
            selection=preview.source_selection,
            question=preview.question,
            approver_user_id=compute["approver"]["id"],
            max_cost=compute["cost"]["max_cost"],
            budget_currency=compute["cost"]["budget_currency"],
            deadline_at=compute["deadline_at"],
            pipeline_revision_id=preview.pipeline_revision_id,
            rerun_of_id=preview.rerun_of_id,
            ai_draft_id=preview.ai_provenance.get("request_id")
            if preview.ai_provenance and not preview.ai_provenance.get("inherited")
            else None,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(409, "Invalid Compute preview contract") from exc
    # Revalidate every input without accepting changed data or a new destination.
    refreshed = await preview_compute(db, params, user, persist=False)
    if (
        refreshed.source_digest != preview.source_digest
        or refreshed.summary["compute"]["environment"] != compute["environment"]
        or refreshed.ai_provenance != preview.ai_provenance
    ):
        raise HTTPException(
            409, "Compute sources or environment changed; preview again"
        )
    snapshot, _, project = await capture_sources(
        db, protocol_id=preview.protocol_id, user=user, selection=params.selection
    )
    if canonical_digest(snapshot) != preview.source_digest:
        raise HTTPException(409, "Compute sources changed; preview again")
    run = AnalysisRun(
        project_id=project.id,
        protocol_id=preview.protocol_id,
        created_by_user_id=user.id,
        pipeline_revision_id=preview.pipeline_revision_id,
        rerun_of_id=preview.rerun_of_id,
        question=preview.question,
        recipe=preview.recipe,
        source_selection=preview.source_selection,
        source_snapshot=snapshot,
        source_digest=preview.source_digest,
        recipe_digest=preview.recipe_digest,
        preview_digest=preview_digest,
        client_idempotency_key=key,
        engine_version=COMPUTE_ENGINE_VERSION,
        status="pending",
        ai_provenance=preview.ai_provenance,
    )
    db.add(run)
    await db.flush()
    environment, revision = await environment_for_recipe(db, project, params.recipe)
    job = ResearchComputeJob(
        analysis_run_id=run.id,
        action_id=None,
        compute_environment_id=environment.id,
        compute_environment_revision_id=revision.id,
        compute_environment_revision=revision.revision,
        language=params.recipe.language,
        source_code=params.recipe.source_code,
        source_sha256=compute_source_digest(params.recipe.source_code),
        input_payload=params.recipe.parameters,
        input_schema=revision.input_schema,
        result_schema=revision.result_schema,
        environment_snapshot=compute_environment_snapshot(environment, revision),
        resource_limits=revision.resource_limits,
        timeout_seconds=revision.resource_limits["timeout_seconds"],
        estimated_cost=compute_estimated_cost(revision),
        currency=revision.currency,
        created_by_user_id=user.id,
        output_manifest=[],
    )
    db.add(job)
    await db.flush()
    db.add(
        ResearchComputeJobInput(
            compute_job_id=job.id,
            analysis_run_id=run.id,
            position=1,
            mount_name=SOURCE_FILENAME,
        )
    )
    outputs = []
    for position, spec in enumerate(params.recipe.output_files, 1):
        output = ResearchComputeJobOutput(
            compute_job_id=job.id,
            position=position,
            mount_name=spec.mount_name,
            asset_name=spec.asset_name,
            description=spec.description,
            kind=spec.kind,
            media_type=spec.media_type,
            max_bytes=spec.max_bytes,
            required=spec.required,
            data_schema=spec.data_schema,
            version_metadata=spec.metadata,
        )
        db.add(output)
        outputs.append(output)
    await db.flush()
    job.output_manifest = [compute_output_snapshot(o) for o in outputs]
    details = AnalysisCompute(
        analysis_run_id=run.id,
        approver_user_id=params.approver_user_id,
        approval_state="pending",
        approval_revision=1,
        max_cost=params.max_cost,
        budget_currency=params.budget_currency,
        deadline_at=params.deadline_at,
        decision_reason="",
    )
    details.contract_digest = compute_contract_digest(run, details, job)
    db.add(details)
    await db.flush()
    await emit_analysis_compute_event(
        db,
        run.id,
        "compute.requested",
        actor_user_id=user.id,
        payload={"compute_job_id": str(job.id)},
        key="requested",
    )
    return run


async def verify_compute_contract(db, run, details, job):
    try:
        recipe = AnalysisComputeRecipe.model_validate(run.recipe)
    except ValueError as exc:
        raise HTTPException(
            409, "Private Compute recipe integrity check failed"
        ) from exc
    if (
        run.engine_version != COMPUTE_ENGINE_VERSION
        or job.analysis_run_id != run.id
        or job.action_id is not None
        or job.created_by_user_id != run.created_by_user_id
        or compute_contract_digest(run, details, job) != details.contract_digest
        or compute_source_digest(job.source_code) != job.source_sha256
        or job.source_code != recipe.source_code
        or job.language != recipe.language
        or job.input_payload != recipe.parameters
        or job.compute_environment_revision_id != recipe.environment_revision_id
    ):
        raise HTTPException(409, "Private Compute contract integrity check failed")
    if run.status == "succeeded" and (
        job.status != "completed"
        or job.result != (run.result or {}).get("computed_result")
        or job.output_manifest != (run.result or {}).get("outputs")
        or job.usage != (run.result or {}).get("usage")
        or money(job.actual_cost) != (run.result or {}).get("actual_cost")
    ):
        raise HTTPException(409, "Private Compute result integrity check failed")
    inputs = (
        await db.scalars(
            select(ResearchComputeJobInput).where(
                ResearchComputeJobInput.compute_job_id == job.id
            )
        )
    ).all()
    if (
        len(inputs) != 1
        or inputs[0].analysis_run_id != run.id
        or inputs[0].mount_name != SOURCE_FILENAME
        or inputs[0].position != 1
        or inputs[0].data_asset_id is not None
        or inputs[0].data_asset_version_id is not None
    ):
        raise HTTPException(409, "Private Compute source binding changed")
    outputs = (
        await db.scalars(
            select(ResearchComputeJobOutput)
            .where(ResearchComputeJobOutput.compute_job_id == job.id)
            .order_by(ResearchComputeJobOutput.position)
        )
    ).all()
    actual = [
        {
            "mount_name": o.mount_name,
            "asset_name": o.asset_name,
            "description": o.description,
            "kind": o.kind,
            "media_type": o.media_type,
            "max_bytes": o.max_bytes,
            "required": o.required,
            "data_schema": o.data_schema,
            "metadata": o.version_metadata,
        }
        for o in outputs
    ]
    if actual != [o.model_dump(mode="json") for o in recipe.output_files] or any(
        o.research_file_id is not None
        or o.data_asset_id is not None
        or o.data_asset_version_id is not None
        for o in outputs
    ):
        raise HTTPException(409, "Private Compute output contract changed")


async def authorize_compute_execution(
    db, job, *, require_approved=True, check_deadline=True
):
    owner = await db.get(User, job.created_by_user_id)
    if owner is None or job.analysis_run_id is None:
        raise HTTPException(404, "Private analysis owner not found")
    run = await owned_run(db, job.analysis_run_id, owner)
    details = await db.get(AnalysisCompute, run.id, populate_existing=True)
    if details is None:
        raise HTTPException(409, "Private Compute context is missing")
    await verify_compute_contract(db, run, details, job)
    _, project, _ = await analysis_scope(db, run.protocol_id, owner)
    await require_research_capability(
        db, user=owner, project=project, capability="research.compute.use"
    )
    environment, revision = await environment_for_recipe(
        db, project, AnalysisComputeRecipe.model_validate(run.recipe)
    )
    if compute_environment_snapshot(environment, revision) != job.environment_snapshot:
        raise HTTPException(409, "Pinned Compute Environment changed")
    if require_approved:
        if details.approval_state != "approved":
            raise HTTPException(409, "Private computation has not been approved")
        approver = await db.get(User, details.approver_user_id)
        if approver is None or details.decided_by_user_id != approver.id:
            raise HTTPException(403, "Analysis approval authority changed")
        await authorize_approver(
            db, run.protocol_id, project, run.source_snapshot, approver
        )
    if check_deadline and details.deadline_at and details.deadline_at <= utcnow():
        raise HTTPException(409, "Private Compute deadline has passed")
    return run, details


async def owned_compute(db, analysis_id, user, *, approval_access=False, lock=False):
    if lock:
        await owned_compute(db, analysis_id, user, approval_access=approval_access)
        await db.scalar(
            select(AnalysisRun)
            .where(AnalysisRun.id == analysis_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    statement = (
        select(ResearchComputeJob)
        .where(ResearchComputeJob.analysis_run_id == analysis_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        statement = statement.with_for_update()
    job = await db.scalar(statement)
    details = await db.get(AnalysisCompute, analysis_id, populate_existing=True)
    if (
        job is None
        or details is None
        or (
            job.created_by_user_id != user.id
            and (not approval_access or details.approver_user_id != user.id)
        )
    ):
        raise HTTPException(404, "Private computation not found")
    owner = await db.get(User, job.created_by_user_id)
    if owner is None:
        raise HTTPException(404, "Private analysis owner not found")
    run = await owned_run(db, analysis_id, owner)
    await verify_compute_contract(db, run, details, job)
    if user.id != owner.id:
        _, project, _ = await analysis_scope(db, run.protocol_id, user)
        await authorize_approver(
            db, run.protocol_id, project, run.source_snapshot, user
        )
    return run, details, job
