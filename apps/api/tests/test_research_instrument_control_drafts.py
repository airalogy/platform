import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.main import app
from app.routers.research_instrument_jobs import AiraInstrumentControlDraftRequest
from app.services.research_instrument_control_drafts import (
    AiraInstrumentControlOutput,
    generate_instrument_control_draft,
    instrument_control_draft_prompt,
    validate_instrument_control_output,
)


def command_catalog(command_id=None):
    return [
        {
            "id": str(command_id or uuid4()),
            "name": "Set temperature",
            "description": "Set an incubator target",
            "command_key": "incubator.set-temperature",
            "command_version": "1.0",
            "revision": 3,
            "risk": "medium",
            "input_schema": {
                "type": "object",
                "properties": {"temperature": {"type": "number"}},
                "required": ["temperature"],
                "additionalProperties": False,
            },
            "output_schema": {
                "type": "object",
                "properties": {"temperature": {"type": "number"}},
                "required": ["temperature"],
            },
            "device_confirmation_required": True,
            "safety_contract": {"required_interlocks": ["door_closed"]},
            "gateway": {"id": str(uuid4()), "name": "Gateway"},
            "resource": {"id": str(uuid4()), "name": "Incubator", "code": "INC-1"},
            "executor_binding": {"id": str(uuid4()), "revision": 2},
        }
    ]


def output_for(command_id, *, target="complete"):
    return AiraInstrumentControlOutput.model_validate(
        {
            "title": " Stabilize temperature ",
            "description": " Use the approved incubator. ",
            "entry_step_key": " SET ",
            "steps": [
                {
                    "key": " SET ",
                    "command_id": str(command_id),
                    "arguments": {"temperature": 37},
                    "transition": {
                        "condition": None,
                        "on_true": target,
                        "on_false": None,
                    },
                }
            ],
            "rationale": " Uses the exact approved command. ",
            "assumptions": [" Device is loaded ", ""],
            "warnings": ["Confirm the sample limit"],
        }
    )


def test_aira_control_output_is_normalized_and_constrained_to_catalog():
    command_id = uuid4()
    output = output_for(command_id)

    program = validate_instrument_control_output(
        output,
        mode="bounded_sequence",
        max_step_templates=4,
        max_steps=8,
        max_duration_seconds=900,
        commands=command_catalog(command_id),
    )

    assert output.title == "Stabilize temperature"
    assert output.entry_step_key == "set"
    assert output.assumptions == ["Device is loaded"]
    assert program["entry_step_key"] == "set"
    assert program["max_steps"] == 1
    assert program["steps"][0]["arguments"] == {"temperature": 37}


def test_aira_control_output_cannot_escape_catalog_or_input_schema():
    allowed_id = uuid4()
    with pytest.raises(ValueError, match="outside the authorized catalog"):
        validate_instrument_control_output(
            output_for(uuid4()),
            mode="bounded_sequence",
            max_step_templates=2,
            max_steps=2,
            max_duration_seconds=300,
            commands=command_catalog(allowed_id),
        )

    invalid = output_for(allowed_id)
    invalid.steps[0].arguments = {"temperature": "hot"}
    with pytest.raises(ValueError, match="Invalid Aira step set input"):
        validate_instrument_control_output(
            invalid,
            mode="bounded_sequence",
            max_step_templates=2,
            max_steps=2,
            max_duration_seconds=300,
            commands=command_catalog(allowed_id),
        )


def test_aira_control_output_cannot_add_a_sequence_cycle_or_exceed_template_limit():
    command_id = uuid4()
    output = output_for(command_id, target="set")
    with pytest.raises(ValueError, match="cannot contain a cycle"):
        validate_instrument_control_output(
            output,
            mode="bounded_sequence",
            max_step_templates=2,
            max_steps=2,
            max_duration_seconds=300,
            commands=command_catalog(command_id),
        )

    valid = output_for(command_id)
    with pytest.raises(ValueError, match="exceeds the selected template limit"):
        validate_instrument_control_output(
            valid,
            mode="bounded_sequence",
            max_step_templates=0,
            max_steps=2,
            max_duration_seconds=300,
            commands=command_catalog(command_id),
        )


def test_aira_control_request_keeps_user_selected_limits():
    with pytest.raises(ValidationError, match="cannot exceed maximum executions"):
        AiraInstrumentControlDraftRequest(
            instruction="Stabilize the chamber",
            mode="feedback_loop",
            equipment_booking_id=uuid4(),
            max_step_templates=8,
            max_steps=4,
            max_duration_seconds=600,
        )


def test_aira_control_prompt_and_generation_are_draft_only(monkeypatch):
    from app.services import research_instrument_control_drafts as drafts

    command_id = uuid4()
    generated = output_for(command_id).model_dump(mode="json")
    propose = AsyncMock(return_value=generated)
    monkeypatch.setattr(drafts, "aira_structured_proposal", propose)
    booking = {
        "id": str(uuid4()),
        "starts_at": "2026-09-05T00:00:00+00:00",
        "ends_at": "2026-09-05T01:00:00+00:00",
    }
    commands = command_catalog(command_id)

    output, program = asyncio.run(
        generate_instrument_control_draft(
            instruction="Keep the incubator at 37 C",
            mode="bounded_sequence",
            max_step_templates=4,
            max_steps=4,
            max_duration_seconds=600,
            booking=booking,
            commands=commands,
            model_name="test-model",
            usage_context=None,
        )
    )

    prompt = propose.await_args.args[0]
    assert "proposal only" in prompt
    assert "Never invent a command" in prompt
    assert "never retried automatically" in prompt
    assert "separate impact preview and explicit confirmation" in prompt
    assert output.title == "Stabilize temperature"
    assert program["max_steps"] == 1


def test_aira_control_draft_route_is_registered():
    paths = {route.path for route in app.routes}
    assert (
        "/research-tasks/{task_id}/instrument-control-sessions/draft-with-aira" in paths
    )


def test_aira_control_draft_fails_closed_when_ai_is_disabled(monkeypatch):
    from app.routers import research_instrument_jobs as routes

    monkeypatch.setattr(routes.config, "AI_ENABLED", False)
    params = AiraInstrumentControlDraftRequest(
        instruction="Stabilize the chamber",
        mode="bounded_sequence",
        equipment_booking_id=uuid4(),
        max_step_templates=2,
        max_steps=2,
        max_duration_seconds=300,
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            routes.draft_instrument_control_session_with_aira(
                uuid4(), params, object(), object()
            )
        )

    assert error.value.status_code == 409
    assert "deterministic editor" in error.value.detail


def test_aira_control_prompt_rejects_oversized_authorized_context():
    commands = command_catalog()
    commands[0]["description"] = "x" * 90_000
    with pytest.raises(ValueError, match="catalog is too large"):
        instrument_control_draft_prompt(
            instruction="Do it safely",
            mode="bounded_sequence",
            max_step_templates=2,
            max_steps=2,
            max_duration_seconds=300,
            booking={"id": str(uuid4())},
            commands=commands,
        )
