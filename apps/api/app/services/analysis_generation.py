"""Private, source-authorized and idempotent Aira analysis generation.

Generation is a paid, bounded suggestion attempt, never a numeric execution job.
Reserve attempts before contacting Masterbrain and never retry them implicitly.
"""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.libs.masterbrain import build_masterbrain_aira_model
from app.models.analysis_ai import AnalysisAIRequest
from app.models.user import User
from app.services.analysis_ai import (
    generate_analysis_draft,
    generate_analysis_interpretation,
    ground_interpretation,
    interpretation_result_context,
)
from app.services.analysis_compute_ai import (
    compute_interpretation_result_context,
    generate_analysis_compute_draft,
    generate_analysis_compute_interpretation,
    ground_compute_interpretation,
)
from app.services.analysis_compute_contracts import (
    COMPUTE_ENGINE_VERSION,
    AnalysisComputeRecipe,
)
from app.services.analysis_engine import AnalysisError, AnalysisRecipe, canonical_digest
from app.services.model_usage import create_usage_context
from app.services.record_analyses import (
    AnalysisSelection,
    analysis_scope,
    authorize_source_manifest,
    capture_sources,
    owned_run,
    utcnow,
)

MODEL_TIMEOUT_SECONDS = 60
MAX_AI_CONTEXT_BYTES = 60_000
MAX_FOLLOWUPS = 8


class DraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    protocol_id: UUID
    selection: AnalysisSelection
    question: str = Field(min_length=1, max_length=4000)
    locale: Literal["en-US", "zh-CN"] = "en-US"
    previous_request_id: UUID | None = None

    @field_validator("question")
    @classmethod
    def nonblank_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Ask a research question before generating a draft")
        return value.strip()


class InterpretationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    question: str = Field(default="", max_length=4000)
    locale: Literal["en-US", "zh-CN"] = "en-US"

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        return value.strip()


class ComputeDraftRequest(DraftRequest):
    environment_revision_id: UUID
    language: Literal["python", "r"]


async def _compute_environment_context(db, project, user, revision_id, language):
    from app.services.analysis_compute import authorized_analysis_environment
    from app.services.research_compute import compute_environment_snapshot
    from app.services.research_runtime import require_research_capability

    await require_research_capability(
        db, user=user, project=project, capability="research.compute.use"
    )
    environment, revision = await authorized_analysis_environment(
        db, project, revision_id, language
    )
    return compute_environment_snapshot(environment, revision)


async def _interpretation_run(db, analysis_id, user):
    run = await owned_run(db, analysis_id, user)
    if run.engine_version == COMPUTE_ENGINE_VERSION:
        from app.services.analysis_compute import owned_compute

        # Checks the approved source, actual completed receipt and private outputs,
        # not just a standalone report checksum. Historical reads need no Runner.
        run, _, _ = await owned_compute(db, analysis_id, user)
    return run


def request_payload(row: AnalysisAIRequest) -> dict:
    return row.as_dict(excludes=["input_context", "source_manifest"])


def input_digest(row: AnalysisAIRequest) -> str:
    return canonical_digest(
        {
            "id": str(row.id),
            "kind": row.kind,
            "owner": str(row.created_by_user_id),
            "project": str(row.project_id),
            "protocol": str(row.protocol_id),
            "analysis_run_id": str(row.analysis_run_id)
            if row.analysis_run_id
            else None,
            "previous_request_id": str(row.previous_request_id)
            if row.previous_request_id
            else None,
            "question": row.question,
            "locale": row.locale,
            "model": row.model,
            "operation_id": row.operation_id,
            "request_fingerprint": row.request_fingerprint,
            "source_digest": row.source_digest,
            "source_selection": row.source_selection,
            "source_manifest": row.source_manifest,
            "input_context": row.input_context,
        }
    )


def verify_request_integrity(row: AnalysisAIRequest) -> None:
    try:
        valid = input_digest(row) == row.input_digest and (
            row.output is None
            and row.output_digest is None
            and row.state != "generated"
            or row.state == "generated"
            and row.output is not None
            and canonical_digest(row.output) == row.output_digest
        )
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise HTTPException(409, "Aira analysis generation integrity check failed")


