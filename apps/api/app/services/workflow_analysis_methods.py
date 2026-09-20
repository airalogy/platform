"""Publish only explicitly previewed method content into a Project scope."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select

from app.config import config
from app.models.analysis import AnalysisPipeline, AnalysisPipelineRevision
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.workflow_analysis import (
    WorkflowAnalysisMethod,
    WorkflowAnalysisMethodProjectVersion,
)
from app.services.analysis_engine import (
    ENGINE_VERSION,
    AnalysisRecipe,
    canonical_digest,
)
from app.services.analysis_generation import authorize_ai_provenance
from app.services.project_analysis_engine import (
    ENGINE_VERSION as PROJECT_ENGINE_VERSION,
)
from app.services.project_analysis_engine import ProjectAnalysisRecipe
from app.services.record_analyses import owned_pipeline, verify_revision_integrity
from app.services.workflow_analysis_contracts import validate_analysis_method_inputs
from app.services.workflow_definitions import request_lock, require_protocol_read, scope

PROJECT_PREVIEW_AUDIENCE = "airalogy.workflow-project-method-preview"
PROJECT_PREVIEW_TTL = timedelta(minutes=30)


class ProjectMethodInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,23}$")
    protocol_id: UUID
    protocol_version_ids: list[UUID] = Field(min_length=1, max_length=32)

    @field_validator("protocol_version_ids")
    @classmethod
    def unique_versions(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Project method versions must be selected exactly once")
        return sorted(value, key=str)


class MethodPublicationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    pipeline_revision_id: UUID
    protocol_version_id: UUID | None = None
    project_inputs: list[ProjectMethodInput] = Field(default_factory=list, max_length=8)
    title: str = Field(min_length=1, max_length=255)
    compute_result_schema: dict | None = None

    @model_validator(mode="after")
    def exact_input_scope(self):
        if self.project_inputs:
            if (
                self.protocol_version_id is not None
                or self.compute_result_schema is not None
            ):
                raise ValueError(
                    "Project methods cannot contain a single source or Compute contract"
                )
            if len(self.project_inputs) < 2:
                raise ValueError("Project methods require at least two source slots")
            for name in ("slot_id", "protocol_id"):
                if len({getattr(item, name) for item in self.project_inputs}) != len(
                    self.project_inputs
                ):
                    raise ValueError(
                        "Project source slots and Protocols must be unique"
                    )
            self.project_inputs.sort(key=lambda item: item.slot_id)
        elif self.protocol_version_id is None:
            raise ValueError("Select an exact Protocol version or Project inputs")
        return self

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
    preview_token: str | None = Field(default=None, min_length=1, max_length=8000)


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
        "protocol_id": str(method.protocol_id) if method.protocol_id else None,
        "protocol_version_id": str(method.protocol_version_id)
        if method.protocol_version_id
        else None,
        "title": method.title,
        "engine_version": method.engine_version,
        "recipe": method.recipe,
        "input_fields": method.input_fields,
        "source_schema_digest": method.source_schema_digest,
    }
    # An empty additive contract must not change existing builtin publication seals.
    if getattr(method, "compute_contract", None):
        content["compute_contract"] = method.compute_contract
    if getattr(method, "project_contract", None):
        content["project_contract"] = method.project_contract
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
    payload = {
        "id": str(method.id),
        **deepcopy(publication_content(method)),
        "digest": method.digest,
        "created_by_user_id": str(method.created_by_user_id),
        "created_at": method.created_at.isoformat(),
    }
    if getattr(method, "project_contract", None):
        from app.services.workflow_analysis_contracts import (
            validate_project_method_inputs,
        )

        # A response-only view of the same sealed Schema contract. Raw AIMD
        # `fields` metadata is a mapping, not the selectable scalar catalog.
        # Keep one server-side Schema interpreter and leave method seals intact.
        payload["project_input_fields"] = validate_project_method_inputs(
            method.recipe, method.project_contract
        )
    return payload


async def get_method(db, user, publication_id, project=None):
    method = await db.get(
        WorkflowAnalysisMethod, publication_id, populate_existing=True
    )
    if method is None or (project is not None and method.project_id != project.id):
        raise HTTPException(404, "Published analysis method not found")
    project = await scope(db, user, method.project_id)
    if method.engine_version == PROJECT_ENGINE_VERSION:
        await verify_project_publication(db, user, project, method)
        return method
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
        if getattr(method, "project_contract", None):
            raise ValueError("Single-source method cannot contain a Project contract")
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


async def _project_versions(db, user, project, inputs, *, lock=False):
    """Resolve identities before schemas; locks protect content, not global ACLs."""
    versions = {}
    for item in sorted(inputs, key=lambda item: str(item.protocol_id)):
        statement = select(Protocol).where(Protocol.id == item.protocol_id)
        if lock:
            statement = statement.with_for_update(read=True)
        protocol = await db.scalar(statement.execution_options(populate_existing=True))
        if (
            protocol is None
            or protocol.deleted_at is not None
            or protocol.project_id != project.id
        ):
            raise HTTPException(404, "Project method source Protocol is unavailable")
        await require_protocol_read(db, user, project, protocol)
        statement = (
            select(ProtocolVersion)
            .where(ProtocolVersion.id.in_(item.protocol_version_ids))
            .order_by(ProtocolVersion.id)
        )
        if lock:
            statement = statement.with_for_update(read=True)
        rows = list(
            (
                await db.scalars(statement.execution_options(populate_existing=True))
            ).all()
        )
        if len(rows) != len(item.protocol_version_ids) or any(
            row.protocol_id != protocol.id for row in rows
        ):
            raise HTTPException(
                404, "Exact Project method Protocol versions are unavailable"
            )
        versions[item.slot_id] = rows
    return versions


def project_publication_contract(recipe, inputs, versions):
    labels = {slot.slot_id: slot.label for slot in recipe.slots}
    if {item.slot_id for item in inputs} != set(labels):
        raise ValueError("Project method slots must match the saved recipe exactly")
    return {
        "schema_version": 1,
        "slots": [
            {
                "slot_id": item.slot_id,
                "label": labels[item.slot_id],
                "protocol_id": str(item.protocol_id),
                "versions": [
                    {
                        "id": str(version.id),
                        "version": version.version,
                        "schema_digest": schema_digest(version),
                        "json_schema": deepcopy(version.json_schema),
                        "fields": deepcopy(version.fields),
                    }
                    for version in sorted(
                        versions[item.slot_id], key=lambda row: str(row.id)
                    )
                ],
            }
            for item in sorted(inputs, key=lambda item: item.slot_id)
        ],
    }


def project_contract_inputs(contract):
    return [
        ProjectMethodInput(
            slot_id=slot["slot_id"],
            protocol_id=slot["protocol_id"],
            protocol_version_ids=[version["id"] for version in slot["versions"]],
        )
        for slot in contract["slots"]
    ]


async def verify_project_publication(db, user, project, method):
    from app.services.workflow_analysis_contracts import validate_project_method_inputs

    try:
        contract = method.project_contract
        inputs = project_contract_inputs(contract)
        versions = await _project_versions(db, user, project, inputs)
        references = list(
            (
                await db.scalars(
                    select(WorkflowAnalysisMethodProjectVersion).where(
                        WorkflowAnalysisMethodProjectVersion.method_id == method.id
                    )
                )
            ).all()
        )
        expected = {
            (
                item.slot_id,
                str(item.protocol_id),
                str(version.id),
                schema_digest(version),
            )
            for item in inputs
            for version in versions[item.slot_id]
        }
        actual = {
            (
                row.slot_id,
                str(row.protocol_id),
                str(row.protocol_version_id),
                row.schema_digest,
            )
            for row in references
        }
        if (
            method.protocol_id is not None
            or method.protocol_version_id is not None
            or method.input_fields
            or method.compute_contract
            or actual != expected
            or len(references) != len(expected)
            or method.digest != publication_digest(method)
            or method.source_schema_digest != canonical_digest(contract)
        ):
            raise ValueError("Project method source identity changed")
        recipe = ProjectAnalysisRecipe.model_validate(method.recipe)
        validate_project_method_inputs(recipe, contract, versions)
        if canonical_digest(contract) != canonical_digest(
            project_publication_contract(recipe, inputs, versions)
        ):
            raise ValueError("Project method exact Schema or labels changed")
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise HTTPException(
            409, "Published Project method integrity check failed"
        ) from exc


def sign_project_preview(*, user_id, revision_id, digest, now=None):
    now = now or datetime.now(UTC)
    expires = now + PROJECT_PREVIEW_TTL
    return jwt.encode(
        {
            "aud": PROJECT_PREVIEW_AUDIENCE,
            "sub": str(user_id),
            "revision_id": str(revision_id),
            "digest": digest,
            "iat": now,
            "exp": expires,
        },
        config.SECRET_KEY,
        algorithm="HS256",
    ), expires.isoformat()


def verify_project_preview(token, *, user_id, revision_id, digest):
    try:
        claims = jwt.decode(
            token,
            config.SECRET_KEY,
            algorithms=["HS256"],
            audience=PROJECT_PREVIEW_AUDIENCE,
        )
        if (
            any(
                claims.get(key) != value
                for key, value in {
                    "sub": str(user_id),
                    "revision_id": str(revision_id),
                    "digest": digest,
                }.items()
            )
            or "exp" not in claims
            or "iat" not in claims
        ):
            raise ValueError("Project method preview context differs")
    except (JWTError, ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(
            409, "Project method preview is invalid or expired; preview again"
        ) from exc


async def compute_publication_contract(db, project, recipe, version, result_schema):
    from app.services.analysis_compute import environment_for_recipe
    from app.services.research_compute import compute_environment_snapshot
    from app.services.workflow_compute_contracts import validate_compute_result_schema

    if recipe.input_files:
        from app.services.analysis_compute_files import attachment_field_catalog

        fields = attachment_field_catalog(
            {
                "records": [{"protocol_version": version.version}],
                "schemas": [
                    {
                        "version": version.version,
                        "json_schema": version.json_schema,
                        "fields": version.fields,
                    }
                ],
            }
        )
        supported = {tuple(field["field_path"]) for field in fields}
        if any(tuple(item.field_path) not in supported for item in recipe.input_files):
            raise ValueError(
                "Compute attachment declarations require typed FileId fields in the pinned Schema"
            )
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


async def preview_publication(db, user, params, *, lock=False):
    project_statement = select(Project).where(Project.id == params.project_id)
    if lock:
        project_statement = project_statement.with_for_update(read=True)
    await db.scalar(project_statement.execution_options(populate_existing=True))
    project = await scope(db, user, params.project_id, "research.create")
    revision = await db.get(
        AnalysisPipelineRevision, params.pipeline_revision_id, populate_existing=True
    )
    if revision is None:
        raise HTTPException(404, "Private analysis method not found")
    if lock:
        await db.scalar(
            select(AnalysisPipeline)
            .where(AnalysisPipeline.id == revision.pipeline_id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        revision = await db.scalar(
            select(AnalysisPipelineRevision)
            .where(AnalysisPipelineRevision.id == params.pipeline_revision_id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        if revision is None:
            raise HTTPException(404, "Private analysis method not found")
    pipeline = await owned_pipeline(db, revision.pipeline_id, user)
    if pipeline.project_id != project.id:
        raise HTTPException(404, "Method is not in this Project")
    verify_revision_integrity(revision)
    if revision.provenance.get("ai_provenance"):
        await authorize_ai_provenance(db, revision.provenance["ai_provenance"], user)
    if getattr(pipeline, "source_scope", "protocol") == "project":
        return await _preview_project_publication(
            db, user, project, pipeline, revision, params, lock=lock
        )
    if params.project_inputs or params.protocol_version_id is None:
        raise HTTPException(
            422, "Single-source methods require one exact Protocol version"
        )
    if lock:
        await db.scalar(
            select(Protocol)
            .where(Protocol.id == pipeline.protocol_id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        await db.scalar(
            select(ProtocolVersion)
            .where(ProtocolVersion.id == params.protocol_version_id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
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


async def _preview_project_publication(
    db, user, project, pipeline, revision, params, *, lock=False
):
    from app.services.workflow_analysis_contracts import validate_project_method_inputs

    if (
        not params.project_inputs
        or params.protocol_version_id is not None
        or params.compute_result_schema is not None
    ):
        raise HTTPException(
            422, "Project methods require explicit source-slot version selections"
        )
    if (
        revision.provenance.get("engine_version") != PROJECT_ENGINE_VERSION
        or pipeline.protocol_id is not None
    ):
        raise HTTPException(409, "Project method engine or scope changed")
    try:
        recipe = ProjectAnalysisRecipe.model_validate(revision.recipe)
        originals = revision.provenance["input_contracts"]["inputs"]
        original_protocols = {
            item["slot_id"]: item["protocol_id"] for item in originals
        }
        if {
            item.slot_id: str(item.protocol_id) for item in params.project_inputs
        } != original_protocols:
            raise ValueError(
                "Project method Protocols and slots must match its private source contract"
            )
        original_ids = {
            item["slot_id"]: [UUID(row["id"]) for row in item["schemas"]]
            for item in originals
        }
        combined_inputs = [
            ProjectMethodInput(
                slot_id=item.slot_id,
                protocol_id=item.protocol_id,
                protocol_version_ids=sorted(
                    set(item.protocol_version_ids) | set(original_ids[item.slot_id]),
                    key=str,
                ),
            )
            for item in params.project_inputs
        ]
        # Compare against the original Schema contract as well as across every
        # selected version: a compatible-looking new set cannot redefine units.
        combined_versions = await _project_versions(
            db, user, project, combined_inputs, lock=lock
        )
        combined_contract = project_publication_contract(
            recipe, combined_inputs, combined_versions
        )
        validate_project_method_inputs(recipe, combined_contract, combined_versions)
        versions = {
            item.slot_id: [
                row
                for row in combined_versions[item.slot_id]
                if row.id in item.protocol_version_ids
            ]
            for item in params.project_inputs
        }
        contract = project_publication_contract(recipe, params.project_inputs, versions)
        validate_project_method_inputs(recipe, contract, versions)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    publication = {
        "project_id": str(project.id),
        "protocol_id": None,
        "protocol_version_id": None,
        "title": params.title,
        "engine_version": PROJECT_ENGINE_VERSION,
        "recipe": recipe.model_dump(mode="json"),
        "input_fields": [],
        "project_contract": contract,
        "source_schema_digest": canonical_digest(contract),
    }
    command = {
        "publication": publication,
        "source": {
            "pipeline_id": str(pipeline.id),
            "pipeline_revision_id": str(revision.id),
            "revision": revision.revision,
            "method_digest": revision.provenance["method_digest"],
        },
        "destination": {"project_id": str(project.id), "project_name": project.name},
        "audience": "project_research_members_with_all_source_protocol_access",
        "excluded_fields": [
            "source_selection",
            "source_records",
            "question",
            "results",
            "interpretation_history",
            "ai_provenance",
        ],
    }
    digest = canonical_digest({"user_id": str(user.id), **command})
    token, expires = sign_project_preview(
        user_id=user.id, revision_id=revision.id, digest=digest
    )
    return {
        **command,
        "preview_digest": digest,
        "preview_token": token,
        "expires_at": expires,
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
                bool(params.project_inputs)
                != bool(getattr(existing, "project_contract", None))
                or (
                    params.project_inputs
                    and canonical_digest(
                        [item.model_dump(mode="json") for item in params.project_inputs]
                    )
                    != canonical_digest(
                        [
                            item.model_dump(mode="json")
                            for item in project_contract_inputs(
                                existing.project_contract
                            )
                        ]
                    )
                )
            )
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
    if params.project_inputs:
        verify_project_preview(
            params.preview_token,
            user_id=user.id,
            revision_id=params.pipeline_revision_id,
            digest=params.preview_digest,
        )
    preview = await preview_publication(db, user, params, lock=True)
    if preview["preview_digest"] != params.preview_digest:
        raise HTTPException(
            409, "Method or input Schema changed; preview publication again"
        )
    content = dict(preview["publication"])
    for key in ("project_id", "protocol_id", "protocol_version_id"):
        content[key] = UUID(content[key]) if content[key] is not None else None
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
    if method.project_contract:
        for slot in method.project_contract["slots"]:
            for version in slot["versions"]:
                db.add(
                    WorkflowAnalysisMethodProjectVersion(
                        method_id=method.id,
                        slot_id=slot["slot_id"],
                        protocol_id=UUID(slot["protocol_id"]),
                        protocol_version_id=UUID(version["id"]),
                        schema_digest=version["schema_digest"],
                    )
                )
        await db.flush()
    return method
