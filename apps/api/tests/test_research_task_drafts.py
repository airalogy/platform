import asyncio
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.main import app
from app.routers.research_tasks import AiraResearchTaskDraftRequest
from app.services.research_task_drafts import (
    AiraResearchTaskDraft,
    generate_research_task_draft,
    task_draft_prompt,
    validate_task_draft_selection,
)


def _catalog():
    return {
        "protocols": [{"id": str(uuid4()), "name": "Validated assay"}],
        "tools": [{"key": "knowledge.search", "name": "Knowledge search"}],
        "knowledge": [{"id": str(uuid4()), "title": "Reviewed finding"}],
        "resources": [{"id": str(uuid4()), "name": "Plate reader"}],
        "services": [{"id": str(uuid4()), "name": "Sequencing service"}],
        "compute": [{"id": str(uuid4()), "name": "Analysis sandbox"}],
    }


def _draft(catalog):
    return AiraResearchTaskDraft(
        title="  Assess candidate response  ",
        goal="  Determine whether the candidate changes the bounded endpoint.  ",
        success_criteria=[" Predefined effect estimate is reported ", ""],
        stop_conditions=[" Safety boundary is reached "],
        protocol_ids=[catalog["protocols"][0]["id"]],
        tool_keys=[catalog["tools"][0]["key"]],
        knowledge_ids=[catalog["knowledge"][0]["id"]],
        resource_type_ids=[catalog["resources"][0]["id"]],
        service_offering_ids=[catalog["services"][0]["id"]],
        compute_environment_ids=[catalog["compute"][0]["id"]],
        rationale="  The selected capabilities cover evidence collection.  ",
        assumptions=[" Samples are available ", ""],
        warnings=[" Confirm the safety threshold "],
    )


def test_aira_task_draft_normalizes_and_accepts_only_authorized_capabilities():
    catalog = _catalog()
    draft = _draft(catalog)

    validate_task_draft_selection(draft, catalog=catalog)

    assert draft.title == "Assess candidate response"
    assert draft.success_criteria == ["Predefined effect estimate is reported"]
    assert draft.assumptions == ["Samples are available"]


def test_aira_task_draft_rejects_unknown_or_duplicate_capabilities():
    catalog = _catalog()
    draft = _draft(catalog)
    draft.tool_keys = ["untrusted.external.tool"]

    with pytest.raises(ValueError, match="outside the authorized Research catalog"):
        validate_task_draft_selection(draft, catalog=catalog)

    with pytest.raises(ValidationError, match="contains duplicates"):
        AiraResearchTaskDraft(
            title="Duplicate selection",
            goal="Reject duplicate capabilities",
            success_criteria=["Duplicate is rejected"],
            tool_keys=["knowledge.search", "knowledge.search"],
            rationale="The transport must fail closed.",
        )


def test_task_draft_prompt_preserves_protocol_and_execution_boundaries():
    catalog = _catalog()
    prompt = task_draft_prompt(
        research_question="What conditions improve the measured response?",
        additional_constraints="Do not exceed the safety limit.",
        autonomy_level="bounded_autopilot",
        catalog=catalog,
    )

    assert "Protocol means a versioned scientific method" in prompt
    assert "Select only exact IDs or keys" in prompt
    assert "performs no write and starts no work" in prompt
    assert "do not reinterpret or escalate it" in prompt
    assert "What conditions improve the measured response?" in prompt
    assert catalog["tools"][0]["key"] in prompt


def test_generate_task_draft_uses_strict_structured_transport(monkeypatch):
    catalog = _catalog()

    async def fake_proposal(prompt, model_name, *, usage_context):
        assert "editable Research Task brief" in prompt
        assert model_name == "qwen3.5-flash"
        assert usage_context is None
        return {
            "title": "Assess candidate response",
            "goal": "Determine whether the candidate changes the bounded endpoint.",
            "success_criteria": ["Predefined effect estimate is reported"],
            "stop_conditions": ["Safety boundary is reached"],
            "protocol_ids": [catalog["protocols"][0]["id"]],
            "tool_keys": [catalog["tools"][0]["key"]],
            "knowledge_ids": [],
            "resource_type_ids": [],
            "service_offering_ids": [],
            "compute_environment_ids": [],
            "rationale": "The method and search tool cover the bounded objective.",
            "assumptions": ["Samples are available"],
            "warnings": [],
        }

    monkeypatch.setattr(
        "app.services.research_task_drafts.aira_structured_proposal",
        fake_proposal,
    )

    output = asyncio.run(
        generate_research_task_draft(
            research_question="Does the candidate change the response?",
            additional_constraints="",
            autonomy_level="assisted",
            catalog=catalog,
            model_name="qwen3.5-flash",
            usage_context=None,
        )
    )

    assert [str(item) for item in output.protocol_ids] == [
        catalog["protocols"][0]["id"]
    ]
    assert output.tool_keys == ["knowledge.search"]


def test_aira_task_draft_request_rejects_blank_question():
    with pytest.raises(ValidationError, match="cannot be blank"):
        AiraResearchTaskDraftRequest(
            project_id=uuid4(),
            research_question="   ",
        )


def test_openapi_exposes_aira_task_draft_contract():
    assert "/research-tasks/draft-with-aira" in app.openapi()["paths"]