async def owned_ai_request(
    db: AsyncSession, request_id: UUID, user: User, *, visited: set[UUID] | None = None
) -> AnalysisAIRequest:
    visited = set() if visited is None else set(visited)
    if request_id in visited or len(visited) > MAX_FOLLOWUPS:
        raise HTTPException(409, "Invalid Aira analysis follow-up chain")
    visited.add(request_id)
    row = await db.get(AnalysisAIRequest, request_id, populate_existing=True)
    if row is None or row.created_by_user_id != user.id:
        raise HTTPException(404, "Aira analysis generation not found")
    _, project, own_only = await analysis_scope(db, row.protocol_id, user)
    if project.id != row.project_id:
        raise HTTPException(409, "Aira analysis scope changed")
    verify_request_integrity(row)
    await authorize_source_manifest(
        db, row.protocol_id, user, row.source_manifest, own_only=own_only
    )
    if row.previous_request_id:
        await owned_ai_request(db, row.previous_request_id, user, visited=visited)
    if row.analysis_run_id:
        run = await _interpretation_run(db, row.analysis_run_id, user)
        if run.result_digest != row.input_context.get("result_digest"):
            raise HTTPException(409, "Aira interpretation result changed")
    return row


async def settle_interrupted_request(db: AsyncSession, row: AnalysisAIRequest) -> None:
    if row.state == "generating" and row.deadline <= utcnow():
        await db.refresh(row, with_for_update=True)
        if row.state == "generating" and row.deadline <= utcnow():
            row.state, row.error = "failed", "generation_interrupted"
            row.finished_at = utcnow()
            await db.flush()


def _manifest(snapshot: dict) -> list[dict]:
    return [
        {"record_id": row["record_id"], "record_version": row["record_version"]}
        for row in snapshot["records"]
    ]


def _require_bounded_context(value: dict, maximum=MAX_AI_CONTEXT_BYTES) -> None:
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode()) > maximum:
        raise HTTPException(
            422,
            "Aira analysis context is too large; narrow the fields or data scope, or use manual analysis",
        )


