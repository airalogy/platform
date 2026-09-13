"""Analysis workbench API; all products remain private and source-authorized."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.config import config
from app.database import DBSession
from app.models.analysis import AnalysisPipeline, AnalysisPipelineRevision, AnalysisRun
from app.models.protocol_version import ProtocolVersion
from app.routers.depends import CurrentUser
from app.services.analysis_compute_contracts import (
    COMPUTE_ENGINE_VERSION,
    AnalysisComputeRecipe,
)
from app.services.analysis_engine import (
    ENGINE_VERSION,
    MAX_RECORDS,
    AnalysisError,
    AnalysisRecipe,
    canonical_digest,
    resolve_field_catalog,
    validate_recipe,
)
from app.services.analysis_generation import (
    authorize_ai_provenance,
    inherited_provenance,
)
from app.services.record_analyses import (
    AnalysisPreviewRequest,
    AnalysisSelection,
    analysis_scope,
    authorize_snapshot,
    cancel_analysis,
    capture_sources,
    confirm_analysis,
    create_preview,
    method_revision_digest,
    owned_pipeline,
    owned_run,
    schema_fields,
    verify_revision_integrity,
)

router = APIRouter(tags=["analysis"])


class AnalysisConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview_id: UUID
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    client_idempotency_key: str = Field(min_length=8, max_length=128)


class PipelineCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    title: str = Field(min_length=1, max_length=255)


class PipelineReviseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipe: AnalysisRecipe | AnalysisComputeRecipe
    expected_revision: int = Field(ge=1, strict=True)
    source_selection: AnalysisSelection | None = None


def run_payload(run: AnalysisRun, *, summary: bool = False) -> dict:
    return run.as_dict(excludes=["source_snapshot", "result"] if summary else [])


@router.get("/protocols/{protocol_id}/analysis-context")
async def get_analysis_context(
    protocol_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    protocol, project, own_only = await analysis_scope(
        db_session, protocol_id, current_user
    )
    versions = list(
        (
            await db_session.scalars(
                select(ProtocolVersion)
                .where(ProtocolVersion.protocol_id == protocol.id)
                .order_by(ProtocolVersion.version)
            )
        ).all()
    )
    latest = next((v for v in versions if v.version == protocol.latest_version), None)
    try:
        fields = schema_fields(latest) if latest else []
    except AnalysisError as exc:
        raise HTTPException(422, f"Protocol Schema is not analyzable: {exc}") from exc
    return {
        "protocol_id": protocol.id,
        "project_id": project.id,
        "protocol_name": protocol.name,
        "project_name": project.name,
        "fields": fields,
        "protocol_versions": [v.version for v in versions],
        "limits": {"max_records": MAX_RECORDS},
        "ai_available": config.effective_ai_enabled,
        "own_records_only": own_only,
    }


@router.post("/protocols/{protocol_id}/analysis-context")
async def get_selected_analysis_context(
    protocol_id: UUID,
    selection: AnalysisSelection,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
):
    """Resolve editable fields from actual selected Record versions, without a run."""
    response.headers["Cache-Control"] = "private, no-store"
    try:
        snapshot, protocol, project = await capture_sources(
            db_session, protocol_id=protocol_id, user=current_user, selection=selection
        )
    except AnalysisError as exc:
        raise HTTPException(422, str(exc)) from exc
    grouped_fields = {}
    for field in snapshot["fields"]:
        grouped_fields.setdefault(field["key"], []).append(field)
    fields = []
    for key, definitions in grouped_fields.items():
        try:
            fields.append(resolve_field_catalog(definitions, {key})[key])
        except AnalysisError as exc:
            # Disable only this incompatible/complex field, not other usable data.
            fields.append(
                {
                    "key": key,
                    "title": definitions[0].get("title", key),
                    "type": "unsupported",
                    "unsupported_reason": str(exc),
                }
            )
    _, _, own_only = await analysis_scope(db_session, protocol_id, current_user)
    return {
        "protocol_id": protocol.id,
        "project_id": project.id,
        "protocol_name": protocol.name,
        "project_name": project.name,
        "fields": fields,
        "protocol_versions": [item["version"] for item in snapshot["schemas"]],
        "limits": {"max_records": MAX_RECORDS},
        "ai_available": config.effective_ai_enabled,
        "own_records_only": own_only,
    }


@router.post("/analyses/preview")
async def preview_record_analysis(
    params: AnalysisPreviewRequest, db_session: DBSession, current_user: CurrentUser
):
    try:
        preview = await create_preview(db_session, params, current_user)
    except AnalysisError as exc:
        raise HTTPException(422, str(exc)) from exc
    await db_session.commit()
    return preview.as_dict()


@router.post("/analyses")
async def create_record_analysis(
    params: AnalysisConfirmRequest, db_session: DBSession, current_user: CurrentUser
):
    try:
        run = await confirm_analysis(
            db_session,
            preview_id=params.preview_id,
            preview_digest=params.preview_digest,
            key=params.client_idempotency_key,
            user=current_user,
        )
    except AnalysisError as exc:
        raise HTTPException(422, str(exc)) from exc
    await db_session.commit()
    return run_payload(run)


@router.get("/analyses/{analysis_id}")
async def get_record_analysis(
    analysis_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    return run_payload(await owned_run(db_session, analysis_id, current_user))


@router.get("/analyses/{analysis_id}/download")
async def download_record_analysis(
    analysis_id: UUID, db_session: DBSession, current_user: CurrentUser
):
    from fastapi.encoders import jsonable_encoder

    run = await owned_run(db_session, analysis_id, current_user)
    if run.status != "succeeded":
        raise HTTPException(409, "Analysis has not succeeded")
    return JSONResponse(
        jsonable_encoder(run_payload(run)),
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'attachment; filename="analysis-{run.id}.json"',
        },
    )


@router.post("/analyses/{analysis_id}/cancel")
async def cancel_record_analysis(
    analysis_id: UUID, db_session: DBSession, current_user: CurrentUser
):
    from app.services.workflow_analysis_runtime import workflow_analysis_context

    # Authorize the private endpoint before resolving a governed binding, then
    # acquire Task locks before the Analysis row and recheck the private owner.
    await owned_run(db_session, analysis_id, current_user)
    context = await workflow_analysis_context(db_session, analysis_id)
    run = await owned_run(db_session, analysis_id, current_user, lock=True)
    if context is not None:
        raise HTTPException(
            409, "Use Research Task cancellation to stop a Workflow analysis"
        )
    if run.engine_version == COMPUTE_ENGINE_VERSION:
        raise HTTPException(
            409, "Use the reviewed Compute cancellation to stop its Runner"
        )
    await cancel_analysis(db_session, run)
    await db_session.commit()
    return run_payload(run)


@router.get("/projects/{project_id}/analyses")
async def list_record_analyses(
    project_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    response.headers["Cache-Control"] = "private, no-store"
    runs = list(
        (
            await db_session.scalars(
                select(AnalysisRun)
                .where(
                    AnalysisRun.project_id == project_id,
                    AnalysisRun.created_by_user_id == current_user.id,
                )
                .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    items = []
    for run in runs:
        try:
            await authorize_snapshot(db_session, run, current_user)
        except HTTPException as exc:
            if exc.status_code not in {403, 404}:
                raise
            continue
        items.append(run_payload(run, summary=True))
    return {"items": items}


@router.post("/analysis-pipelines")
async def create_analysis_pipeline(
    params: PipelineCreateRequest, db_session: DBSession, current_user: CurrentUser
):
    run = await owned_run(db_session, params.run_id, current_user)
    if run.status != "succeeded":
        raise HTTPException(409, "Save a method from a successfully computed analysis")
    if not params.title.strip():
        raise HTTPException(422, "Method title is required")
    pipeline = AnalysisPipeline(
        project_id=run.project_id,
        protocol_id=run.protocol_id,
        created_by_user_id=current_user.id,
        title=params.title.strip(),
        current_revision=1,
    )
    db_session.add(pipeline)
    await db_session.flush()
    provenance = {
        "analysis_id": str(run.id),
        "source_digest": run.source_digest,
        "result_digest": run.result_digest,
        "engine_version": run.engine_version,
    }
    if run.ai_provenance:
        provenance["ai_provenance"] = run.ai_provenance
    provenance["method_digest"] = method_revision_digest(
        run.recipe, run.source_selection, provenance
    )
    revision = AnalysisPipelineRevision(
        pipeline_id=pipeline.id,
        revision=1,
        recipe=run.recipe,
        recipe_digest=run.recipe_digest,
        source_selection=run.source_selection,
        provenance=provenance,
        created_by_user_id=current_user.id,
    )
    db_session.add(revision)
    await db_session.commit()
    return {
        **pipeline.as_dict(),
        "revisions": [revision.as_dict()],
        "current_recipe": revision.recipe,
    }


@router.get("/analysis-pipelines/{pipeline_id}")
async def get_analysis_pipeline(
    pipeline_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    pipeline = await owned_pipeline(db_session, pipeline_id, current_user)
    revisions = list(
        (
            await db_session.scalars(
                select(AnalysisPipelineRevision)
                .where(AnalysisPipelineRevision.pipeline_id == pipeline.id)
                .order_by(AnalysisPipelineRevision.revision.desc())
            )
        ).all()
    )
    for revision in revisions:
        verify_revision_integrity(revision)
        if revision.provenance.get("ai_provenance"):
            await authorize_ai_provenance(
                db_session, revision.provenance["ai_provenance"], current_user
            )
    return {
        **pipeline.as_dict(),
        "revisions": [r.as_dict() for r in revisions],
        "current_recipe": revisions[0].recipe,
    }


@router.get("/projects/{project_id}/analysis-pipelines")
async def list_analysis_pipelines(
    project_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    response: Response,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    response.headers["Cache-Control"] = "private, no-store"
    pipelines = list(
        (
            await db_session.scalars(
                select(AnalysisPipeline)
                .where(
                    AnalysisPipeline.project_id == project_id,
                    AnalysisPipeline.created_by_user_id == current_user.id,
                )
                .order_by(
                    AnalysisPipeline.updated_at.desc(), AnalysisPipeline.id.desc()
                )
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    items = []
    for pipeline in pipelines:
        try:
            await analysis_scope(db_session, pipeline.protocol_id, current_user)
        except HTTPException as exc:
            if exc.status_code not in {403, 404}:
                raise
            continue
        revision = await db_session.scalar(
            select(AnalysisPipelineRevision).where(
                AnalysisPipelineRevision.pipeline_id == pipeline.id,
                AnalysisPipelineRevision.revision == pipeline.current_revision,
            )
        )
        if revision is None:
            raise HTTPException(409, "Current analysis method revision is missing")
        verify_revision_integrity(revision)
        if revision.provenance.get("ai_provenance"):
            try:
                await authorize_ai_provenance(
                    db_session, revision.provenance["ai_provenance"], current_user
                )
            except HTTPException as exc:
                if exc.status_code not in {403, 404}:
                    raise
                continue
        items.append(
            {
                **pipeline.as_dict(),
                "current_revision_id": revision.id,
                "current_recipe": revision.recipe,
                "source_selection": revision.source_selection,
            }
        )
    return {"items": items}


@router.post("/analysis-pipelines/{pipeline_id}/revisions")
async def revise_analysis_pipeline(
    pipeline_id: UUID,
    params: PipelineReviseRequest,
    db_session: DBSession,
    current_user: CurrentUser,
):
    pipeline = await owned_pipeline(db_session, pipeline_id, current_user, lock=True)
    if pipeline.current_revision != params.expected_revision:
        raise HTTPException(409, "Method changed; reload before revising")
    previous = await db_session.scalar(
        select(AnalysisPipelineRevision).where(
            AnalysisPipelineRevision.pipeline_id == pipeline.id,
            AnalysisPipelineRevision.revision == pipeline.current_revision,
        )
    )
    if previous is None:
        raise HTTPException(409, "Current analysis method revision is missing")
    verify_revision_integrity(previous)
    is_compute = isinstance(params.recipe, AnalysisComputeRecipe)
    if (
        previous.provenance.get("engine_version") == COMPUTE_ENGINE_VERSION
    ) != is_compute:
        raise HTTPException(409, "Changing analysis engines requires a separate method")
    if previous.provenance.get("ai_provenance"):
        await authorize_ai_provenance(
            db_session, previous.provenance["ai_provenance"], current_user
        )
    try:
        selection = params.source_selection or AnalysisSelection.model_validate(
            previous.source_selection
        )
    except ValueError as exc:
        raise HTTPException(409, "Stored analysis method selection is invalid") from exc
    try:
        # Validate against the selected Records' exact Protocol versions, not
        # latest_version: later schema edits must not break a pinned old method.
        snapshot, _, project = await capture_sources(
            db_session,
            protocol_id=pipeline.protocol_id,
            user=current_user,
            selection=selection,
        )
        if is_compute:
            from app.services.analysis_compute import environment_for_recipe
            from app.services.research_runtime import require_research_capability

            await require_research_capability(
                db_session,
                user=current_user,
                project=project,
                capability="research.compute.use",
            )
            await environment_for_recipe(db_session, project, params.recipe)
        else:
            validate_recipe(params.recipe, snapshot["fields"])
    except AnalysisError as exc:
        raise HTTPException(422, str(exc)) from exc
    recipe = params.recipe.model_dump(mode="json")
    source_selection = selection.model_dump(mode="json", exclude_none=True)
    provenance = {
        "parent_revision_id": str(previous.id),
        "parent_recipe_digest": previous.recipe_digest,
        "engine_version": COMPUTE_ENGINE_VERSION if is_compute else ENGINE_VERSION,
    }
    if previous.provenance.get("ai_provenance"):
        provenance["ai_provenance"] = inherited_provenance(
            previous.provenance["ai_provenance"], params.recipe
        )
    provenance["method_digest"] = method_revision_digest(
        recipe, source_selection, provenance
    )
    revision = AnalysisPipelineRevision(
        pipeline_id=pipeline.id,
        revision=pipeline.current_revision + 1,
        recipe=recipe,
        recipe_digest=canonical_digest(recipe),
        source_selection=source_selection,
        provenance=provenance,
        created_by_user_id=current_user.id,
    )
    db_session.add(revision)
    pipeline.current_revision += 1
    await db_session.commit()
    return revision.as_dict()
