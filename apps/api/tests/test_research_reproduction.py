import asyncio
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.research import (
    ResearchResultPackageSnapshot,
    ResearchReviewRecommendation,
)
from app.routers.research_tasks import TaskCompleteParams, _reproduction_context
from app.services.research_reproduction import (
    ReproductionAssessment,
    ReproductionEvaluationError,
    build_reproduction_context,
    effective_environment_snapshot,
    finalized_reproduction_evaluation,
    validate_reproduction_assessment,
)
from app.services.research_runtime import canonical_digest


def _fixture():
    task_id = str(uuid4())
    source_run_id = str(uuid4())
    replication_run_id = str(uuid4())
    source_evidence_id = str(uuid4())
    replication_evidence_id = str(uuid4())
    source_environment = {
        "schema": "airalogy.research-environment.v2",
        "protocols": [{"id": "protocol", "version": "1.0.0"}],
    }
    source_package = {
        "schema": "airalogy.research-result-package.v1",
        "task_id": task_id,
        "run_id": source_run_id,
        "evidence": [
            {
                "id": source_evidence_id,
                "run_id": source_run_id,
                "kind": "measurement",
                "summary": "Validated source measurement",
                "artifact_type": "data_asset",
                "artifact_id": str(uuid4()),
                "artifact_version": "1",
                "quality_state": "validated",
            },
            {
                "id": str(uuid4()),
                "run_id": source_run_id,
                "quality_state": "rejected",
            },
            {
                "id": str(uuid4()),
                "run_id": str(uuid4()),
                "kind": "measurement",
                "quality_state": "validated",
            },
        ],
    }
    source_result_digest = canonical_digest(source_package)
    replication_environment = {
        **source_environment,
        "run_origin": {
            "kind": "replication",
            "source_run_id": source_run_id,
            "source_run_number": 1,
            "source_environment_digest": canonical_digest(source_environment),
            "source_result_digest": source_result_digest,
        },
    }
    task_evidence = [
        {
            "id": replication_evidence_id,
            "run_id": replication_run_id,
            "kind": "measurement",
            "summary": "Validated replication measurement",
            "artifact_type": "data_asset",
            "artifact_id": str(uuid4()),
            "artifact_version": "1",
            "quality_state": "validated",
        },
        {
            "id": str(uuid4()),
            "run_id": source_run_id,
            "kind": "measurement",
            "quality_state": "validated",
        },
    ]
    context = build_reproduction_context(
        task_id=task_id,
        success_criteria=["Effect direction matches", "Magnitude is within tolerance"],
        source_run_id=source_run_id,
        source_run_number=1,
        source_environment=source_environment,
        source_result_package=source_package,
        source_result_digest=source_result_digest,
        source_snapshot_sealed=True,
        replication_run_id=replication_run_id,
        replication_run_number=2,
        replication_environment=replication_environment,
        task_evidence=task_evidence,
    )
    assessment = ReproductionAssessment(
        outcome="reproduced",
        summary="Both predefined criteria reproduced under the pinned environment.",
        criteria_results=[
            {
                "criterion": "Effect direction matches",
                "status": "reproduced",
                "rationale": "Both validated measurements have the same direction.",
            },
            {
                "criterion": "Magnitude is within tolerance",
                "status": "reproduced",
                "rationale": "The observed difference is within the fixed tolerance.",
            },
        ],
        source_evidence_ids=[source_evidence_id],
        replication_evidence_ids=[replication_evidence_id],
        deviations=[],
        limitations=["Single-site replication"],
    )
    return context, assessment


def test_reproduction_context_checks_lineage_environment_and_run_scoped_evidence():
    context, _assessment = _fixture()

    assert context["lineage_intact"] is True
    assert context["environment_equivalent"] is True
    assert context["source_run"]["snapshot_sealed"] is True
    assert len(context["source_evidence"]) == 1
    assert len(context["replication_evidence"]) == 1
    assert context["source_evidence"][0]["run_id"] == context["source_run"]["id"]
    assert (
        context["replication_evidence"][0]["run_id"] == context["replication_run"]["id"]
    )


def test_effective_environment_excludes_only_run_lineage_metadata():
    snapshot = {
        "schema": "airalogy.research-environment.v2",
        "tools": [{"key": "literature.search", "version": "1"}],
        "run_origin": {"kind": "replication", "source_run_id": str(uuid4())},
    }

    assert effective_environment_snapshot(snapshot) == {
        "schema": "airalogy.research-environment.v2",
        "tools": [{"key": "literature.search", "version": "1"}],
    }
    assert "run_origin" in snapshot


def test_reproduction_assessment_is_bound_to_exact_criteria_and_both_evidence_sets():
    context, assessment = _fixture()

    validate_reproduction_assessment(assessment, context=context)

    with pytest.raises(ReproductionEvaluationError, match="every success criterion"):
        validate_reproduction_assessment(
            assessment.model_copy(
                update={"criteria_results": list(reversed(assessment.criteria_results))}
            ),
            context=context,
        )
    with pytest.raises(ReproductionEvaluationError, match="both Runs"):
        validate_reproduction_assessment(
            assessment.model_copy(update={"replication_evidence_ids": []}),
            context=context,
        )
    with pytest.raises(ReproductionEvaluationError, match="outside the sealed source"):
        validate_reproduction_assessment(
            assessment.model_copy(update={"source_evidence_ids": [str(uuid4())]}),
            context=context,
        )


