"""Project source envelopes, explicit interpretation and result comparison."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.services import project_analyses as service
from app.services.analysis_engine import canonical_digest
from app.services.project_analysis_engine import compute_project_analysis
from tests.test_project_analysis_engine import project_fixture


def selection(snapshot):
    return service.ProjectAnalysisSelection.model_validate(
        {
            "inputs": [
                {
                    "slot_id": item["slot_id"],
                    "protocol_id": item["snapshot"]["protocol_id"],
                }
                for item in snapshot["inputs"]
            ]
        }
    )


def interpretation(**changes):
    value = {
        "judgement": "inconclusive",
        "summary": "Two independent measurements need more evidence.",
        "findings": [
            {
                "slot_id": "treatment",
                "field": "dose",
                "relation": "supports",
                "note": "Dose varied.",
            },
            {
                "slot_id": "assay",
                "field": "response",
                "relation": "inconclusive",
                "note": "Responses varied.",
            },
        ],
        "limitations": ["Synthetic observations."],
        "unanswered_questions": ["Is the difference causal?"],
    }
    return service.ProjectInterpretationContent.model_validate({**value, **changes})


def result_run(recipe, snapshot):
    result = compute_project_analysis(recipe, snapshot)
    return SimpleNamespace(
        id=uuid4(),
        project_id=UUID(snapshot["project_id"]),
        source_snapshot=deepcopy(snapshot),
        recipe_digest=canonical_digest(recipe.model_dump(mode="json")),
        result=result,
        result_digest=canonical_digest(result),
    )


def test_project_selection_canonical_order_preserves_exact_record_mode():
    _, snapshot = project_fixture()
    value = selection(snapshot)
    value.inputs[0].selection = service.AnalysisSelection(
        mode="selected", records=[{"id": uuid4(), "version": 2}]
    )
    payload = service.project_selection_payload(value)
    assert payload["schema"] == service.PROJECT_SELECTION_SCHEMA
    assert [item["slot_id"] for item in payload["inputs"]] == ["assay", "treatment"]
    chosen = next(item for item in payload["inputs"] if item["slot_id"] == "treatment")
    assert chosen["selection"]["mode"] == "selected"
    assert chosen["selection"]["records"][0]["version"] == 2


@pytest.mark.parametrize(
    "mutation", ["duplicate_protocol", "duplicate_slot", "one_slot", "extra_field"]
)
def test_project_selection_rejects_ambiguous_inputs(mutation):
    _, snapshot = project_fixture()
    payload = selection(snapshot).model_dump(mode="json", by_alias=True)
    if mutation == "duplicate_protocol":
        payload["inputs"][1]["protocol_id"] = payload["inputs"][0]["protocol_id"]
    elif mutation == "duplicate_slot":
        payload["inputs"][1]["slot_id"] = payload["inputs"][0]["slot_id"]
    elif mutation == "one_slot":
        payload["inputs"].pop()
    else:
        payload["inputs"][0]["whole_project"] = True
    with pytest.raises(ValidationError):
        service.ProjectAnalysisSelection.model_validate(payload)


def test_method_contract_excludes_records_but_pins_exact_schema():
    _, snapshot = project_fixture()
    original = service.project_input_contracts(snapshot)
    next_snapshot = deepcopy(snapshot)
    next_snapshot["inputs"][0]["snapshot"]["records"].pop()
    assert service.project_input_contracts(next_snapshot) == original
    next_snapshot["inputs"][0]["snapshot"]["schemas"][0]["json_schema"][
        "description"
    ] = "Explicit new Schema"
    assert service.project_input_contracts(next_snapshot) != original
    assert "record_id" not in str(original)


def test_project_source_contract_rejects_multiple_revisions_of_one_record():
    _, snapshot = project_fixture()
    record = deepcopy(snapshot["inputs"][0]["snapshot"]["records"][0])
    record["record_version"] = 2
    snapshot["inputs"][0]["snapshot"]["records"].append(record)
    with pytest.raises(ValidationError, match="one revision of each Record"):
        service.project_input_contracts(snapshot)


def test_capture_checks_same_project_and_aggregate_count(monkeypatch):
    _, snapshot = project_fixture()
    project = SimpleNamespace(id=UUID(snapshot["project_id"]))
    monkeypatch.setattr(
        service, "project_analysis_scope", AsyncMock(return_value=project)
    )
    by_protocol = {
        UUID(item["snapshot"]["protocol_id"]): item["snapshot"]
        for item in snapshot["inputs"]
    }

    async def capture(db, *, protocol_id, selection, user):
        return by_protocol[protocol_id], SimpleNamespace(project_id=project.id), project

    mock = AsyncMock(side_effect=capture)
    monkeypatch.setattr(service, "capture_sources", mock)
    captured, _ = asyncio.run(
        service.capture_project_sources(
            None, project_id=project.id, selection=selection(snapshot), user=None
        )
    )
    assert len(captured["inputs"]) == 2
    monkeypatch.setattr(service, "MAX_RECORDS", 5)
    with pytest.raises(service.AnalysisError, match="at most 5"):
        asyncio.run(
            service.capture_project_sources(
                None, project_id=project.id, selection=selection(snapshot), user=None
            )
        )
    mock.side_effect = None
    mock.return_value = (
        snapshot["inputs"][0]["snapshot"],
        SimpleNamespace(project_id=uuid4()),
        project,
    )
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(
            service.capture_project_sources(
                None, project_id=project.id, selection=selection(snapshot), user=None
            )
        )
    assert rejected.value.status_code == 422


def test_interpretation_resolves_actual_statistics_without_mutating_result():
    recipe, snapshot = project_fixture("evidence_synthesis")
    run = result_run(recipe, snapshot)
    original = deepcopy(run.result)
    evidence = service.interpretation_evidence(run.result, interpretation())
    assert evidence[0]["groups"][0]["statistics"]["mean"] == 4
    assert evidence[1]["groups"][0]["statistics"]["mean"] == pytest.approx(70 / 3)
    assert run.result == original
    evidence[0]["groups"][0]["statistics"]["mean"] = -1
    assert run.result == original


@pytest.mark.parametrize("field", ["sample_id", "nonexistent"])
def test_interpretation_cannot_cite_noncomputed_fields(field):
    recipe, snapshot = project_fixture("evidence_synthesis")
    content = interpretation()
    content.findings[0].field = field
    with pytest.raises(HTTPException) as rejected:
        service.interpretation_evidence(
            compute_project_analysis(recipe, snapshot), content
        )
    assert rejected.value.status_code == 422


@pytest.mark.parametrize(
    "mutation", ["one_source", "duplicate", "blank", "huge", "invented_stats"]
)
def test_interpretation_content_is_bounded_and_cross_source(mutation):
    content = interpretation().model_dump(mode="json")
    if mutation == "one_source":
        content["findings"][1]["slot_id"] = "treatment"
    elif mutation == "duplicate":
        content["findings"].append(deepcopy(content["findings"][0]))
    elif mutation == "blank":
        content["summary"] = "   "
    elif mutation == "huge":
        content["limitations"] = ["x" * 4001]
    else:
        content["findings"][0]["statistics"] = {"mean": 9999}
    with pytest.raises(ValidationError):
        service.ProjectInterpretationContent.model_validate(content)


def test_result_comparison_keeps_snapshots_and_reports_separate():
    recipe, snapshot = project_fixture("evidence_synthesis")
    before = result_run(recipe, snapshot)
    after = result_run(recipe, snapshot)
    record = after.source_snapshot["inputs"][0]["snapshot"]["records"][0]
    record["record_version"] = 2
    record["record_hash"] = "f" * 64
    compared = service.project_result_comparison(after, before)
    assert compared["inputs"][0]["changed"][0]["before"]["record_version"] == 1
    assert compared["inputs"][0]["changed"][0]["after"]["record_version"] == 2
    assert not compared["local_results"][0]["changed"]
    assert after.source_snapshot != before.source_snapshot
    after.project_id = uuid4()
    with pytest.raises(HTTPException) as rejected:
        service.project_result_comparison(after, before)
    assert rejected.value.status_code == 409


def test_interpretation_digest_binds_author_result_and_evidence():
    row = SimpleNamespace(
        analysis_run_id=uuid4(),
        revision=1,
        result_digest="a" * 64,
        content=interpretation().model_dump(mode="json"),
        resolved_evidence=[{"mean": 4}],
        created_by_user_id=uuid4(),
    )
    original = service.interpretation_digest(row)
    row.resolved_evidence[0]["mean"] = 6
    assert service.interpretation_digest(row) != original
