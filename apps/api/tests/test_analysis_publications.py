"""Real numeric projection, immutable publication and separate authorization."""

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.analysis_publication import AnalysisEvidencePublication
from app.services import analysis_publications as service
from app.services import project_analyses, record_analyses
from app.services.analysis_engine import (
    AnalysisRecipe,
    canonical_digest,
    compute_analysis,
)
from app.services.project_analysis_engine import compute_project_analysis
from migrations.model_registry import MODEL_MODULES, import_models
from tests.test_project_analyses import interpretation
from tests.test_project_analysis_engine import make_source, project_fixture


def project_run():
    recipe, snapshot = project_fixture()
    result = compute_project_analysis(recipe, snapshot)
    return SimpleNamespace(
        id=uuid4(),
        project_id=UUID(snapshot["project_id"]),
        protocol_id=None,
        source_scope="project",
        engine_version=service.PROJECT_ENGINE_VERSION,
        status="succeeded",
        source_snapshot=snapshot,
        source_digest=canonical_digest(snapshot),
        recipe=recipe.model_dump(mode="json"),
        recipe_digest=canonical_digest(recipe.model_dump(mode="json")),
        result=result,
        result_digest=canonical_digest(result),
        created_by_user_id=uuid4(),
    )


def protocol_run():
    source = make_source(
        1,
        [{"dose": 2, "batch": "a"}, {"dose": 4, "batch": "b"}],
        {"dose": {"type": "number", "unit": "mg"}, "batch": {"type": "string"}},
    )
    recipe = AnalysisRecipe(numeric_fields=["dose"], group_by=["batch"])
    result = compute_analysis(recipe, source["records"], source["fields"])
    return SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        protocol_id=UUID(source["protocol_id"]),
        source_scope="protocol",
        engine_version=service.ENGINE_VERSION,
        status="succeeded",
        source_snapshot=source,
        source_digest=canonical_digest(source),
        recipe=recipe.model_dump(mode="json"),
        recipe_digest=canonical_digest(recipe.model_dump(mode="json")),
        result=result,
        result_digest=canonical_digest(result),
        created_by_user_id=uuid4(),
    )


def draft(project=True, **changes):
    return service.AnalysisPublicationDraft.model_validate(
        {
            "task_id": str(uuid4()),
            "title": "Selected synthetic evidence",
            "summary": "Human supplied summary",
            "sections": (
                [
                    {"section_id": "source:treatment", "fields": ["dose"]},
                    {"section_id": "source:assay", "fields": ["response"]},
                ]
                if project
                else [{"section_id": "protocol", "fields": ["dose"]}]
            ),
            **changes,
        }
    )


def publication(run, params, interpretation_row=None):
    row = AnalysisEvidencePublication(
        id=uuid4(),
        project_id=run.project_id,
        task_id=params.task_id,
        analysis_run_id=run.id,
        evidence_id=uuid4(),
        created_by_user_id=run.created_by_user_id,
        title=params.title,
        summary=params.summary,
        selection=params.model_dump(mode="json"),
        snapshot=service.build_publication_snapshot(run, params, interpretation_row),
        source_digest=run.source_digest,
        recipe_digest=run.recipe_digest,
        result_digest=run.result_digest,
        interpretation_revision_id=interpretation_row.id
        if interpretation_row
        else None,
        interpretation_digest=interpretation_row.content_digest
        if interpretation_row
        else None,
        idempotency_key=uuid4(),
        request_digest="c" * 64,
        created_at=datetime.now(UTC),
    )
    row.digest = service.analysis_publication_digest(row)
    return row


def interpreted(run):
    content = interpretation()
    row = SimpleNamespace(
        id=uuid4(),
        analysis_run_id=run.id,
        revision=1,
        result_digest=run.result_digest,
        content=content.model_dump(mode="json"),
        resolved_evidence=project_analyses.interpretation_evidence(run.result, content),
        created_by_user_id=run.created_by_user_id,
    )
    row.content_digest = project_analyses.interpretation_digest(row)
    return row


def test_protocol_publication_keeps_real_all_groups_and_does_not_publish_raw_rows():
    run, params = protocol_run(), draft(False)
    snapshot = service.build_publication_snapshot(run, params)
    report = snapshot["sections"][0]["report"]
    assert [group["fields"]["dose"]["mean"] for group in report["groups"]] == [2, 4]
    assert len(report["groups"]) == 2
    assert report["fields"][0]["unit"] == "mg"
    assert report["counts"] == run.result["counts"]
    assert report["group_by"] == run.result["group_by"]
    assert (
        snapshot["sources"][0]["records"][0]["record_id"]
        == run.source_snapshot["records"][0]["record_id"]
    )
    encoded = json.dumps(snapshot)
    assert (
        '"data"' not in encoded
        and '"question"' not in encoded
        and '"source_selection"' not in encoded
    )
    assert snapshot["interpretation"] is None
    snapshot["sections"][0]["report"]["groups"][0]["fields"]["dose"]["mean"] = 99
    assert run.result["groups"][0]["fields"]["dose"]["mean"] == 2


