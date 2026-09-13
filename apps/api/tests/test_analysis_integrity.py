"""Saved-method and snapshot integrity using real deterministic analysis results."""

from __future__ import annotations

import asyncio
import copy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services import record_analyses
from app.services.analysis_engine import (
    AnalysisRecipe,
    canonical_digest,
    compute_analysis,
)
from app.services.record_analyses import (
    authorize_snapshot,
    method_revision_digest,
    preview_identity_digest,
    verify_revision_integrity,
    verify_run_integrity,
)


def real_run():
    owner_id, protocol_id = uuid4(), uuid4()
    recipe = AnalysisRecipe(numeric_fields=["measurement"])
    fields = [{"key": "measurement", "type": "number", "unit": "mg"}]
    rows = [
        {
            "record_id": str(uuid4()),
            "record_version": 1,
            "protocol_version": "1.0.0",
            "user_id": str(owner_id),
            "data": {"var": {"measurement": value}},
        }
        for value in (2, 4)
    ]
    snapshot = {"protocol_id": str(protocol_id), "records": rows, "fields": fields}
    result = compute_analysis(recipe, rows, fields)
    assert result["groups"][0]["fields"]["measurement"]["mean"] == 3
    return SimpleNamespace(
        id=uuid4(),
        protocol_id=protocol_id,
        created_by_user_id=owner_id,
        source_snapshot=snapshot,
        source_digest=canonical_digest(snapshot),
        recipe=recipe.model_dump(mode="json"),
        recipe_digest=canonical_digest(recipe.model_dump(mode="json")),
        source_selection={"mode": "latest", "filters": {"protocol_version": "1.0.0"}},
        result=result,
        result_digest=canonical_digest(result),
        status="succeeded",
        engine_version=result["engine_version"],
    )


def saved_revision():
    run = real_run()
    provenance = {
        "analysis_id": str(run.id),
        "source_digest": run.source_digest,
        "result_digest": run.result_digest,
        "engine_version": run.engine_version,
    }
    provenance["method_digest"] = method_revision_digest(
        run.recipe, run.source_selection, provenance
    )
    return SimpleNamespace(
        recipe=copy.deepcopy(run.recipe),
        recipe_digest=run.recipe_digest,
        source_selection=copy.deepcopy(run.source_selection),
        provenance=provenance,
    )


def test_complete_method_digest_accepts_real_computation_and_is_canonical():
    revision = saved_revision()
    verify_revision_integrity(revision)
    digest = revision.provenance["method_digest"]
    assert (
        method_revision_digest(
            revision.recipe, revision.source_selection, revision.provenance
        )
        == digest
    )
    reversed_provenance = dict(reversed(list(revision.provenance.items())))
    reversed_provenance["method_digest"] = "ignored-self-reference"
    assert (
        method_revision_digest(
            revision.recipe, revision.source_selection, reversed_provenance
        )
        == digest
    )


@pytest.mark.parametrize(
    "target", ["selection", "engine", "source", "result", "analysis", "recipe", "seal"]
)
def test_saved_method_tampering_fails_even_when_recipe_is_unchanged(target):
    revision = saved_revision()
    if target == "selection":
        revision.source_selection = {"mode": "latest", "filters": {}}
    elif target == "engine":
        revision.provenance["engine_version"] = "unverified-engine"
    elif target == "source":
        revision.provenance["source_digest"] = "a" * 64
    elif target == "result":
        revision.provenance["result_digest"] = "b" * 64
    elif target == "analysis":
        revision.provenance["analysis_id"] = str(uuid4())
    elif target == "recipe":
        revision.recipe["chart"] = "line"
    else:
        revision.provenance["method_digest"] = "c" * 64
    with pytest.raises(HTTPException) as error:
        verify_revision_integrity(revision)
    assert error.value.status_code == 409


def test_repairing_only_recipe_hash_does_not_reseal_a_changed_method():
    revision = saved_revision()
    revision.recipe["chart"] = "line"
    revision.recipe_digest = canonical_digest(revision.recipe)
    with pytest.raises(HTTPException) as error:
        verify_revision_integrity(revision)
    assert error.value.status_code == 409


def test_unsealed_methods_are_not_implicitly_accepted():
    revision = saved_revision()
    revision.provenance.pop("method_digest")
    with pytest.raises(HTTPException) as error:
        verify_revision_integrity(revision)
    assert error.value.status_code == 409


@pytest.mark.parametrize(
    "target,value",
    [
        ("recipe", {"value": float("nan")}),
        ("source_selection", {"value": float("inf")}),
        ("source_selection", {"value": object()}),
        ("source_selection", []),
        ("provenance", None),
        ("provenance", []),
        ("provenance", {"value": float("nan")}),
    ],
)
def test_noncanonical_method_contracts_return_409_not_serialization_errors(
    target, value
):
    revision = saved_revision()
    setattr(revision, target, value)
    with pytest.raises(HTTPException) as error:
        verify_revision_integrity(revision)
    assert error.value.status_code == 409


