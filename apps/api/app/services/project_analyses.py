"""Private, source-authorized Project analyses on the existing Analysis lifecycle.

Each input retains a complete Protocol snapshot. Nothing flattens columns or
infers cross-Protocol relationships; the pure recipe declares those semantics.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import timedelta
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.models.analysis import (
    AnalysisInterpretationRevision,
    AnalysisPipeline,
    AnalysisPipelineRevision,
    AnalysisPreview,
    AnalysisProjectInput,
    AnalysisRun,
)
from app.models.lab import Lab
from app.models.project import Project
from app.models.protocol_version import ProtocolVersion
from app.models.user import User
from app.services.analysis_engine import MAX_RECORDS, AnalysisError, canonical_digest
from app.services.persistent_jobs import enqueue_job
from app.services.project_analysis_engine import (
    ENGINE_VERSION as PROJECT_ENGINE_VERSION,
)
from app.services.project_analysis_engine import (
    MAX_PROJECT_SNAPSHOT_BYTES,
    ProjectAnalysisRecipe,
    preview_project_analysis,
    validate_project_recipe,
)
from app.services.record_analyses import (
    PREVIEW_MINUTES,
    AnalysisSelection,
    analysis_scope,
    capture_sources,
    method_revision_digest,
    preview_identity_digest,
    utcnow,
    verify_revision_integrity,
    verify_run_integrity,
)

PROJECT_SNAPSHOT_SCHEMA = "airalogy.project-snapshot.v1"
PROJECT_SELECTION_SCHEMA = "airalogy.project-selection.v1"
MAX_PROJECT_INPUTS = 8


class ProjectInputSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,23}$")
    protocol_id: UUID
    selection: AnalysisSelection = Field(default_factory=AnalysisSelection)


class ProjectAnalysisSelection(BaseModel):
    model_config = ConfigDict(
        extra="forbid", populate_by_name=True, serialize_by_alias=True
    )

    schema_: Literal["airalogy.project-selection.v1"] = Field(
        default=PROJECT_SELECTION_SCHEMA, alias="schema"
    )
    inputs: list[ProjectInputSelection] = Field(
        min_length=2, max_length=MAX_PROJECT_INPUTS
    )

    @model_validator(mode="after")
    def unique_scopes(self):
        if len({item.slot_id for item in self.inputs}) != len(self.inputs):
            raise ValueError("Project input slot IDs must be unique")
        if len({item.protocol_id for item in self.inputs}) != len(self.inputs):
            raise ValueError("Select 2 to 8 distinct Protocols in this Project")
        return self


class ProjectPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    selection: ProjectAnalysisSelection
    recipe: ProjectAnalysisRecipe
    question: str = Field(default="", max_length=4000)
    pipeline_revision_id: UUID | None = None
    rerun_of_id: UUID | None = None


def project_selection_payload(selection):
    """One stable shape for stored selections, without changing legacy models."""
    value = ProjectAnalysisSelection.model_validate(selection)
    payload = value.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload["inputs"].sort(key=lambda item: item["slot_id"])
    return payload


async def project_analysis_scope(db, project_id, user):
    from app.routers.permission import check_user_permission

    project = await db.get(Project, project_id, populate_existing=True)
    if project is None or project.deleted_at is not None:
        raise HTTPException(404, "Project not found")
    if await db.get(Lab, project.lab_id) is None:
        raise HTTPException(404, "Lab not found")
    try:
        await check_user_permission(
            db, project=project, user=user, action="read_project"
        )
    except HTTPException as exc:
        raise HTTPException(403, "Project analysis access denied") from exc
    return project


async def capture_project_sources(db, *, project_id, selection, user):
    selection = ProjectAnalysisSelection.model_validate(selection)
    project = await project_analysis_scope(db, project_id, user)
    inputs, total = [], 0
    for item in sorted(selection.inputs, key=lambda item: item.slot_id):
        snapshot, protocol, source_project = await capture_sources(
            db, protocol_id=item.protocol_id, selection=item.selection, user=user
        )
        if source_project.id != project.id or protocol.project_id != project.id:
            raise HTTPException(
                422, "Every selected Protocol must belong to this Project"
            )
        total += len(snapshot["records"])
        if total > MAX_RECORDS:
            raise AnalysisError(
                f"Narrow all Project inputs to at most {MAX_RECORDS} Records"
            )
        inputs.append(
            {"slot_id": item.slot_id, "label": item.slot_id, "snapshot": snapshot}
        )
    result = {
        "schema": PROJECT_SNAPSHOT_SCHEMA,
        "project_id": str(project.id),
        "inputs": inputs,
    }
    encoded = json.dumps(result, ensure_ascii=False, allow_nan=False).encode()
    if len(encoded) > MAX_PROJECT_SNAPSHOT_BYTES:
        raise AnalysisError(
            "Project analysis snapshot exceeds its supported byte limit; narrow the selection"
        )
    return result, project


def _snapshot_selection(snapshot, *, project_id):
    if (
        not isinstance(snapshot, dict)
        or snapshot.get("schema") != PROJECT_SNAPSHOT_SCHEMA
        or snapshot.get("project_id") != str(project_id)
        or not isinstance(snapshot.get("inputs"), list)
    ):
        raise HTTPException(409, "Project analysis source contract changed")
    return ProjectAnalysisSelection.model_validate(
        {
            "schema": PROJECT_SELECTION_SCHEMA,
            "inputs": [
                {
                    "slot_id": item["slot_id"],
                    "protocol_id": item["snapshot"]["protocol_id"],
                    "selection": {
                        "mode": "selected",
                        "records": [
                            {
                                "id": record["record_id"],
                                "version": record["record_version"],
                            }
                            for record in item["snapshot"]["records"]
                        ],
                    },
                }
                for item in snapshot["inputs"]
            ],
        }
    )


def _selection_bindings(selection):
    return {
        item.slot_id: str(item.protocol_id)
        for item in ProjectAnalysisSelection.model_validate(selection).inputs
    }


def project_input_contracts(snapshot):
    """Method schema identity excludes Records, while pinning every input scope."""
    _snapshot_selection(snapshot, project_id=snapshot["project_id"])
    return {
        "schema": "airalogy.project-input-contracts.v1",
        "inputs": [
            {
                "slot_id": item["slot_id"],
                "protocol_id": item["snapshot"]["protocol_id"],
                "schemas": [
                    {
                        "id": schema["id"],
                        "version": schema["version"],
                        "json_schema_digest": canonical_digest(schema["json_schema"]),
                        "fields_digest": canonical_digest(schema["fields"]),
                    }
                    for schema in sorted(
                        item["snapshot"]["schemas"], key=lambda row: row["version"]
                    )
                ],
            }
            for item in sorted(snapshot["inputs"], key=lambda row: row["slot_id"])
        ],
    }


async def authorize_project_snapshot(db, run, user):
    # Public source access never makes another user's report public.
    if run.created_by_user_id != user.id:
        raise HTTPException(404, "Analysis not found")
    await authorize_project_sources(db, run, user)


async def authorize_project_sources(db, run, user):
    """Authorize exact sources, not ownership of the private report itself."""
    try:
        if (
            run.source_scope != "project"
            or run.protocol_id is not None
            or run.engine_version != PROJECT_ENGINE_VERSION
        ):
            raise HTTPException(409, "Project analysis engine or scope changed")
        verify_run_integrity(run)
        exact = _snapshot_selection(run.source_snapshot, project_id=run.project_id)
        if _selection_bindings(exact) != _selection_bindings(run.source_selection):
            raise HTTPException(409, "Project analysis input slots changed")
        references = list(
            (
                await db.scalars(
                    select(AnalysisProjectInput).where(
                        AnalysisProjectInput.run_id == run.id
                    )
                )
            ).all()
        )
        expected = {
            item["slot_id"]: (
                item["snapshot"]["protocol_id"],
                canonical_digest(item["snapshot"]),
            )
            for item in run.source_snapshot["inputs"]
        }
        actual = {
            row.slot_id: (str(row.protocol_id), row.source_digest) for row in references
        }
        if actual != expected or len(references) != len(expected):
            raise HTTPException(409, "Project analysis typed source bindings changed")
        current, _ = await capture_project_sources(
            db, project_id=run.project_id, selection=exact, user=user
        )
        if canonical_digest(current) != run.source_digest:
            raise HTTPException(
                409, "Project analysis Records or exact Schema revisions changed"
            )
        validate_project_recipe(
            ProjectAnalysisRecipe.model_validate(run.recipe), current
        )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(
            409, "Project analysis source contract is unavailable or changed"
        ) from exc


async def _authorize_method_revision(db, pipeline, revision, user):
    verify_revision_integrity(revision)
    if revision.provenance.get("engine_version") != PROJECT_ENGINE_VERSION:
        raise HTTPException(409, "Project method engine changed")
    selection = ProjectAnalysisSelection.model_validate(revision.source_selection)
    contracts = revision.provenance.get("input_contracts")
    if (
        not isinstance(contracts, dict)
        or contracts.get("schema") != "airalogy.project-input-contracts.v1"
    ):
        raise HTTPException(409, "Project method input contract is missing")
    expected = _selection_bindings(selection)
    actual = {item["slot_id"]: item["protocol_id"] for item in contracts["inputs"]}
    if actual != expected or len(actual) != len(contracts["inputs"]):
        raise HTTPException(409, "Project method input scopes changed")
    for item in selection.inputs:
        protocol, project, _ = await analysis_scope(db, item.protocol_id, user)
        if (
            project.id != pipeline.project_id
            or protocol.project_id != pipeline.project_id
        ):
            raise HTTPException(403, "Project method source is unavailable")
        if item.selection.mode == "selected":
            await capture_sources(
                db, protocol_id=item.protocol_id, selection=item.selection, user=user
            )
    for item in contracts["inputs"]:
        for expected_schema in item["schemas"]:
            version = await db.get(
                ProtocolVersion, UUID(expected_schema["id"]), populate_existing=True
            )
            if (
                version is None
                or str(version.protocol_id) != item["protocol_id"]
                or version.version != expected_schema["version"]
                or canonical_digest(version.json_schema)
                != expected_schema["json_schema_digest"]
                or canonical_digest(version.fields) != expected_schema["fields_digest"]
            ):
                raise HTTPException(409, "Project method exact Schema revision changed")
    origin_id = revision.provenance.get("analysis_id")
    if origin_id:
        origin = await db.get(AnalysisRun, UUID(origin_id), populate_existing=True)
        if origin is None or origin.project_id != pipeline.project_id:
            raise HTTPException(403, "Project method original source is unavailable")
        await authorize_project_snapshot(db, origin, user)


async def authorize_project_pipeline(db, pipeline, user):
    if pipeline.created_by_user_id != user.id:
        raise HTTPException(404, "Analysis method not found")
    if pipeline.source_scope != "project" or pipeline.protocol_id is not None:
        raise HTTPException(409, "Project method scope changed")
    await project_analysis_scope(db, pipeline.project_id, user)
    revisions = list(
        (
            await db.scalars(
                select(AnalysisPipelineRevision)
                .where(AnalysisPipelineRevision.pipeline_id == pipeline.id)
                .order_by(AnalysisPipelineRevision.revision)
            )
        ).all()
    )
    if not revisions:
        raise HTTPException(409, "Project method revision is missing")
    try:
        for revision in revisions:
            await _authorize_method_revision(db, pipeline, revision, user)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(
            409, "Project method source contract is unavailable or changed"
        ) from exc


async def validate_project_lineage(db, params, user, *, snapshot=None):
    if snapshot is None:
        snapshot, _ = await capture_project_sources(
            db, project_id=params.project_id, selection=params.selection, user=user
        )
    current_contracts = project_input_contracts(snapshot)
    if params.rerun_of_id:
        original = await db.get(AnalysisRun, params.rerun_of_id, populate_existing=True)
        if original is None:
            raise HTTPException(404, "Original analysis not found")
        await authorize_project_snapshot(db, original, user)
        if (
            original.project_id != params.project_id
            or project_input_contracts(original.source_snapshot) != current_contracts
        ):
            raise HTTPException(
                409,
                "Changing Project input Protocols or Schema revisions requires an explicit new method revision",
            )
    if params.pipeline_revision_id:
        revision = await db.get(AnalysisPipelineRevision, params.pipeline_revision_id)
        if revision is None:
            raise HTTPException(404, "Analysis method revision not found")
        pipeline = await db.get(AnalysisPipeline, revision.pipeline_id)
        if pipeline is None:
            raise HTTPException(404, "Analysis method not found")
        await authorize_project_pipeline(db, pipeline, user)
        if (
            pipeline.project_id != params.project_id
            or revision.recipe_digest
            != canonical_digest(params.recipe.model_dump(mode="json"))
            or revision.provenance.get("input_contracts") != current_contracts
        ):
            raise HTTPException(
                409,
                "Edited Project method or input Schema requires a new revision or ad hoc analysis",
            )


def project_preview_summary(project, recipe, snapshot):
    """One preview representation for private and explicitly governed methods."""
    return {
        **preview_project_analysis(recipe, snapshot),
        "engine_version": PROJECT_ENGINE_VERSION,
        "source_scope": "project",
        "visibility": "private",
        "project_name": project.name,
        "source_inputs": [
            {
                "slot_id": item["slot_id"],
                "protocol_id": item["snapshot"]["protocol_id"],
                "record_count": len(item["snapshot"]["records"]),
                "sources": [
                    {key: value for key, value in row.items() if key != "data"}
                    for row in item["snapshot"]["records"]
                ],
                "schemas": [
                    {"id": row["id"], "version": row["version"]}
                    for row in item["snapshot"]["schemas"]
                ],
            }
            for item in snapshot["inputs"]
        ],
    }


async def create_project_preview(db, params, user, *, persist=True):
    snapshot, project = await capture_project_sources(
        db, project_id=params.project_id, selection=params.selection, user=user
    )
    await validate_project_lineage(db, params, user, snapshot=snapshot)
    summary = project_preview_summary(project, params.recipe, snapshot)
    recipe = params.recipe.model_dump(mode="json")
    preview = AnalysisPreview(
        source_scope="project",
        project_id=project.id,
        protocol_id=None,
        created_by_user_id=user.id,
        pipeline_revision_id=params.pipeline_revision_id,
        rerun_of_id=params.rerun_of_id,
        question=params.question,
        recipe=recipe,
        source_selection=project_selection_payload(params.selection),
        source_digest=canonical_digest(snapshot),
        recipe_digest=canonical_digest(recipe),
        ai_provenance={},
        expires_at=utcnow() + timedelta(minutes=PREVIEW_MINUTES),
        summary=summary,
    )
    preview.preview_digest = preview_identity_digest(preview)
    if persist:
        db.add(preview)
        await db.flush()
    return preview


async def confirm_project_analysis(db, *, preview_id, preview_digest, key, user):
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    existing = await db.scalar(
        select(AnalysisRun).where(
            AnalysisRun.created_by_user_id == user.id,
            AnalysisRun.client_idempotency_key == key,
        )
    )
    if existing is not None:
        if (
            existing.preview_digest != preview_digest
            or existing.engine_version != PROJECT_ENGINE_VERSION
        ):
            raise HTTPException(409, "Idempotency key belongs to a different analysis")
        await authorize_project_snapshot(db, existing, user)
        return existing
    preview = await db.get(AnalysisPreview, preview_id, populate_existing=True)
    if preview is None or preview.created_by_user_id != user.id:
        raise HTTPException(404, "Analysis preview not found")
    try:
        valid = (
            preview.source_scope == "project"
            and preview.protocol_id is None
            and preview.preview_digest == preview_digest
            and preview.expires_at > utcnow()
            and canonical_digest(preview.recipe) == preview.recipe_digest
            and preview_identity_digest(preview) == preview.preview_digest
            and preview.summary.get("engine_version") == PROJECT_ENGINE_VERSION
            and not preview.ai_provenance
        )
    except (TypeError, ValueError, AttributeError):
        valid = False
    if not valid:
        raise HTTPException(
            409, "Project analysis preview changed or expired; preview again"
        )
    previous = await db.scalar(
        select(AnalysisRun).where(
            AnalysisRun.created_by_user_id == user.id,
            AnalysisRun.preview_digest == preview_digest,
        )
    )
    if previous is not None:
        await authorize_project_snapshot(db, previous, user)
        return previous
    params = ProjectPreviewRequest(
        project_id=preview.project_id,
        selection=preview.source_selection,
        recipe=preview.recipe,
        question=preview.question,
        pipeline_revision_id=preview.pipeline_revision_id,
        rerun_of_id=preview.rerun_of_id,
    )
    snapshot, project = await capture_project_sources(
        db, project_id=params.project_id, selection=params.selection, user=user
    )
    if canonical_digest(snapshot) != preview.source_digest:
        raise HTTPException(409, "Project analysis sources changed; preview again")
    await validate_project_lineage(db, params, user, snapshot=snapshot)
    validate_project_recipe(params.recipe, snapshot)
    run = AnalysisRun(
        source_scope="project",
        project_id=project.id,
        protocol_id=None,
        created_by_user_id=user.id,
        pipeline_revision_id=preview.pipeline_revision_id,
        rerun_of_id=preview.rerun_of_id,
        question=preview.question,
        recipe=deepcopy(preview.recipe),
        source_selection=deepcopy(preview.source_selection),
        source_snapshot=snapshot,
        source_digest=preview.source_digest,
        recipe_digest=preview.recipe_digest,
        preview_digest=preview_digest,
        ai_provenance={},
        client_idempotency_key=key,
        engine_version=PROJECT_ENGINE_VERSION,
        status="pending",
    )
    db.add(run)
    await db.flush()
    for item in snapshot["inputs"]:
        db.add(
            AnalysisProjectInput(
                run_id=run.id,
                slot_id=item["slot_id"],
                protocol_id=UUID(item["snapshot"]["protocol_id"]),
                source_digest=canonical_digest(item["snapshot"]),
            )
        )
    await db.flush()
    job = await enqueue_job(
        db,
        kind="record_analysis",
        payload={"analysis_id": str(run.id)},
        idempotency_key=f"record-analysis:{run.id}",
        lab_id=project.lab_id,
    )
    run.job_id = job.id
    await db.flush()
    return run


async def revise_project_pipeline(db, pipeline, params, user):
    """An explicit revision may change source schemas; a rerun may not."""
    await authorize_project_pipeline(db, pipeline, user)
    if pipeline.current_revision != params.expected_revision:
        raise HTTPException(409, "Method changed; reload before revising")
    previous = await db.scalar(
        select(AnalysisPipelineRevision).where(
            AnalysisPipelineRevision.pipeline_id == pipeline.id,
            AnalysisPipelineRevision.revision == pipeline.current_revision,
        )
    )
    if previous is None:
        raise HTTPException(409, "Current Project method revision is missing")
    if not isinstance(params.recipe, ProjectAnalysisRecipe):
        raise HTTPException(409, "Changing analysis engines requires a separate method")
    if params.source_selection is not None and not isinstance(
        params.source_selection, ProjectAnalysisSelection
    ):
        raise HTTPException(409, "Project methods require explicit Project input slots")
    try:
        selection = ProjectAnalysisSelection.model_validate(
            params.source_selection or previous.source_selection
        )
        snapshot, _ = await capture_project_sources(
            db, project_id=pipeline.project_id, selection=selection, user=user
        )
        validate_project_recipe(params.recipe, snapshot)
    except AnalysisError as exc:
        raise HTTPException(422, str(exc)) from exc
    recipe = params.recipe.model_dump(mode="json")
    stored_selection = project_selection_payload(selection)
    provenance = {
        "parent_revision_id": str(previous.id),
        "parent_recipe_digest": previous.recipe_digest,
        "engine_version": PROJECT_ENGINE_VERSION,
        "input_contracts": project_input_contracts(snapshot),
    }
    provenance["method_digest"] = method_revision_digest(
        recipe, stored_selection, provenance
    )
    revision = AnalysisPipelineRevision(
        pipeline_id=pipeline.id,
        revision=pipeline.current_revision + 1,
        recipe=recipe,
        recipe_digest=canonical_digest(recipe),
        source_selection=stored_selection,
        provenance=provenance,
        created_by_user_id=user.id,
    )
    db.add(revision)
    pipeline.current_revision += 1
    await db.flush()
    return revision


Judgement = Literal["supports", "contradicts", "inconclusive"]


class ProjectInterpretationFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,23}$")
    field: str = Field(min_length=1, max_length=255)
    relation: Judgement
    note: str = Field(min_length=1, max_length=4000)


class ProjectInterpretationContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    judgement: Judgement
    summary: str = Field(min_length=1, max_length=8000)
    findings: list[ProjectInterpretationFinding] = Field(min_length=2, max_length=40)
    limitations: list[str] = Field(default_factory=list, max_length=40)
    unanswered_questions: list[str] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def bounded_evidence(self):
        if len({finding.slot_id for finding in self.findings}) < 2:
            raise ValueError(
                "A Project interpretation must cite at least two source slots"
            )
        if len({(finding.slot_id, finding.field) for finding in self.findings}) != len(
            self.findings
        ):
            raise ValueError("Cite each source field only once")
        if not self.summary.strip() or any(
            not item.note.strip() for item in self.findings
        ):
            raise ValueError(
                "Interpretation summary and evidence notes cannot be blank"
            )
        if any(
            not item.strip() or len(item) > 4000
            for item in self.limitations + self.unanswered_questions
        ):
            raise ValueError(
                "Limitations and questions must contain 1 to 4000 characters"
            )
        return self


class ProjectInterpretationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0, strict=True)
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    content: ProjectInterpretationContent


def interpretation_evidence(result, content):
    """Resolve citations only from the actual sealed numeric outputs, not user text."""
    try:
        local = {row["slot_id"]: row for row in result["local_results"]}
        if len(local) != len(result["local_results"]):
            raise ValueError("Duplicate local result slots")
        evidence = []
        for finding in content.findings:
            row = local[finding.slot_id]
            report = row["report"]
            fields = {field["key"]: field for field in report["fields"]}
            if finding.field not in fields or fields[finding.field]["type"] not in {
                "number",
                "integer",
            }:
                raise ValueError(
                    "Interpretations must cite an actually computed numeric field"
                )
            evidence.append(
                {
                    "slot_id": finding.slot_id,
                    "field": finding.field,
                    "source_digest": row["source_digest"],
                    "recipe_digest": row["recipe_digest"],
                    "field_schema": deepcopy(fields[finding.field]),
                    "counts": deepcopy(report["counts"]),
                    "groups": [
                        {
                            "key": deepcopy(group["key"]),
                            "row_count": group["row_count"],
                            "statistics": deepcopy(group["fields"][finding.field]),
                        }
                        for group in report["groups"]
                    ],
                }
            )
        return evidence
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            422, "Cite actual computed numeric fields from at least two source slots"
        ) from exc


def interpretation_digest(row):
    return canonical_digest(
        {
            "analysis_run_id": str(row.analysis_run_id),
            "revision": row.revision,
            "result_digest": row.result_digest,
            "content": row.content,
            "resolved_evidence": row.resolved_evidence,
            "created_by_user_id": str(row.created_by_user_id),
        }
    )


async def _interpretation_run(db, analysis_id, user, *, lock=False):
    run = await db.scalar(
        select(AnalysisRun)
        .where(AnalysisRun.id == analysis_id)
        .execution_options(populate_existing=True)
    )
    if run is None:
        raise HTTPException(404, "Analysis not found")
    await authorize_project_snapshot(db, run, user)
    if lock:
        await db.refresh(run, with_for_update=True)
        await authorize_project_snapshot(db, run, user)
    if run.status != "succeeded":
        raise HTTPException(
            409, "An interpretation requires a successfully computed analysis"
        )
    return run


async def project_interpretations(db, analysis_id, user):
    run = await _interpretation_run(db, analysis_id, user)
    rows = list(
        (
            await db.scalars(
                select(AnalysisInterpretationRevision)
                .where(AnalysisInterpretationRevision.analysis_run_id == run.id)
                .order_by(AnalysisInterpretationRevision.revision)
            )
        ).all()
    )
    for number, row in enumerate(rows, 1):
        if (
            row.revision != number
            or row.result_digest != run.result_digest
            or row.content_digest != interpretation_digest(row)
        ):
            raise HTTPException(409, "Interpretation revision integrity check failed")
        if row.resolved_evidence != interpretation_evidence(
            run.result, ProjectInterpretationContent.model_validate(row.content)
        ):
            raise HTTPException(409, "Interpretation evidence changed")
    return {
        "analysis_id": str(run.id),
        "result_digest": run.result_digest,
        "current_revision": len(rows),
        "items": [row.as_dict() for row in rows],
    }


async def create_project_interpretation(db, analysis_id, params, user):
    run = await _interpretation_run(db, analysis_id, user, lock=True)
    current = await project_interpretations(db, run.id, user)
    if (
        params.expected_revision != current["current_revision"]
        or params.result_digest != run.result_digest
    ):
        raise HTTPException(
            409, "Analysis result or interpretation changed; reload before revising"
        )
    evidence = interpretation_evidence(run.result, params.content)
    row = AnalysisInterpretationRevision(
        analysis_run_id=run.id,
        revision=current["current_revision"] + 1,
        result_digest=run.result_digest,
        content=params.content.model_dump(mode="json"),
        resolved_evidence=evidence,
        created_by_user_id=user.id,
    )
    row.content_digest = interpretation_digest(row)
    db.add(row)
    await db.flush()
    return row


def project_result_comparison(current, baseline):
    if current.project_id != baseline.project_id or project_input_contracts(
        current.source_snapshot
    ) != project_input_contracts(baseline.source_snapshot):
        raise HTTPException(
            409,
            "Compare analyses with the same Project input slots, Protocols and exact Schemas",
        )
    old_inputs = {
        item["slot_id"]: item["snapshot"] for item in baseline.source_snapshot["inputs"]
    }
    differences = []

    def ref(row):
        return {
            key: row[key]
            for key in (
                "record_id",
                "record_version",
                "record_hash",
                "protocol_version",
            )
        }

    for item in current.source_snapshot["inputs"]:
        now = {row["record_id"]: ref(row) for row in item["snapshot"]["records"]}
        before = {
            row["record_id"]: ref(row) for row in old_inputs[item["slot_id"]]["records"]
        }
        differences.append(
            {
                "slot_id": item["slot_id"],
                "protocol_id": item["snapshot"]["protocol_id"],
                "added": [now[key] for key in sorted(now.keys() - before.keys())],
                "removed": [before[key] for key in sorted(before.keys() - now.keys())],
                "changed": [
                    {"before": before[key], "after": now[key]}
                    for key in sorted(now.keys() & before.keys())
                    if now[key] != before[key]
                ],
            }
        )
    old_local = {row["slot_id"]: row for row in baseline.result["local_results"]}
    local = [
        {
            "slot_id": row["slot_id"],
            "changed": canonical_digest(old_local[row["slot_id"]]["report"])
            != canonical_digest(row["report"]),
            "before": deepcopy(old_local[row["slot_id"]]["report"]),
            "after": deepcopy(row["report"]),
        }
        for row in current.result["local_results"]
    ]
    return {
        "analysis_id": str(current.id),
        "baseline_id": str(baseline.id),
        "current_result_digest": current.result_digest,
        "baseline_result_digest": baseline.result_digest,
        "recipe_changed": current.recipe_digest != baseline.recipe_digest,
        "inputs": differences,
        "local_results": local,
        "join": {
            "changed": current.result.get("join") != baseline.result.get("join"),
            "before": deepcopy(baseline.result.get("join")),
            "after": deepcopy(current.result.get("join")),
        },
        "warnings": [
            "Comparisons describe computed differences, not causation or an automatic scientific judgement"
        ],
    }


async def compare_project_analyses(db, analysis_id, baseline_id, user):
    current = await _interpretation_run(db, analysis_id, user)
    baseline = await _interpretation_run(db, baseline_id, user)
    return project_result_comparison(current, baseline)
