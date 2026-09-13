"""Publish only explicitly previewed method content into a Project scope."""

from copy import deepcopy
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from app.models.analysis import AnalysisPipelineRevision
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.workflow_analysis import WorkflowAnalysisMethod
from app.services.analysis_engine import (
    ENGINE_VERSION,
    AnalysisRecipe,
    canonical_digest,
)
from app.services.analysis_generation import authorize_ai_provenance
from app.services.record_analyses import owned_pipeline, verify_revision_integrity
from app.services.workflow_analysis_contracts import validate_analysis_method_inputs
from app.services.workflow_definitions import request_lock, require_protocol_read, scope


class MethodPublicationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    pipeline_revision_id: UUID
    protocol_version_id: UUID
    title: str = Field(min_length=1, max_length=255)
    compute_result_schema: dict | None = None

    @field_validator("title")
    @classmethod
    def title_required(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Published method title is required")
        return value


class MethodPublicationConfirm(MethodPublicationDraft):
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotency_key: UUID


def schema_digest(version):
    return canonical_digest(
        {
            "id": str(version.id),
            "protocol_id": str(version.protocol_id),
            "version": version.version,
            "json_schema": version.json_schema,
            "fields": version.fields,
        }
    )


def publication_content(method):
    content = {
        "project_id": str(method.project_id),
        "protocol_id": str(method.protocol_id),
        "protocol_version_id": str(method.protocol_version_id),
        "title": method.title,
        "engine_version": method.engine_version,
        "recipe": method.recipe,
        "input_fields": method.input_fields,
        "source_schema_digest": method.source_schema_digest,
    }
    # An empty additive contract must not change existing builtin publication seals.
    if getattr(method, "compute_contract", None):
        content["compute_contract"] = method.compute_contract
    return content


def publication_digest(method):
    return canonical_digest(
        {
            "schema": "airalogy.workflow-analysis-method.v1",
            "content": publication_content(method),
            "source_pipeline_revision_id": str(method.source_pipeline_revision_id),
            "source_method_digest": method.source_method_digest,
        }
    )


def publication_payload(method):
    # A whitelist is deliberate: origin IDs, original selection and AI context
    # belong to the private source, not to the new Project asset's public shape.
    return {
        "id": str(method.id),
        **deepcopy(publication_content(method)),
        "digest": method.digest,
        "created_by_user_id": str(method.created_by_user_id),
        "created_at": method.created_at.isoformat(),
    }


async def get_method(db, user, publication_id, project=None):
    method = await db.get(
        WorkflowAnalysisMethod, publication_id, populate_existing=True
    )
    if method is None or (project is not None and method.project_id != project.id):
        raise HTTPException(404, "Published analysis method not found")
    project = await scope(db, user, method.project_id)
    protocol = await db.get(Protocol, method.protocol_id, populate_existing=True)
    version = await db.get(
        ProtocolVersion, method.protocol_version_id, populate_existing=True
    )
    if (
        protocol is None
        or protocol.deleted_at is not None
        or protocol.project_id != project.id
        or version is None
        or version.protocol_id != protocol.id
    ):
        raise HTTPException(404, "Published method Protocol is unavailable")
    await require_protocol_read(db, user, project, protocol)
    try:
        if method.digest != publication_digest(
            method
        ) or method.source_schema_digest != schema_digest(version):
            raise ValueError("Published method integrity check failed")
        if method.engine_version == ENGINE_VERSION:
            if method.compute_contract:
                raise ValueError("Builtin method cannot contain a Compute contract")
            recipe = AnalysisRecipe.model_validate(method.recipe)
            fields = validate_analysis_method_inputs(recipe, [version])
            if canonical_digest(fields) != canonical_digest(method.input_fields):
                raise ValueError("Published method input contract changed")
        else:
            try:
                await verify_compute_publication(db, project, method, version)
            except HTTPException as exc:
                if exc.status_code != 422:
                    raise
                raise ValueError(
                    "Published Compute contract is no longer valid"
                ) from exc
    except ValueError as exc:
        raise HTTPException(409, "Published method integrity check failed") from exc
    return method


async def compute_publication_contract(db, project, recipe, version, result_schema):
    from app.services.analysis_compute import environment_for_recipe
    from app.services.research_compute import compute_environment_snapshot
    from app.services.workflow_compute_contracts import validate_compute_result_schema

    environment, revision = await environment_for_recipe(db, project, recipe)
    input_contract = {
        "json_schema": deepcopy(version.json_schema),
        "fields": deepcopy(version.fields),
    }
    return {
        "environment": compute_environment_snapshot(environment, revision),
        "input_schema_contract": input_contract,
        "input_schema_digest": canonical_digest(input_contract),
        "result_schema": validate_compute_result_schema(
            revision.result_schema if result_schema is None else result_schema
        ),
    }


async def verify_compute_publication(db, project, method, version):
    from app.services.analysis_compute_contracts import (
        COMPUTE_ENGINE_VERSION,
        AnalysisComputeRecipe,
    )

    if method.engine_version != COMPUTE_ENGINE_VERSION or method.input_fields:
        raise ValueError("Unsupported published method engine")
    contract = method.compute_contract
    if not isinstance(contract, dict) or "result_schema" not in contract:
        raise ValueError("Published Compute contract is missing")
    current = await compute_publication_contract(
        db,
        project,
        AnalysisComputeRecipe.model_validate(method.recipe),
        version,
        contract["result_schema"],
    )
    if canonical_digest(contract) != canonical_digest(current):
        raise ValueError("Published Compute environment or input contract changed")


async def list_methods(db, user, project, *, unavailable=None):
    """Isolate stale assets after authorization without exposing private details."""
    await scope(db, user, project.id)
    rows = (
        await db.scalars(
            select(WorkflowAnalysisMethod)
            .where(WorkflowAnalysisMethod.project_id == project.id)
            .order_by(WorkflowAnalysisMethod.created_at.desc())
            .limit(200)
        )
    ).all()
    items = []
    for row in rows:
        try:
            method = await get_method(db, user, row.id, project)
        except HTTPException as exc:
            if exc.status_code in {403, 404}:
                continue
            if exc.status_code == 409:
                if unavailable is not None:
                    # get_method performs Project/Protocol authorization before
                    # integrity checks. Never echo the untrusted title or recipe.
                    unavailable.append(
                        {"id": str(row.id), "code": "method_unavailable"}
                    )
                continue
            raise
        items.append(publication_payload(method))
    return items


async def preview_publication(db, user, params):
    project = await scope(db, user, params.project_id, "research.create")
    revision = await db.get(
        AnalysisPipelineRevision, params.pipeline_revision_id, populate_existing=True
    )
    if revision is None:
        raise HTTPException(404, "Private analysis method not found")
    pipeline = await owned_pipeline(db, revision.pipeline_id, user)
    if pipeline.project_id != project.id:
        raise HTTPException(404, "Method is not in this Project")
    verify_revision_integrity(revision)
    if revision.provenance.get("ai_provenance"):
        await authorize_ai_provenance(db, revision.provenance["ai_provenance"], user)
    version = await db.get(
        ProtocolVersion, params.protocol_version_id, populate_existing=True
    )
    if version is None or version.protocol_id != pipeline.protocol_id:
        raise HTTPException(404, "Exact method input Protocol version not found")
    try:
        from app.services.analysis_compute_contracts import (
            COMPUTE_ENGINE_VERSION,
            AnalysisComputeRecipe,
        )
        from app.services.research_runtime import require_research_capability

        engine = revision.provenance.get("engine_version")
        compute_contract = None
        if engine == ENGINE_VERSION:
            if params.compute_result_schema is not None:
                raise ValueError(
                    "A builtin method cannot declare a Compute result Schema"
                )
            recipe = AnalysisRecipe.model_validate(revision.recipe)
            fields = validate_analysis_method_inputs(recipe, [version])
        elif engine == COMPUTE_ENGINE_VERSION:
            await require_research_capability(
                db, user=user, project=project, capability="research.compute.use"
            )
            recipe = AnalysisComputeRecipe.model_validate(revision.recipe)
            fields = []
            compute_contract = await compute_publication_contract(
                db, project, recipe, version, params.compute_result_schema
            )
        else:
            raise ValueError("Unsupported analysis method engine")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    publication = {
        "project_id": str(project.id),
        "protocol_id": str(pipeline.protocol_id),
        "protocol_version_id": str(version.id),
        "title": params.title,
        "engine_version": engine,
        "recipe": recipe.model_dump(mode="json"),
        "input_fields": fields,
        "source_schema_digest": schema_digest(version),
    }
    if compute_contract is not None:
        publication["compute_contract"] = compute_contract
    source = {
        "pipeline_id": str(pipeline.id),
        "pipeline_revision_id": str(revision.id),
        "revision": revision.revision,
        "method_digest": revision.provenance["method_digest"],
    }
    command = {
        "publication": publication,
        "source": source,
        "audience": "project_research_members_with_protocol_access",
        "excluded_fields": [
            "source_selection",
            "source_records",
            "results",
            "ai_provenance",
        ],
    }
    if compute_contract is not None:
        command["excluded_fields"].extend(
            ["original_approver", "original_budget", "original_deadline"]
        )
    return {
        **command,
        "preview_digest": canonical_digest({"user_id": str(user.id), **command}),
    }


async def confirm_publication(db, user, params):
    await request_lock(db, user.id, params.idempotency_key)
    existing = await db.scalar(
        select(WorkflowAnalysisMethod).where(
            WorkflowAnalysisMethod.created_by_user_id == user.id,
            WorkflowAnalysisMethod.idempotency_key == params.idempotency_key,
        )
    )
    if existing is not None:
        result_schema = params.compute_result_schema
        if result_schema is None and existing.compute_contract:
            result_schema = existing.compute_contract["environment"]["output_schema"]
        if (
            existing.request_digest != params.preview_digest
            or existing.project_id != params.project_id
            or existing.source_pipeline_revision_id != params.pipeline_revision_id
            or existing.protocol_version_id != params.protocol_version_id
            or existing.title != params.title
            or (
                result_schema is not None
                and canonical_digest(result_schema)
                != canonical_digest(
                    (existing.compute_contract or {}).get("result_schema")
                )
            )
        ):
            raise HTTPException(409, "Publication key belongs to another preview")
        return await get_method(db, user, existing.id)
    preview = await preview_publication(db, user, params)
    if preview["preview_digest"] != params.preview_digest:
        raise HTTPException(
            409, "Method or input Schema changed; preview publication again"
        )
    content = dict(preview["publication"])
    for key in ("project_id", "protocol_id", "protocol_version_id"):
        content[key] = UUID(content[key])
    method = WorkflowAnalysisMethod(
        **content,
        source_pipeline_revision_id=params.pipeline_revision_id,
        source_method_digest=preview["source"]["method_digest"],
        created_by_user_id=user.id,
        idempotency_key=params.idempotency_key,
        request_digest=params.preview_digest,
    )
    method.digest = publication_digest(method)
    db.add(method)
    await db.flush()
    return method
