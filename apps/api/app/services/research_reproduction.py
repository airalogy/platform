"""Deterministic context and validation for scientific replication review."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.research_runtime import canonical_digest


class ReproductionEvaluationError(ValueError):
    """Raised when a replication comparison is incomplete or inconsistent."""


class ReproductionCriterionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion: str = Field(min_length=1, max_length=4_000)
    status: Literal["reproduced", "not_reproduced", "inconclusive"]
    rationale: str = Field(min_length=1, max_length=20_000)

    @model_validator(mode="after")
    def normalize(self):
        self.criterion = self.criterion.strip()
        self.rationale = self.rationale.strip()
        if not self.criterion or not self.rationale:
            raise ValueError("Reproduction criterion and rationale cannot be blank")
        return self


class ReproductionAssessment(BaseModel):
    """Editable assessment draft; it becomes authoritative only after human review."""

    model_config = ConfigDict(extra="forbid")

    outcome: Literal[
        "reproduced",
        "partially_reproduced",
        "not_reproduced",
        "inconclusive",
    ]
    summary: str = Field(min_length=1, max_length=100_000)
    criteria_results: list[ReproductionCriterionResult] = Field(
        default_factory=list, max_length=100
    )
    source_evidence_ids: list[str] = Field(default_factory=list, max_length=100)
    replication_evidence_ids: list[str] = Field(default_factory=list, max_length=100)
    deviations: list[str] = Field(default_factory=list, max_length=100)
    limitations: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def normalize(self):
        self.summary = self.summary.strip()
        if not self.summary:
            raise ValueError("Reproduction summary cannot be blank")
        for field_name in (
            "source_evidence_ids",
            "replication_evidence_ids",
            "deviations",
            "limitations",
        ):
            values = [
                item.strip() for item in getattr(self, field_name) if item.strip()
            ]
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} contains duplicates")
            if any(len(item) > 4_000 for item in values):
                raise ValueError(f"{field_name} contains an oversized item")
            setattr(self, field_name, values)
        overlap = set(self.source_evidence_ids) & set(self.replication_evidence_ids)
        if overlap:
            raise ValueError(
                "Evidence cannot belong to both source and replication selections"
            )
        return self


def effective_environment_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Remove Run lineage metadata before comparing executable environments."""

    result = deepcopy(snapshot)
    result.pop("run_origin", None)
    return result


def _validated_evidence(items: Any, *, run_id: str | None = None) -> list[dict]:
    result: list[dict] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        if item.get("quality_state") != "validated":
            continue
        if run_id is not None and str(item.get("run_id") or "") != run_id:
            continue
        result.append(
            {
                "id": str(item["id"]),
                "run_id": str(item.get("run_id") or ""),
                "kind": str(item.get("kind") or ""),
                "summary": str(item.get("summary") or ""),
                "artifact_type": str(item.get("artifact_type") or ""),
                "artifact_id": str(item.get("artifact_id") or ""),
                "artifact_version": str(item.get("artifact_version") or ""),
                "quality_state": "validated",
            }
        )
    return result


