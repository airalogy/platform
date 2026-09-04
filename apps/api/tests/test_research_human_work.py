from datetime import date
from uuid import uuid4

import pytest
from app.models.research_asset import EvidenceKind
from app.services.research_capabilities import human_work_capability
from app.services.research_executor_bindings import derived_executor_binding
from app.services.research_human_work import (
    HUMAN_WORK_CAPABILITY_KEY,
    HUMAN_WORK_CAPABILITY_VERSION,
    HumanWorkField,
    HumanWorkRequest,
    human_work_request_from_contract,
    validate_human_work_submission,
)
from pydantic import ValidationError


def _request(**overrides) -> HumanWorkRequest:
    values = {
        "title": "Inspect collected samples",
        "instructions": "Record sample condition and attach the measurement table.",
        "completion_criteria": "Every sample has an observed condition.",
        "evidence_kind": EvidenceKind.OBSERVATION,
        "fields": [
            {
                "key": "sample_condition",
                "label": "Sample condition",
                "value_type": "choice",
                "options": ["intact", "damaged"],
            },
            {
                "key": "temperature",
                "label": "Temperature",
                "value_type": "number",
                "unit": "Cel",
            },
            {
                "key": "observed_on",
                "label": "Observed on",
                "value_type": "date",
            },
            {
                "key": "sealed",
                "label": "Container sealed",
                "value_type": "boolean",
            },
        ],
        "data_asset_min_count": 1,
        "data_asset_max_count": 2,
    }
    values.update(overrides)
    return HumanWorkRequest.model_validate(values)


def test_human_work_contract_is_bounded_renderer_safe_and_round_trips():
    request = _request()
    contract = request.submission_contract()
    restored = human_work_request_from_contract(
        title=request.title,
        instructions=request.instructions,
        contract=contract,
    )

    assert contract["schema"] == "airalogy.human-work-submission.v1"
    assert restored == request
    assert date.fromisoformat("2030-01-03").isoformat() == "2030-01-03"


def test_human_work_field_contract_rejects_ambiguous_or_unsafe_shapes():
    with pytest.raises(ValidationError, match="title and instructions"):
        _request(title="   ")
    with pytest.raises(ValidationError, match="field key is invalid"):
        HumanWorkField(
            key="Sample Name",
            label="Sample",
            value_type="text",
        )
    with pytest.raises(ValidationError, match="at least two"):
        HumanWorkField(
            key="condition",
            label="Condition",
            value_type="choice",
            options=["intact"],
        )
    with pytest.raises(ValidationError, match="Only number fields"):
        HumanWorkField(
            key="condition",
            label="Condition",
            value_type="text",
            unit="Cel",
        )
    with pytest.raises(ValidationError, match="keys must be unique"):
        _request(fields=[
            {"key": "condition", "label": "One", "value_type": "text"},
            {"key": "condition", "label": "Two", "value_type": "text"},
        ])
    with pytest.raises(ValidationError, match="minimum exceeds"):
        _request(data_asset_min_count=2, data_asset_max_count=1)


def test_human_work_submission_requires_exact_typed_values_and_asset_count():
    request = _request()
    accepted = validate_human_work_submission(
        request,
        values={
            "sample_condition": " intact ",
            "temperature": 4.5,
            "observed_on": "2030-01-03",
            "sealed": True,
        },
        data_asset_count=1,
    )
    assert accepted["sample_condition"] == "intact"

    with pytest.raises(ValueError, match="unknown field"):
        validate_human_work_submission(
            request,
            values={**accepted, "untrusted": "value"},
            data_asset_count=1,
        )
    with pytest.raises(ValueError, match="must be a number"):
        validate_human_work_submission(
            request,
            values={**accepted, "temperature": True},
            data_asset_count=1,
        )
    with pytest.raises(ValueError, match="must be a number"):
        validate_human_work_submission(
            request,
            values={**accepted, "temperature": float("nan")},
            data_asset_count=1,
        )
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        validate_human_work_submission(
            request,
            values={**accepted, "observed_on": "03/01/2030"},
            data_asset_count=1,
        )
    with pytest.raises(ValueError, match="DataAsset count"):
        validate_human_work_submission(
            request,
            values=accepted,
            data_asset_count=0,
        )


def test_generic_human_work_is_a_versioned_capability_with_a_pinned_executor():
    descriptor = human_work_capability()
    binding = derived_executor_binding(
        capability=descriptor.payload(),
        owner_user_id=uuid4(),
    )

    assert descriptor.key == HUMAN_WORK_CAPABILITY_KEY
    assert descriptor.version == HUMAN_WORK_CAPABILITY_VERSION
    assert descriptor.kind == "human"
    assert descriptor.input_schema["additionalProperties"] is False
    assert binding["mode"] == "structured_submission"
    assert binding["approval_policy"] == "always_ask"
