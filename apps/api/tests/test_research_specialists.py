import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.config import config
from app.services import research_specialists
from app.services.research_specialists import (
    MAX_SPECIALIST_ACTIONS_PER_RUN,
    SPECIALIST_RESULT_SCHEMA,
    SpecialistAgentRequest,
    build_specialist_context_snapshot,
    ensure_specialist_action_capacity,
    run_specialist_agent,
    specialist_agent_prompt,
    validate_specialist_context_snapshot,
)
from app.services.research_tools import execute_research_tool, research_tool_catalog


def task_and_run():
    task_id = uuid4()
    run_id = uuid4()
    task = SimpleNamespace(
        id=task_id,
        revision=3,
        title="Discriminate two RNA mechanisms",
        goal="Determine whether mechanism A or B explains the observation",
        success_criteria=["One explanation is discriminated by evidence"],
        stop_conditions=["The available evidence cannot distinguish them"],
        autonomy_level="assisted",
    )
    run = SimpleNamespace(
        id=run_id,
        plan_version=7,
        environment_snapshot={
            "knowledge": [
                {
                    "id": str(uuid4()),
                    "revision": 2,
                    "title": "Reviewed RNA result",
                    "body": "Mechanism A predicts increased binding.",
                    "kind": "finding",
                    "tags": ["rna"],
                    "state": "reviewed",
                    "visibility": "lab",
                },
                {
                    "id": str(uuid4()),
                    "revision": 1,
                    "title": "Restricted note",
                    "body": "Must never enter the model context.",
                    "kind": "note",
                    "tags": [],
                    "state": "reviewed",
                    "visibility": "restricted",
                },
                {
                    "id": str(uuid4()),
                    "revision": 1,
                    "title": "Unreviewed note",
                    "body": "Also excluded.",
                    "kind": "note",
                    "tags": [],
                    "state": "draft",
                    "visibility": "lab",
                },
            ]
        },
        aira_state={
            "steps": [
                {
                    "step": "add_research_strategy",
                    "data": {"hypothesis": "Compare A and B"},
                }
            ],
            "tool_results": [
                {
                    "action_id": str(uuid4()),
                    "tool_key": "knowledge.search",
                    "result": {"items": [{"title": "Prior result"}]},
                }
            ],
        },
    )
    return task, run


def test_specialist_request_is_strict_and_normalized():
    request = SpecialistAgentRequest(
        role="research_critic",
        question="  Which alternative explanation remains?  ",
    )
    assert request.question == "Which alternative explanation remains?"
    with pytest.raises(ValidationError, match="question cannot be blank"):
        SpecialistAgentRequest(role="data_analyst", question="   ")
    with pytest.raises(ValidationError, match="extra_forbidden"):
        SpecialistAgentRequest(
            role="data_analyst",
            question="Assess the result",
            execute=True,
        )


def test_specialist_context_is_stable_bounded_and_excludes_unsafe_knowledge():
    task, run = task_and_run()
    first = build_specialist_context_snapshot(
        task=task,
        run=run,
        model_name="qwen3.5-flash",
    )
    second = build_specialist_context_snapshot(
        task=task,
        run=run,
        model_name="qwen3.5-flash",
    )

    assert first == second
    assert first["digest"] == second["digest"]
    assert len(first["digest"]) == 64
    assert "Reviewed RNA result" in str(first["sources"])
    assert "Restricted note" not in str(first["sources"])
    assert "Unreviewed note" not in str(first["sources"])
    validate_specialist_context_snapshot(first, task=task, run=run)

    first["sources"][0]["content"] = "tampered"
    with pytest.raises(ValueError, match="digest is invalid"):
        validate_specialist_context_snapshot(first)


def test_specialist_prompt_sets_advisory_and_source_boundaries():
    task, run = task_and_run()
    context = build_specialist_context_snapshot(
        task=task,
        run=run,
        model_name="qwen3.5-flash",
    )
    request = SpecialistAgentRequest(
        role="experimental_designer",
        question="What experiment would discriminate the hypotheses?",
    )

    prompt = specialist_agent_prompt(request, context)

    assert "no tools, web access, write authority" in prompt
    assert "Do not invent citations" in prompt
    assert "Platform decides whether any Action" in prompt
    assert context["digest"] in prompt