def test_project_publication_keeps_all_source_refs_and_join_counts_without_derived_rows():
    run, params = project_run(), draft()
    snapshot = service.build_publication_snapshot(run, params)
    assert len(snapshot["sources"]) == 2
    assert snapshot["join_audit"] == run.result["join"]["audit"]
    assert snapshot["warnings"] == [{"code": "association_not_causation"}]
    assert '"row_id"' not in json.dumps(snapshot)
    assert '"values"' not in json.dumps(snapshot)
    assert snapshot["analysis"]["result_digest"] == run.result_digest


def test_project_join_statistics_can_be_explicitly_selected_without_copying_join_rows():
    run = project_run()
    field = run.result["join"]["report"]["fields"][0]["key"]
    params = draft(sections=[{"section_id": "join", "fields": [field]}])
    snapshot = service.build_publication_snapshot(run, params)
    assert (
        snapshot["sections"][0]["report"]["groups"][0]["fields"][field]
        == run.result["join"]["report"]["groups"][0]["fields"][field]
    )
    assert len(snapshot["sources"]) == 2
    assert "rows" not in snapshot


@pytest.mark.parametrize("scope", [True, False])
def test_unknown_or_uncomputed_field_is_rejected(scope):
    run = project_run() if scope else protocol_run()
    params = draft(scope)
    params.sections[0].fields = ["invented_measurement"]
    with pytest.raises(HTTPException) as error:
        service.build_publication_snapshot(run, params)
    assert error.value.status_code == 422


def test_project_interpretation_pins_exact_revision_and_requires_all_cited_fields():
    run = project_run()
    row = interpreted(run)
    params = draft(interpretation_revision_id=row.id)
    snapshot = service.build_publication_snapshot(run, params, row)
    assert snapshot["interpretation"]["resolved_evidence"] == row.resolved_evidence
    params.sections.pop()
    with pytest.raises(HTTPException) as error:
        service.build_publication_snapshot(run, params, row)
    assert error.value.status_code == 422


def test_changed_interpretation_cannot_be_resolved_against_new_result():
    run = project_run()
    row = interpreted(run)
    row.result_digest = "f" * 64
    with pytest.raises(HTTPException) as error:
        service.build_publication_snapshot(
            run, draft(interpretation_revision_id=row.id), row
        )
    assert error.value.status_code == 409


@pytest.mark.parametrize(
    "change", ["result", "task", "source", "identity", "selection", "interpretation"]
)
def test_publication_seal_rejects_source_identity_and_content_tampering(change):
    row = publication(protocol_run(), draft(False))
    if change == "result":
        row.snapshot["sections"][0]["report"]["counts"]["total"] = 999
    elif change == "task":
        row.task_id = uuid4()
    elif change == "source":
        row.source_digest = "b" * 64
    elif change == "identity":
        row.evidence_id = uuid4()
    elif change == "selection":
        row.selection["sections"][0]["fields"] = ["another"]
    else:
        row.interpretation_revision_id = uuid4()
    with pytest.raises(HTTPException) as error:
        service.publication_payload(row)
    assert error.value.status_code == 409


def test_publication_payload_never_contains_private_selection_or_request_credentials():
    row = publication(protocol_run(), draft(False))
    payload = service.publication_payload(row)
    assert payload["snapshot"]["schema"] == service.PUBLICATION_SCHEMA
    assert (
        not {
            "selection",
            "request_digest",
            "idempotency_key",
            "source_snapshot",
            "question",
            "recipe",
        }
        & payload.keys()
    )


@pytest.mark.parametrize(
    "engine,status",
    [
        ("airalogy.analysis-compute.v1", "succeeded"),
        (service.ENGINE_VERSION, "pending"),
        (service.ENGINE_VERSION, "failed"),
    ],
)
def test_only_real_successful_builtin_outputs_are_supported(engine, status):
    run = protocol_run()
    run.engine_version, run.status = engine, status
    with pytest.raises(HTTPException) as error:
        service.build_publication_snapshot(run, draft(False))
    assert error.value.status_code == 409


@pytest.mark.parametrize(
    "changes",
    [
        {"sections": []},
        {"title": "  "},
        {"sections": [{"section_id": "protocol", "fields": ["dose", "dose"]}]},
        {"whole_report": True},
    ],
)
def test_publication_request_rejects_ambiguous_or_implicit_sharing(changes):
    with pytest.raises(ValidationError):
        draft(False, **changes)


def test_selected_publication_has_bounded_size(monkeypatch):
    monkeypatch.setattr(service, "MAX_PUBLICATION_BYTES", 100)
    with pytest.raises(HTTPException) as error:
        service.build_publication_snapshot(protocol_run(), draft(False))
    assert error.value.status_code == 422