async def generate_request(
    db: AsyncSession,
    params: DraftRequest | InterpretationRequest,
    user: User,
    *,
    analysis_id: UUID | None = None,
) -> AnalysisAIRequest:
    if isinstance(params, DraftRequest) != (analysis_id is None):
        raise HTTPException(422, "Aira request kind does not match the target")
    kind = (
        "interpretation"
        if analysis_id
        else "compute_draft"
        if isinstance(params, ComputeDraftRequest)
        else "draft"
    )
    fingerprint = canonical_digest(
        {
            "kind": kind,
            "analysis_id": str(analysis_id) if analysis_id else None,
            "request": params.model_dump(mode="json", exclude={"id"}),
        }
    )
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    existing = await db.get(AnalysisAIRequest, params.id)
    if existing is not None:
        row = await owned_ai_request(db, params.id, user)
        if row.request_fingerprint != fingerprint:
            raise HTTPException(
                409, "Aira request identity belongs to another question or data scope"
            )
        await settle_interrupted_request(db, row)
        await db.commit()
        return row
    if not config.effective_ai_enabled:
        raise HTTPException(
            503, "Aira is unavailable; manual analysis remains available"
        )
    previous = None
    if isinstance(params, DraftRequest):
        snapshot, protocol, project = await capture_sources(
            db, protocol_id=params.protocol_id, user=user, selection=params.selection
        )
        if params.previous_request_id:
            previous = await owned_ai_request(db, params.previous_request_id, user)
            if (
                previous.kind != kind
                or previous.state != "generated"
                or previous.protocol_id != protocol.id
            ):
                raise HTTPException(
                    409, "Follow up a completed draft in the same Protocol"
                )
            if isinstance(params, ComputeDraftRequest) and (
                previous.input_context.get("environment", {}).get("source_revision_id")
                != str(params.environment_revision_id)
                or previous.input_context.get("language") != params.language
            ):
                raise HTTPException(
                    409, "Follow up in the same Compute Environment and language"
                )
        depth = previous.input_context.get("followup_depth", 0) + 1 if previous else 0
        if depth > MAX_FOLLOWUPS:
            raise HTTPException(422, "Start a new question after eight Aira follow-ups")
        selection = params.selection.model_dump(mode="json", exclude_none=True)
        source_digest = canonical_digest(snapshot)
        context = {
            "fields": snapshot["fields"],
            "selection_summary": {
                "record_count": len(snapshot["records"]),
                "mode": params.selection.mode,
                "scope_digest": canonical_digest(selection),
                "filters": {
                    key: value
                    for key, value in selection.get("filters", {}).items()
                    if key != "user_id"
                },
                "submitter_filter_applied": bool(
                    selection.get("filters", {}).get("user_id")
                ),
                "protocol_versions": [s["version"] for s in snapshot["schemas"]],
            },
            "previous_draft": previous.output if previous else None,
            "followup_depth": depth,
        }
        if isinstance(params, ComputeDraftRequest):
            context["environment"] = await _compute_environment_context(
                db, project, user, params.environment_revision_id, params.language
            )
            context["language"] = params.language
    else:
        if analysis_id is None:
            raise HTTPException(422, "Select a computed report to interpret")
        run = await _interpretation_run(db, analysis_id, user)
        if run.status != "succeeded":
            raise HTTPException(
                409, "Aira can only interpret a successfully computed report"
            )
        is_compute = run.engine_version == COMPUTE_ENGINE_VERSION
        if not is_compute and not run.result.get("groups"):
            raise HTTPException(422, "There are no included Record groups to interpret")
        protocol, project, _ = await analysis_scope(db, run.protocol_id, user)
        snapshot, selection, source_digest = (
            run.source_snapshot,
            run.source_selection,
            run.source_digest,
        )
        context = {
            "result": compute_interpretation_result_context(run.result)
            if is_compute
            else interpretation_result_context(run.result),
            "result_digest": run.result_digest,
            "recipe_digest": run.recipe_digest,
            "analysis_question": run.question
            or (
                "解释已计算的结果，指出局限和后续检查。"
                if params.locale == "zh-CN"
                else "Explain the computed results, their limitations, and useful next checks."
            ),
        }
        if is_compute:
            context["result_kind"] = "compute"
        else:
            context["recipe"] = run.recipe
    _require_bounded_context(
        context,
        262144
        if kind == "compute_draft"
        else 1048576 + 60000
        if context.get("result_kind") == "compute"
        else MAX_AI_CONTEXT_BYTES,
    )
    model = build_masterbrain_aira_model(config.CHAT_MODEL_ACCURATE)
    usage = create_usage_context(
        feature=f"analysis.{kind}",
        user_id=user.id,
        lab_id=project.lab_id,
        project_id=project.id,
        attributes={
            "analysis_ai_request_id": str(params.id),
            "protocol_id": str(protocol.id),
        },
    )
    row = AnalysisAIRequest(
        id=params.id,
        kind=kind,
        project_id=project.id,
        protocol_id=protocol.id,
        created_by_user_id=user.id,
        analysis_run_id=analysis_id,
        previous_request_id=previous.id if previous else None,
        question=params.question,
        locale=params.locale,
        model=model,
        operation_id=usage.operation_id,
        request_fingerprint=fingerprint,
        source_selection=selection,
        source_manifest=_manifest(snapshot),
        source_digest=source_digest,
        input_context=context,
        state="generating",
        deadline=utcnow() + timedelta(seconds=MODEL_TIMEOUT_SECONDS + 15),
    )
    row.input_digest = input_digest(row)
    db.add(row)
    await (
        db.commit()
    )  # Persist paid-attempt identity; release every lock before model latency.
    error, output = None, None
    try:
        async with asyncio.timeout(MODEL_TIMEOUT_SECONDS):
            if row.kind == "draft":
                generated = await generate_analysis_draft(
                    question=row.question,
                    locale=row.locale,
                    field_catalog=context["fields"],
                    selection_summary=context["selection_summary"],
                    previous_draft=context["previous_draft"],
                    model_name=model,
                    usage_context=usage,
                )
                output = generated.model_dump(mode="json")
            elif row.kind == "compute_draft":
                generated = await generate_analysis_compute_draft(
                    question=row.question,
                    locale=row.locale,
                    field_catalog=context["fields"],
                    selection_summary=context["selection_summary"],
                    environment=context["environment"],
                    language=context["language"],
                    previous_draft=context["previous_draft"],
                    model_name=model,
                    usage_context=usage,
                )
                output = generated.model_dump(mode="json")
            elif context.get("result_kind") == "compute":
                generated = await generate_analysis_compute_interpretation(
                    question=row.question or context["analysis_question"],
                    locale=row.locale,
                    result=context["result"],
                    model_name=model,
                    usage_context=usage,
                )
                output = ground_compute_interpretation(generated, context["result"])
            else:
                generated = await generate_analysis_interpretation(
                    question=row.question or context["analysis_question"],
                    locale=row.locale,
                    result=context["result"],
                    model_name=model,
                    usage_context=usage,
                )
                output = ground_interpretation(generated, context["result"])
    except TimeoutError:
        error = "model_timeout"
    except (ValueError, TypeError, KeyError):
        error = "invalid_proposal"
    except Exception:
        error = "model_unavailable"  # Never persist provider bodies, endpoints or credentials.
    await db.refresh(row, with_for_update=True)
    if row.state != "generating":
        await db.commit()
        return await owned_ai_request(db, row.id, user)
    if row.deadline <= utcnow():
        error = "generation_interrupted"
    if not config.effective_ai_enabled:
        error = "ai_disabled"
    try:
        await owned_ai_request(db, row.id, user)
        if row.kind in {"draft", "compute_draft"}:
            current, _, current_project = await capture_sources(
                db,
                protocol_id=row.protocol_id,
                user=user,
                selection=AnalysisSelection.model_validate(row.source_selection),
            )
            if canonical_digest(current) != row.source_digest:
                error = "context_changed"
            if row.kind == "compute_draft":
                current_environment = await _compute_environment_context(
                    db,
                    current_project,
                    user,
                    UUID(context["environment"]["source_revision_id"]),
                    context["language"],
                )
                if current_environment != context["environment"]:
                    error = "context_changed"
        else:
            current_run = await _interpretation_run(db, row.analysis_run_id, user)
            if current_run.result_digest != context["result_digest"]:
                error = "context_changed"
    except (HTTPException, AnalysisError):
        error = "source_access_changed"
    row.state = "failed" if error else "generated"
    row.error = error
    row.output = None if error else output
    row.output_digest = None if error else canonical_digest(output)
    row.finished_at = utcnow()
    await db.commit()
    # A revoked caller must not receive even saved draft text from the response.
    return await owned_ai_request(db, row.id, user)