def test_specialist_agent_returns_typed_advice_with_pinned_provenance(monkeypatch):
    task, run = task_and_run()
    context = build_specialist_context_snapshot(
        task=task,
        run=run,
        model_name="qwen3.5-flash",
    )
    source_ref = context["sources"][0]["ref"]
    proposal = AsyncMock(
        return_value={
            "summary": "The current evidence does not discriminate A from B.",
            "findings": [
                {
                    "statement": "Both mechanisms remain compatible.",
                    "source_refs": [source_ref],
                    "confidence": "medium",
                    "limitation": "No direct perturbation result is available.",
                }
            ],
            "recommendations": [
                {
                    "title": "Run a discriminating perturbation",
                    "rationale": "A controlled perturbation tests the divergent prediction.",
                    "suggested_next_action": "protocol",
                    "prerequisites": ["Confirm the control condition"],
                    "basis_refs": [source_ref],
                }
            ],
            "uncertainties": ["Effect size is unknown"],
            "risks": ["Confounding may remain"],
            "next_questions": ["Which control is feasible?"],
        }
    )
    monkeypatch.setattr(research_specialists, "aira_structured_proposal", proposal)

    result = asyncio.run(
        run_specialist_agent(
            arguments={
                "role": "research_critic",
                "question": "What evidence is missing?",
            },
            context_snapshot=context,
            model_name="qwen3.5-flash",
        )
    )

    assert result["schema"] == SPECIALIST_RESULT_SCHEMA
    assert result["role"] == "research_critic"
    assert result["context_digest"] == context["digest"]
    assert result["advisory_boundary"].startswith("advice_only")
    proposal.assert_awaited_once()


def test_specialist_agent_rejects_invented_source_references(monkeypatch):
    task, run = task_and_run()
    context = build_specialist_context_snapshot(
        task=task,
        run=run,
        model_name="qwen3.5-flash",
    )
    monkeypatch.setattr(
        research_specialists,
        "aira_structured_proposal",
        AsyncMock(
            return_value={
                "summary": "Unsupported claim",
                "findings": [
                    {
                        "statement": "Invented",
                        "source_refs": ["paper:invented"],
                        "confidence": "high",
                        "limitation": "",
                    }
                ],
                "recommendations": [],
                "uncertainties": [],
                "risks": [],
                "next_questions": [],
            }
        ),
    )

    with pytest.raises(ValueError, match="outside the pinned context"):
        asyncio.run(
            run_specialist_agent(
                arguments={
                    "role": "literature_analyst",
                    "question": "Summarize the evidence",
                },
                context_snapshot=context,
                model_name="qwen3.5-flash",
            )
        )


def test_specialist_tool_dispatch_requires_and_validates_the_pinned_context(
    monkeypatch,
):
    task, run = task_and_run()
    context = build_specialist_context_snapshot(
        task=task,
        run=run,
        model_name="qwen3.5-flash",
    )
    definition = replace(
        research_tool_catalog()["aira.specialist"],
        available=True,
        unavailable_reason="",
    )
    result = {
        "schema": SPECIALIST_RESULT_SCHEMA,
        "role": "data_analyst",
        "question": "Which analysis is needed?",
        "deliverable": "",
        "summary": "A sensitivity analysis is needed.",
        "findings": [],
        "recommendations": [],
        "uncertainties": [],
        "risks": [],
        "next_questions": [],
        "model": "qwen3.5-flash",
        "context_digest": context["digest"],
        "advisory_boundary": "advice_only_no_execution_approval_or_asset_write",
    }
    specialist = AsyncMock(return_value=result)
    monkeypatch.setattr(research_specialists, "run_specialist_agent", specialist)

    output = asyncio.run(
        execute_research_tool(
            AsyncMock(),
            task=task,
            definition=definition,
            arguments={
                "role": "data_analyst",
                "question": "Which analysis is needed?",
            },
            context_snapshot=context,
            model_name="qwen3.5-flash",
        )
    )
    assert output == result
    specialist.assert_awaited_once()

    with pytest.raises(ValueError, match="requires a pinned context"):
        asyncio.run(
            execute_research_tool(
                AsyncMock(),
                task=task,
                definition=definition,
                arguments={
                    "role": "data_analyst",
                    "question": "Which analysis is needed?",
                },
            )
        )


def test_specialist_tool_is_ai_gated_and_never_read_only():
    definition = research_tool_catalog()["aira.specialist"]

    assert definition.version == "1"
    assert definition.risk == "model_advisory"
    assert definition.executor_type == "platform_tool"
    assert definition.available is config.effective_ai_enabled
    assert set(definition.input_schema["properties"]["role"]["enum"]) == {
        "literature_analyst",
        "experimental_designer",
        "data_analyst",
        "research_critic",
    }


def test_specialist_panel_has_a_hard_per_run_limit():
    db_session = SimpleNamespace(
        scalar=AsyncMock(return_value=MAX_SPECIALIST_ACTIONS_PER_RUN)
    )
    with pytest.raises(ValueError, match="at most 4"):
        asyncio.run(ensure_specialist_action_capacity(db_session, run_id=uuid4()))