def test_preview_receipt_binds_user_analysis_digest_and_expiry():
    user_id, analysis_id, digest = uuid4(), uuid4(), "a" * 64
    token, _ = service.sign_preview(
        user_id=user_id, analysis_id=analysis_id, digest=digest
    )
    service.verify_preview(
        token, user_id=user_id, analysis_id=analysis_id, digest=digest
    )
    for bad in [{"user_id": uuid4()}, {"analysis_id": uuid4()}, {"digest": "b" * 64}]:
        with pytest.raises(HTTPException):
            service.verify_preview(
                token,
                **{
                    "user_id": user_id,
                    "analysis_id": analysis_id,
                    "digest": digest,
                    **bad,
                },
            )
    expired, _ = service.sign_preview(
        user_id=user_id,
        analysis_id=analysis_id,
        digest=digest,
        now=datetime.now(UTC) - timedelta(hours=1),
    )
    with pytest.raises(HTTPException):
        service.verify_preview(
            expired, user_id=user_id, analysis_id=analysis_id, digest=digest
        )


@pytest.mark.parametrize("renamed", ["task", "project"])
def test_preview_seal_binds_displayed_destination_even_without_revision_change(
    monkeypatch, renamed
):
    run, params = protocol_run(), draft(False)
    user = SimpleNamespace(id=run.created_by_user_id)
    task = SimpleNamespace(
        id=params.task_id, project_id=run.project_id, revision=1, title="Original Task"
    )
    project = SimpleNamespace(id=run.project_id, name="Original Project")
    monkeypatch.setattr(service, "_task", AsyncMock(return_value=(task, project)))
    monkeypatch.setattr(service, "_run", AsyncMock(return_value=run))
    monkeypatch.setattr(service, "_exact_sources", AsyncMock())
    monkeypatch.setattr(service, "_interpretation", AsyncMock(return_value=None))
    db = SimpleNamespace(scalar=AsyncMock(return_value=None))
    original = asyncio.run(
        service.preview_analysis_publication(db, run.id, user, params)
    )
    if renamed == "task":
        task.title = "Changed Task"
    else:
        project.name = "Changed Project"
    changed = asyncio.run(
        service.preview_analysis_publication(db, run.id, user, params)
    )
    assert original["preview_digest"] != changed["preview_digest"]
    assert original["destination"] != changed["destination"]
    assert original["publication"] == changed["publication"]
    assert task.revision == 1


def test_private_report_authorization_retains_owner_gate_before_source_helper(
    monkeypatch,
):
    checked = AsyncMock()
    monkeypatch.setattr(record_analyses, "authorize_analysis_sources", checked)
    run = protocol_run()
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            record_analyses.authorize_snapshot(Mock(), run, SimpleNamespace(id=uuid4()))
        )
    assert error.value.status_code == 404
    checked.assert_not_awaited()
    project_checked = AsyncMock()
    monkeypatch.setattr(project_analyses, "authorize_project_sources", project_checked)
    with pytest.raises(HTTPException):
        asyncio.run(
            project_analyses.authorize_project_snapshot(
                Mock(), project_run(), SimpleNamespace(id=uuid4())
            )
        )
    project_checked.assert_not_awaited()


def test_exact_source_recheck_rejects_same_identity_with_changed_record_content(
    monkeypatch,
):
    run = protocol_run()
    changed = deepcopy(run.source_snapshot)
    changed["records"][0]["data"]["var"]["dose"] = 90
    monkeypatch.setattr(
        service,
        "capture_sources",
        AsyncMock(return_value=(changed, None, SimpleNamespace(id=run.project_id))),
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            service._exact_sources(
                Mock(), run, SimpleNamespace(id=run.created_by_user_id)
            )
        )
    assert error.value.status_code == 409


def test_publication_model_foreign_keys_and_migration_protect_exact_evidence():
    import_models()
    assert "app.models.analysis_publication" in MODEL_MODULES
    table = AnalysisEvidencePublication.__table__
    assert all(key.ondelete == "RESTRICT" for key in table.foreign_keys)
    sql = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert "UNIQUE (created_by_user_id, idempotency_key)" in sql
    assert "UNIQUE (evidence_id)" in sql
    assert (
        "FOREIGN KEY(evidence_id) REFERENCES research_evidence (id) ON DELETE RESTRICT"
        in sql
    )
    migration = import_module("migrations.versions.0072_analysis_publications")
    assert migration.down_revision == "0071_workflow_asset_inputs"
    assert migration.TABLE_NAME == table.name


def test_migration_downgrade_refuses_to_erase_publications(monkeypatch):
    migration = import_module("migrations.versions.0072_analysis_publications")
    operations = Mock()
    operations.get_bind.return_value.execute.return_value.scalar.return_value = True
    monkeypatch.setattr(migration, "op", operations)
    with pytest.raises(RuntimeError, match="Cannot downgrade"):
        migration.downgrade()
    operations.drop_table.assert_not_called()
