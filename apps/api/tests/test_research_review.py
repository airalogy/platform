import asyncio
from importlib import import_module
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.main import app
from app.models.research import ResearchReviewRecommendation
from app.services.research_review import (
    ResearchReviewOutput,
    generate_research_review,
    research_review_prompt,
    validate_review_evidence,
)
from app.services.research_runtime import canonical_digest


def test_review_recommendations_are_immutable_context_specific_assets():
    ddl = str(
        CreateTable(ResearchReviewRecommendation.__table__).compile(
            dialect=postgresql.dialect()
        )
    )

    assert "context_digest" in ddl
    assert "recommended_task_outcome" in ddl
    assert "supporting_evidence_ids" in ddl
    assert "ck_research_review_recommendation" in ddl
    assert "ck_research_review_task_outcome" in ddl
    assert "ck_research_review_scientific_outcome" in ddl
    assert "uq_research_review_context_model" in ddl

    migration = import_module(
        "migrations.versions.0023_research_review_recommendations"
    )
    assert migration.down_revision == "0022_protocol_improvement_ai_provenance"
    assert migration.TABLE_NAMES == ("research_review_recommendations",)


def test_review_output_separates_support_contradiction_and_uncertainty():
    output = ResearchReviewOutput(
        recommendation="collect_more_evidence",
        recommended_task_outcome="inconclusive",
        recommended_scientific_outcome="inconclusive",
        summary="The stated effect needs an independent replicate.",
        supporting_evidence_ids=["evidence-1"],
        contradicting_evidence_ids=["evidence-2"],
        uncertainties=["Small sample size"],
        missing_checks=["Independent replicate"],
        risk_flags=["Potential batch effect"],
    )

    validate_review_evidence(
        output, available_evidence_ids={"evidence-1", "evidence-2"}
    )
    with pytest.raises(ValueError, match="outside the review context"):
        validate_review_evidence(output, available_evidence_ids={"evidence-1"})
    with pytest.raises(ValidationError, match="both support and contradict"):
        ResearchReviewOutput(
            recommendation="revise",
            recommended_task_outcome="inconclusive",
            recommended_scientific_outcome="inconclusive",
            summary="Conflicting classification",
            supporting_evidence_ids=["same"],
            contradicting_evidence_ids=["same"],
        )


def test_review_prompt_is_explicitly_advisory_and_treats_context_as_data():
    evidence_id = uuid4()
    prompt = research_review_prompt(
        {
            "task": {"goal": "Assess reproducibility"},
            "available_evidence": [{"id": evidence_id}],
        }
    )

    assert "independent scientific Reviewer Agent" in prompt
    assert "output is advisory" in prompt
    assert "untrusted scientific data" in prompt
    assert "Never claim approval" in prompt
    assert str(evidence_id) in prompt


def test_reviewer_agent_uses_strict_structured_transport(monkeypatch):
    async def fake_proposal(prompt, model_name, *, usage_context):
        assert "Reviewer Agent" in prompt
        assert model_name == "qwen3-max"
        return {
            "recommendation": "accept",
            "recommended_task_outcome": "goal_met",
            "recommended_scientific_outcome": "supports_hypothesis",
            "summary": "The validated Evidence meets the stated criteria.",
            "supporting_evidence_ids": ["evidence-1"],
            "contradicting_evidence_ids": [],
            "uncertainties": ["External replication remains desirable"],
            "missing_checks": [],
            "risk_flags": [],
        }

    monkeypatch.setattr(
        "app.services.research_review.aira_structured_proposal", fake_proposal
    )

    output = asyncio.run(
        generate_research_review(
            context={"available_evidence": [{"id": "evidence-1"}]},
            model_name="qwen3-max",
            usage_context=None,
        )
    )

    assert output.recommendation == "accept"
    assert output.recommended_task_outcome.value == "goal_met"


def test_reviewer_agent_must_return_a_valid_replication_assessment():
    source_run_id = str(uuid4())
    replication_run_id = str(uuid4())
    source_evidence_id = str(uuid4())
    replication_evidence_id = str(uuid4())
    context = {
        "schema": "airalogy.reproduction-context.v1",
        "success_criteria": ["The result direction matches"],
        "lineage_intact": True,
        "environment_equivalent": True,
        "source_evidence": [{"id": source_evidence_id}],
        "replication_evidence": [{"id": replication_evidence_id}],
        "source_run": {"id": source_run_id},
        "replication_run": {"id": replication_run_id},
    }
    output = ResearchReviewOutput(
        recommendation="accept",
        recommended_task_outcome="goal_met",
        recommended_scientific_outcome="supports_hypothesis",
        summary="The independent result reproduced.",
        reproduction_assessment={
            "outcome": "reproduced",
            "summary": "The predefined criterion reproduced.",
            "criteria_results": [
                {
                    "criterion": "The result direction matches",
                    "status": "reproduced",
                    "rationale": "Both validated measurements agree.",
                }
            ],
            "source_evidence_ids": [source_evidence_id],
            "replication_evidence_ids": [replication_evidence_id],
            "deviations": [],
            "limitations": [],
        },
    )

    validate_review_evidence(
        output,
        available_evidence_ids={source_evidence_id, replication_evidence_id},
        context={"reproduction_context": context},
    )
    with pytest.raises(ValueError, match="omitted"):
        validate_review_evidence(
            output.model_copy(update={"reproduction_assessment": None}),
            available_evidence_ids={source_evidence_id, replication_evidence_id},
            context={"reproduction_context": context},
        )
    with pytest.raises(ValueError, match="outside a replication Run"):
        validate_review_evidence(
            output,
            available_evidence_ids={source_evidence_id, replication_evidence_id},
            context={"context_digest": canonical_digest(context)},
        )


def test_review_recommendation_endpoint_is_publicly_typed():
    paths = app.openapi()["paths"]

    assert "/research-tasks/{task_id}/review-recommendations" in paths