def build_reproduction_context(
    *,
    task_id: str,
    success_criteria: list[str],
    source_run_id: str,
    source_run_number: int,
    source_environment: dict[str, Any],
    source_result_package: dict[str, Any],
    source_result_digest: str,
    source_snapshot_sealed: bool,
    replication_run_id: str,
    replication_run_number: int,
    replication_environment: dict[str, Any],
    task_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a bounded, provenance-checked comparison context for one replication."""

    origin = replication_environment.get("run_origin")
    if not isinstance(origin, dict) or origin.get("kind") != "replication":
        raise ReproductionEvaluationError(
            "Replication Run is missing its immutable replication origin"
        )
    if str(origin.get("source_run_id") or "") != source_run_id:
        raise ReproductionEvaluationError("Replication source Run lineage has changed")
    package_task_id = str(source_result_package.get("task_id") or "")
    package_run_id = str(source_result_package.get("run_id") or "")
    if package_task_id and package_task_id != task_id:
        raise ReproductionEvaluationError(
            "Replication source result belongs to another Research Task"
        )
    if package_run_id and package_run_id != source_run_id:
        raise ReproductionEvaluationError(
            "Replication source result belongs to another Research Run"
        )

    source_environment_digest = canonical_digest(source_environment)
    source_effective_digest = canonical_digest(
        effective_environment_snapshot(source_environment)
    )
    replication_environment_digest = canonical_digest(replication_environment)
    replication_effective_digest = canonical_digest(
        effective_environment_snapshot(replication_environment)
    )
    actual_source_result_digest = canonical_digest(source_result_package)
    recorded_environment_digest = str(origin.get("source_environment_digest") or "")
    recorded_result_digest = str(origin.get("source_result_digest") or "")
    lineage_intact = (
        origin.get("source_run_number") == source_run_number
        and recorded_environment_digest == source_environment_digest
        and recorded_result_digest == source_result_digest
        and actual_source_result_digest == source_result_digest
    )

    return {
        "schema": "airalogy.reproduction-context.v1",
        "task_id": task_id,
        "kind": "replication",
        "success_criteria": list(success_criteria),
        "source_run": {
            "id": source_run_id,
            "run_number": source_run_number,
            "environment_digest": source_environment_digest,
            "effective_environment_digest": source_effective_digest,
            "result_digest": source_result_digest,
            "snapshot_sealed": source_snapshot_sealed,
        },
        "replication_run": {
            "id": replication_run_id,
            "run_number": replication_run_number,
            "environment_digest": replication_environment_digest,
            "effective_environment_digest": replication_effective_digest,
        },
        "lineage_intact": lineage_intact,
        "environment_equivalent": (
            source_effective_digest == replication_effective_digest
        ),
        "source_evidence": _validated_evidence(
            source_result_package.get("evidence"), run_id=source_run_id
        ),
        "replication_evidence": _validated_evidence(
            task_evidence, run_id=replication_run_id
        ),
    }


def validate_reproduction_assessment(
    assessment: ReproductionAssessment,
    *,
    context: dict[str, Any],
) -> None:
    """Bind a scientific comparison to exact criteria and scoped validated Evidence."""

    if context.get("schema") != "airalogy.reproduction-context.v1":
        raise ReproductionEvaluationError("Unsupported reproduction context")
    if not context.get("lineage_intact"):
        raise ReproductionEvaluationError(
            "Replication lineage is not intact; start a new replication Run"
        )
    if not context.get("environment_equivalent"):
        raise ReproductionEvaluationError(
            "Replication Research Environment differs from its source Run"
        )

    expected_criteria = [str(item) for item in context.get("success_criteria") or []]
    actual_criteria = [item.criterion for item in assessment.criteria_results]
    if actual_criteria != expected_criteria:
        raise ReproductionEvaluationError(
            "Reproduction assessment must evaluate every success criterion in order"
        )

    source_ids = {
        str(item["id"])
        for item in context.get("source_evidence") or []
        if isinstance(item, dict) and item.get("id")
    }
    replication_ids = {
        str(item["id"])
        for item in context.get("replication_evidence") or []
        if isinstance(item, dict) and item.get("id")
    }
    if unknown := set(assessment.source_evidence_ids) - source_ids:
        raise ReproductionEvaluationError(
            "Source Evidence is outside the sealed source result: "
            + ", ".join(sorted(unknown))
        )
    if unknown := set(assessment.replication_evidence_ids) - replication_ids:
        raise ReproductionEvaluationError(
            "Replication Evidence is outside the current replication Run: "
            + ", ".join(sorted(unknown))
        )
    if assessment.outcome != "inconclusive" and (
        not assessment.source_evidence_ids or not assessment.replication_evidence_ids
    ):
        raise ReproductionEvaluationError(
            "A conclusive reproduction outcome requires validated Evidence from both Runs"
        )

    statuses = [item.status for item in assessment.criteria_results]
    if assessment.outcome == "reproduced" and any(
        status != "reproduced" for status in statuses
    ):
        raise ReproductionEvaluationError(
            "A reproduced outcome requires every criterion to be reproduced"
        )
    if assessment.outcome == "not_reproduced" and "not_reproduced" not in statuses:
        raise ReproductionEvaluationError(
            "A not-reproduced outcome requires a failed criterion"
        )
    if assessment.outcome == "partially_reproduced" and not (
        "reproduced" in statuses and any(status != "reproduced" for status in statuses)
    ):
        raise ReproductionEvaluationError(
            "A partially reproduced outcome requires both reproduced and unresolved or failed criteria"
        )


def finalized_reproduction_evaluation(
    *,
    context: dict[str, Any],
    assessment: ReproductionAssessment,
    reviewed_by_user_id: str,
    reviewed_at: str,
    review_recommendation_id: str | None,
) -> dict[str, Any]:
    validate_reproduction_assessment(assessment, context=context)
    return {
        "schema": "airalogy.replication-evaluation.v1",
        "context_digest": canonical_digest(context),
        "source_run": context["source_run"],
        "replication_run": context["replication_run"],
        "lineage_intact": context["lineage_intact"],
        "environment_equivalent": context["environment_equivalent"],
        "assessment": assessment.model_dump(mode="json"),
        "reviewed_by_user_id": reviewed_by_user_id,
        "reviewed_at": reviewed_at,
        "review_recommendation_id": review_recommendation_id,
    }