def test_unmodified_real_result_passes_snapshot_integrity():
    verify_run_integrity(real_run())


@pytest.mark.parametrize(
    "change", ["missing_records", "bad_uuid", "noncanonical_value"]
)
def test_snapshot_integrity_precedes_record_reference_parsing(monkeypatch, change):
    run = real_run()
    if change == "missing_records":
        run.source_snapshot.pop("records")
    elif change == "bad_uuid":
        run.source_snapshot["records"][0]["record_id"] = "not-a-uuid"
    else:
        run.source_snapshot["records"][0]["data"]["var"]["measurement"] = float("nan")
    scope = AsyncMock(return_value=(None, None, False))
    monkeypatch.setattr(record_analyses, "analysis_scope", scope)
    db = SimpleNamespace(execute=AsyncMock())
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            authorize_snapshot(db, run, SimpleNamespace(id=run.created_by_user_id))
        )
    assert error.value.status_code == 409
    assert "integrity" in error.value.detail
    scope.assert_awaited_once()
    db.execute.assert_not_awaited()


@pytest.mark.parametrize(
    "records",
    [
        [],
        None,
        {},
        [None],
        [{"record_id": "bad", "record_version": 1}],
        [{"record_id": str(uuid4()), "record_version": True}],
        [{"record_id": str(uuid4()), "record_version": "1"}],
        [{"record_id": str(uuid4()), "record_version": 0}],
    ],
)
def test_invalid_manifest_shape_returns_409_even_when_its_json_digest_matches(
    monkeypatch, records
):
    run = real_run()
    run.source_snapshot["records"] = records
    run.source_digest = canonical_digest(run.source_snapshot)
    monkeypatch.setattr(
        record_analyses, "analysis_scope", AsyncMock(return_value=(None, None, False))
    )
    db = SimpleNamespace(execute=AsyncMock())
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            authorize_snapshot(db, run, SimpleNamespace(id=run.created_by_user_id))
        )
    assert error.value.status_code == 409
    db.execute.assert_not_awaited()


def test_scope_and_owner_denials_precede_integrity_details(monkeypatch):
    run = real_run()
    run.source_snapshot = {"corrupted": True}
    scope = AsyncMock(side_effect=HTTPException(403, "Access revoked"))
    monkeypatch.setattr(record_analyses, "analysis_scope", scope)
    db = SimpleNamespace(execute=AsyncMock())
    with pytest.raises(HTTPException) as foreign_owner:
        asyncio.run(authorize_snapshot(db, run, SimpleNamespace(id=uuid4())))
    assert foreign_owner.value.status_code == 404
    scope.assert_not_awaited()
    with pytest.raises(HTTPException) as revoked:
        asyncio.run(
            authorize_snapshot(db, run, SimpleNamespace(id=run.created_by_user_id))
        )
    assert revoked.value.status_code == 403
    assert revoked.value.detail == "Access revoked"
    db.execute.assert_not_awaited()


def test_valid_snapshot_still_requires_current_record_access(monkeypatch):
    run = real_run()
    monkeypatch.setattr(
        record_analyses, "analysis_scope", AsyncMock(return_value=(None, None, False))
    )
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=list)))
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            authorize_snapshot(db, run, SimpleNamespace(id=run.created_by_user_id))
        )
    assert error.value.status_code == 403
    db.execute.assert_awaited_once()


@pytest.mark.parametrize(
    "field",
    [
        "source_digest",
        "recipe_digest",
        "source_selection",
        "question",
        "created_by_user_id",
        "project_id",
        "protocol_id",
        "pipeline_revision_id",
        "rerun_of_id",
        "summary",
        "expires_at",
        "ai_provenance",
    ],
)
def test_preview_identity_binds_every_displayed_and_executed_input(field):
    preview = SimpleNamespace(
        source_digest="a" * 64,
        recipe_digest="b" * 64,
        source_selection={"mode": "latest", "filters": {}},
        question="Synthetic comparison",
        created_by_user_id=uuid4(),
        project_id=uuid4(),
        protocol_id=uuid4(),
        pipeline_revision_id=None,
        rerun_of_id=None,
        summary={"counts": {"included": 12}, "visibility": "private"},
        expires_at=datetime(2026, 1, 1, tzinfo=UTC),
        ai_provenance={},
    )
    original = preview_identity_digest(preview)
    if field.endswith("_id"):
        setattr(preview, field, uuid4())
    elif field == "expires_at":
        preview.expires_at += timedelta(minutes=1)
    elif field == "summary":
        preview.summary["counts"]["included"] = 13
    elif field == "source_selection":
        preview.source_selection["filters"]["protocol_version"] = "2.0.0"
    elif field == "ai_provenance":
        preview.ai_provenance["request_id"] = str(uuid4())
    else:
        setattr(preview, field, "changed")
    assert preview_identity_digest(preview) != original