def verify_ai_provenance(provenance: dict) -> None:
    if not provenance:
        return
    try:
        valid = isinstance(provenance, dict) and canonical_digest(
            {key: value for key, value in provenance.items() if key != "digest"}
        ) == provenance.get("digest")
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise HTTPException(409, "Analysis AI provenance integrity check failed")


async def authorize_ai_provenance(
    db: AsyncSession, provenance: dict, user: User
) -> None:
    verify_ai_provenance(provenance)
    try:
        request_id = UUID(provenance["request_id"])
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(409, "Invalid analysis AI provenance reference") from exc
    candidate = await db.get(AnalysisAIRequest, request_id, populate_existing=True)
    if candidate is None or candidate.created_by_user_id != user.id:
        raise HTTPException(404, "Aira analysis generation not found")
    # Check this edge before traversing any run/reference. Interpretations point
    # back to a report and can never be that report's source-code provenance.
    if candidate.kind not in {"draft", "compute_draft"}:
        raise HTTPException(409, "Only an analysis draft can be execution provenance")
    row = await owned_ai_request(db, request_id, user)
    if (
        row.kind not in {"draft", "compute_draft"}
        or row.state != "generated"
        or row.output.get("mode")
        != ("compute" if row.kind == "compute_draft" else "builtin")
        or row.input_digest != provenance.get("input_digest")
        or row.output_digest != provenance.get("output_digest")
        or row.output != provenance.get("generation")
        or row.model != provenance.get("model")
        or row.source_digest != provenance.get("source_digest")
    ):
        raise HTTPException(409, "Analysis AI provenance no longer matches its source")


async def draft_provenance(
    db: AsyncSession,
    request_id: UUID,
    user: User,
    *,
    protocol_id: UUID,
    source_digest: str,
    recipe: AnalysisRecipe | AnalysisComputeRecipe,
    question: str,
    environment: dict | None = None,
) -> dict:
    row = await owned_ai_request(db, request_id, user)
    is_compute = isinstance(recipe, AnalysisComputeRecipe)
    if (
        row.kind != ("compute_draft" if is_compute else "draft")
        or row.state != "generated"
        or row.output.get("mode") != ("compute" if is_compute else "builtin")
    ):
        raise HTTPException(409, "Select a generated draft for this analysis engine")
    if row.protocol_id != protocol_id or row.source_digest != source_digest:
        raise HTTPException(
            409,
            "Aira draft sources changed; regenerate or explicitly start a manual analysis",
        )
    if is_compute and (
        row.input_context.get("environment", {}).get("source_revision_id")
        != str(recipe.environment_revision_id)
        or row.input_context.get("language") != recipe.language
        or row.input_context.get("environment") != environment
    ):
        raise HTTPException(
            409, "Aira draft environment changed; regenerate or start a manual analysis"
        )
    provenance = {
        "request_id": str(row.id),
        "model": row.model,
        "operation_id": row.operation_id,
        "input_digest": row.input_digest,
        "output_digest": row.output_digest,
        "source_digest": row.source_digest,
        "generated_at": row.finished_at.isoformat(),
        "generation_question": row.question,
        "generation": row.output,
        "user_edited": row.output["recipe"] != recipe.model_dump(mode="json")
        or row.question != question,
    }
    provenance["digest"] = canonical_digest(provenance)
    return provenance


def inherited_provenance(
    provenance: dict, recipe: AnalysisRecipe | AnalysisComputeRecipe
) -> dict:
    if not provenance:
        return {}
    verify_ai_provenance(provenance)
    if provenance.get("generation", {}).get("mode") != (
        "compute" if isinstance(recipe, AnalysisComputeRecipe) else "builtin"
    ):
        raise HTTPException(
            409, "AI provenance cannot be converted between analysis engines"
        )
    result = {key: value for key, value in provenance.items() if key != "digest"}
    result["inherited"] = True
    result["user_edited"] = result.get("user_edited", False) or result["generation"][
        "recipe"
    ] != recipe.model_dump(mode="json")
    result["digest"] = canonical_digest(result)
    return result