def test_reproduction_outcome_must_match_criterion_level_results():
    context, assessment = _fixture()

    with pytest.raises(ReproductionEvaluationError, match="every criterion"):
        validate_reproduction_assessment(
            assessment.model_copy(
                update={
                    "criteria_results": [
                        assessment.criteria_results[0],
                        assessment.criteria_results[1].model_copy(
                            update={"status": "inconclusive"}
                        ),
                    ]
                }
            ),
            context=context,
        )

    partial = assessment.model_copy(
        update={
            "outcome": "partially_reproduced",
            "criteria_results": [
                assessment.criteria_results[0],
                assessment.criteria_results[1].model_copy(
                    update={"status": "not_reproduced"}
                ),
            ],
        }
    )
    validate_reproduction_assessment(partial, context=context)


def test_finalized_reproduction_evaluation_records_human_and_context_digest():
    context, assessment = _fixture()
    reviewer_id = str(uuid4())
    recommendation_id = str(uuid4())

    result = finalized_reproduction_evaluation(
        context=context,
        assessment=assessment,
        reviewed_by_user_id=reviewer_id,
        reviewed_at="2026-09-06T10:00:00+00:00",
        review_recommendation_id=recommendation_id,
    )

    assert result["schema"] == "airalogy.replication-evaluation.v1"
    assert result["context_digest"] == canonical_digest(context)
    assert result["assessment"]["outcome"] == "reproduced"
    assert result["reviewed_by_user_id"] == reviewer_id
    assert result["review_recommendation_id"] == recommendation_id


def test_complete_request_accepts_strict_replication_assessment_only():
    _context, assessment = _fixture()
    params = TaskCompleteParams(
        expected_revision=2,
        outcome="goal_met",
        scientific_outcome="supports_hypothesis",
        conclusion="The replication met the predefined criteria.",
        reproduction_assessment=assessment,
    )

    assert params.reproduction_assessment is not None
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TaskCompleteParams(
            expected_revision=2,
            outcome="goal_met",
            scientific_outcome="supports_hypothesis",
            conclusion="Invalid extra field",
            reproduction_assessment={
                **assessment.model_dump(),
                "approval": "accepted",
            },
        )


def test_reproduction_review_column_and_migration_are_chained():
    ddl = str(
        CreateTable(ResearchReviewRecommendation.__table__).compile(
            dialect=postgresql.dialect()
        )
    )
    migration = import_module(
        "migrations.versions.0046_research_reproduction_assessments"
    )

    assert "reproduction_assessment" in ddl
    assert migration.down_revision == "0045_instrument_safety_interlocks"
    assert migration.TABLE_NAME == "research_review_recommendations"


def test_context_rejects_changed_source_lineage():
    context, _assessment = _fixture()
    source = context["source_run"]
    replication = context["replication_run"]
    with pytest.raises(ReproductionEvaluationError, match="source Run lineage"):
        build_reproduction_context(
            task_id=context["task_id"],
            success_criteria=context["success_criteria"],
            source_run_id=source["id"],
            source_run_number=source["run_number"],
            source_environment={"schema": "airalogy.research-environment.v2"},
            source_result_package={"evidence": []},
            source_result_digest=canonical_digest({"evidence": []}),
            source_snapshot_sealed=True,
            replication_run_id=replication["id"],
            replication_run_number=replication["run_number"],
            replication_environment={
                "schema": "airalogy.research-environment.v2",
                "run_origin": {
                    "kind": "replication",
                    "source_run_id": str(uuid4()),
                    "source_run_number": source["run_number"],
                },
            },
            task_evidence=[],
        )


def test_router_context_prefers_and_verifies_sealed_source_snapshot(monkeypatch):
    task_id = uuid4()
    source_run_id = uuid4()
    replication_run_id = uuid4()
    source_environment = {"schema": "airalogy.research-environment.v2"}
    source_package = {
        "schema": "airalogy.research-result-package.v1",
        "task_id": str(task_id),
        "run_id": str(source_run_id),
        "evidence": [],
    }
    source_digest = canonical_digest(source_package)
    source_run = SimpleNamespace(
        id=source_run_id,
        task_id=task_id,
        run_number=1,
        environment_snapshot=source_environment,
        result_package={"changed": "unsealed row must not win"},
    )
    replication_run = SimpleNamespace(
        id=replication_run_id,
        task_id=task_id,
        run_number=2,
        environment_snapshot={
            **source_environment,
            "run_origin": {
                "kind": "replication",
                "source_run_id": str(source_run_id),
                "source_run_number": 1,
                "source_environment_digest": canonical_digest(source_environment),
                "source_result_digest": source_digest,
            },
        },
    )
    snapshot = SimpleNamespace(package=source_package, digest=source_digest)
    db_session = SimpleNamespace(get=AsyncMock(return_value=source_run))
    monkeypatch.setattr(
        ResearchResultPackageSnapshot,
        "find_by",
        AsyncMock(return_value=snapshot),
    )

    context = asyncio.run(
        _reproduction_context(
            db_session,
            SimpleNamespace(id=task_id, success_criteria=["Criterion"]),
            run=replication_run,
            scientific_assets={"evidence": []},
        )
    )

    assert context is not None
    assert context["source_run"]["snapshot_sealed"] is True
    assert context["source_run"]["result_digest"] == source_digest
    assert context["lineage_intact"] is True
