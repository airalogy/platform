"""Deterministic private Compute contracts, without a database or code execution."""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, localcontext
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.services.analysis_compute import instant, money
from app.services.analysis_compute_contracts import (
    AnalysisComputeCancel,
    AnalysisComputeDecision,
    AnalysisComputeDraft,
    AnalysisComputeRecipe,
)
from app.services.analysis_engine import canonical_digest
from app.services.research_compute_contracts import MAX_SOURCE_BYTES

SYNTHETIC_ID = UUID("00000000-0000-4000-8000-000000000001")


def recipe_payload():
    return {
        "environment_revision_id": str(SYNTHETIC_ID),
        "language": "python",
        "source_code": "# Synthetic contract only; never executed.\nprint('测量')\n",
        "parameters": {"scale": 1},
        "output_files": [
            {
                "mount_name": "summary.json",
                "asset_name": "Synthetic result",
                "media_type": "application/json",
                "max_bytes": 4096,
            }
        ],
    }


def draft_payload(**changes):
    return {
        "protocol_id": str(SYNTHETIC_ID),
        "approver_user_id": str(SYNTHETIC_ID),
        "recipe": recipe_payload(),
        **changes,
    }


@pytest.mark.parametrize(
    "change",
    [
        {"source_code": " \n\t"},
        {"source_code": None},
        {"source_code": 42},
        {"source_code": "x" * (MAX_SOURCE_BYTES + 1)},
        {"source_code": "测" * (MAX_SOURCE_BYTES // 3 + 1)},
        {"language": "shell"},
        {"language": "Python"},
        {"kind": "builtin"},
        {"environment_revision_id": "latest"},
        {"parameters": []},
        {"parameters": {"large": "x" * 100001}},
        {"network_policy": "unrestricted"},
        {"host_mounts": ["/"]},
        {"timeout_seconds": 0},
        {"shell": True},
    ],
)
def test_recipe_rejects_invalid_code_and_unreviewed_runtime_options(change):
    with pytest.raises(ValidationError):
        AnalysisComputeRecipe.model_validate({**recipe_payload(), **change})


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("location", ["parameters", "metadata", "data_schema"])
def test_recipe_rejects_nonfinite_json_in_every_persisted_dictionary(number, location):
    payload = recipe_payload()
    if location == "parameters":
        payload[location] = {"nested": [{"value": number}]}
    else:
        payload["output_files"][0][location] = {"nested": [{"value": number}]}
    with pytest.raises(ValidationError):
        AnalysisComputeRecipe.model_validate(payload)


@pytest.mark.parametrize(
    "output_change",
    [
        {"mount_name": "../private.json"},
        {"mount_name": "/tmp/private.json"},
        {"mount_name": "nested/private.json"},
        {"mount_name": "nested\\private.json"},
        {"mount_name": ".hidden"},
        {"mount_name": "a\x00.json"},
        {"asset_name": " \t"},
        {"max_bytes": 0},
        {"max_bytes": 2**31},
        {"media_type": "text/html; x=unsafe"},
        {"kind": "executable"},
        {"public": True},
    ],
)
def test_output_contract_rejects_unsafe_names_and_undeclared_options(output_change):
    payload = recipe_payload()
    payload["output_files"][0].update(output_change)
    with pytest.raises(ValidationError):
        AnalysisComputeRecipe.model_validate(payload)


def test_output_names_are_unique_after_normalization_and_count_is_bounded():
    payload = recipe_payload()
    payload["output_files"].append(
        {**payload["output_files"][0], "mount_name": " summary.json "}
    )
    with pytest.raises(ValidationError, match="unique"):
        AnalysisComputeRecipe.model_validate(payload)
    payload = recipe_payload()
    template = payload["output_files"][0]
    payload["output_files"] = [
        {**template, "mount_name": f"result-{i}.json"} for i in range(17)
    ]
    with pytest.raises(ValidationError):
        AnalysisComputeRecipe.model_validate(payload)


def test_normalized_contract_round_trips_without_altering_executable_source():
    payload = recipe_payload()
    payload["output_files"][0].update(
        {
            "mount_name": " summary.json ",
            "asset_name": "  测量结果  ",
            "description": "  Synthetic description  ",
            "media_type": " APPLICATION/JSON ",
        }
    )
    source = payload["source_code"]
    model = AnalysisComputeRecipe.model_validate(copy.deepcopy(payload))
    assert model.source_code == source
    output = model.output_files[0]
    assert output.mount_name == "summary.json"
    assert output.asset_name == "测量结果"
    assert output.description == "Synthetic description"
    assert output.media_type == "application/json"
    restored = AnalysisComputeRecipe.model_validate_json(model.model_dump_json())
    assert restored == model
    assert canonical_digest(restored.model_dump(mode="json")) == canonical_digest(
        model.model_dump(mode="json")
    )


@pytest.mark.parametrize(
    "options",
    [
        {"max_cost": "1"},
        {"budget_currency": "USD"},
        {"max_cost": "-0.001", "budget_currency": "USD"},
        {"max_cost": "NaN", "budget_currency": "USD"},
        {"max_cost": "Infinity", "budget_currency": "USD"},
        {"max_cost": "0.0000000000000000001", "budget_currency": "USD"},
        {"max_cost": "100000000000000000000", "budget_currency": "USD"},
        {"max_cost": "1", "budget_currency": "usd"},
        {"max_cost": "1", "budget_currency": "US"},
        {"max_cost": "1", "budget_currency": "USDD"},
        {"deadline_at": "2030-01-01T00:00:00"},
        {"deadline_at": datetime(2030, 1, 1)},
        {"approved": True},
        {"visibility": "public"},
    ],
)
def test_draft_rejects_unreviewed_governance_or_nonrepresentable_budget(options):
    with pytest.raises(ValidationError):
        AnalysisComputeDraft.model_validate(draft_payload(**options))


@pytest.mark.parametrize(
    "amount",
    ["0", "0.1", "1.234567890123456789", "99999999999999999999.999999999999999999"],
)
def test_budget_fits_exact_postgres_numeric_38_18_and_json_round_trip(amount):
    model = AnalysisComputeDraft.model_validate(
        draft_payload(max_cost=amount, budget_currency="USD")
    )
    restored = AnalysisComputeDraft.model_validate_json(model.model_dump_json())
    with localcontext() as context:
        context.prec = 60
        stored = model.max_cost.quantize(Decimal("1e-18"), rounding=ROUND_HALF_UP)
    assert stored == Decimal(amount) == restored.max_cost
    assert money(model.max_cost) == money(stored)


@pytest.mark.parametrize(
    "amount,expected",
    [
        (None, None),
        ("0.000000000000000000", "0"),
        ("0.100000000000000000", "0.1"),
        ("1.230000000000000000", "1.23"),
        ("0.0000000000000000004", "0"),
        ("0.0000000000000000005", "0.000000000000000001"),
        (
            "99999999999999999999.999999999999999999",
            "99999999999999999999.999999999999999999",
        ),
    ],
)
def test_money_seal_matches_numeric_storage_rounding_without_context_truncation(
    amount, expected
):
    value = Decimal(amount) if amount is not None else None
    with localcontext() as context:
        context.prec = 8
        assert money(value) == expected


def test_repeating_estimated_cost_matches_postgres_numeric_storage_seal():
    with localcontext() as context:
        context.prec = 60
        estimate = Decimal("0.1") * Decimal(17) / Decimal(3600)
        stored = estimate.quantize(Decimal("1e-18"), rounding=ROUND_HALF_UP)
    assert money(estimate) == money(stored) == "0.000472222222222222"


def test_governance_normalization_preserves_instant_and_strips_question():
    deadline = datetime(2030, 1, 1, 8, 0, tzinfo=timezone(timedelta(hours=8)))
    model = AnalysisComputeDraft.model_validate(
        draft_payload(
            question="  Compare synthetic groups\n",
            deadline_at=deadline,
        )
    )
    assert model.question == "Compare synthetic groups"
    assert instant(model.deadline_at) == "2030-01-01T00:00:00+00:00"
    assert instant(model.deadline_at) == instant(datetime(2030, 1, 1, tzinfo=UTC))
    assert instant(None) is None
    assert model.selection.mode == "latest"


@pytest.mark.parametrize("model", [AnalysisComputeCancel, AnalysisComputeDecision])
@pytest.mark.parametrize(
    "change",
    [
        {"expected_revision": True},
        {"expected_revision": "1"},
        {"expected_revision": 1.0},
        {"expected_revision": 0},
        {"contract_digest": "A" * 64},
        {"contract_digest": "a" * 63},
        {"contract_digest": "a" * 65},
        {"reason": " \n\t"},
        {"reason": "x" * 4001},
        {"force": True},
    ],
)
def test_decisions_and_cancellation_require_exact_revision_digest_and_reason(
    model, change
):
    payload = {
        "expected_revision": 1,
        "contract_digest": "a" * 64,
        "reason": "Reviewed",
    }
    if model is AnalysisComputeDecision:
        payload["decision"] = "approved"
    with pytest.raises(ValidationError):
        model.model_validate({**payload, **change})


def test_decision_is_explicit_and_reasons_are_normalized():
    payload = {
        "expected_revision": 1,
        "contract_digest": "a" * 64,
        "reason": "  Reviewed\n",
    }
    assert AnalysisComputeCancel.model_validate(payload).reason == "Reviewed"
    decision = AnalysisComputeDecision.model_validate(
        {**payload, "decision": "approved"}
    )
    assert decision.reason == "Reviewed"
    for invalid in ("pending", "cancelled", True, "approve"):
        with pytest.raises(ValidationError):
            AnalysisComputeDecision.model_validate({**payload, "decision": invalid})
