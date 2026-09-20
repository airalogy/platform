"""Schema-only Project method publication, privacy, receipts and old seals."""

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

from app.models.workflow_analysis import (
    WorkflowAnalysisMethod,
    WorkflowAnalysisMethodProjectVersion,
)
from app.services import workflow_analysis_methods as service
from app.services.analysis_engine import canonical_digest
from app.services.workflow_analysis_contracts import validate_project_method_inputs
from migrations.model_registry import import_models
from tests.test_project_analysis_engine import project_fixture


def schema_inputs():
    recipe, snapshot = project_fixture()
    inputs, versions = [], {}
    for item in snapshot["inputs"]:
        source = item["snapshot"]
        protocol_id = UUID(source["protocol_id"])
        versions[item["slot_id"]] = [
            SimpleNamespace(
                **{**schema, "id": UUID(schema["id"]), "protocol_id": protocol_id},
            )
            for schema in source["schemas"]
        ]
        inputs.append(
            service.ProjectMethodInput(
                slot_id=item["slot_id"],
                protocol_id=protocol_id,
                protocol_version_ids=[row.id for row in versions[item["slot_id"]]],
            )
        )
    inputs.sort(key=lambda item: item.slot_id)
    return recipe, inputs, versions


def draft(**changes):
    _, inputs, _ = schema_inputs()
    return service.MethodPublicationDraft(
        **{
            "project_id": uuid4(),
            "pipeline_revision_id": uuid4(),
            "title": "Reusable Project method",
            "project_inputs": inputs,
            **changes,
        }
    )


def test_publication_returns_derived_slot_catalog_without_changing_sealed_contract():
    row = method()
    original_contract = deepcopy(row.project_contract)
    before = service.publication_digest(row)
    payload = service.publication_payload(row)
    fields = payload["project_input_fields"]
    assert isinstance(fields["treatment"], list)
    assert (
        next(field for field in fields["treatment"] if field["key"] == "dose")["unit"]
        == "mg"
    )
    assert (
        next(field for field in fields["assay"] if field["key"] == "response")["unit"]
        == "%"
    )
    assert all(
        isinstance(version["fields"], dict)
        for slot in payload["project_contract"]["slots"]
        for version in slot["versions"]
    )
    assert "project_input_fields" not in service.publication_content(row)
    assert row.project_contract == original_contract
    assert service.publication_digest(row) == before
    assert "project_input_fields" not in service.publication_payload(
        method(project=False)
    )


def method(*, project=True):
    recipe, inputs, versions = schema_inputs()
    contract = service.project_publication_contract(recipe, inputs, versions)
    row = SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        protocol_id=None,
        protocol_version_id=None,
        title="Shared method",
        engine_version=service.PROJECT_ENGINE_VERSION,
        recipe=recipe.model_dump(mode="json"),
        input_fields=[],
        compute_contract={},
        project_contract=contract,
        source_schema_digest=canonical_digest(contract),
        source_pipeline_revision_id=uuid4(),
        source_method_digest="b" * 64,
        created_by_user_id=uuid4(),
        created_at=datetime.now(UTC),
    )
    if not project:
        row.protocol_id, row.protocol_version_id = uuid4(), uuid4()
        row.engine_version = service.ENGINE_VERSION
        row.recipe = {"numeric_fields": ["dose"]}
        row.project_contract = {}
    row.digest = service.publication_digest(row)
    return row


def test_old_method_content_and_digest_are_byte_compatible_with_empty_addition():
    row = method(project=False)
    original = {
        "project_id": str(row.project_id),
        "protocol_id": str(row.protocol_id),
        "protocol_version_id": str(row.protocol_version_id),
        "title": row.title,
        "engine_version": row.engine_version,
        "recipe": row.recipe,
        "input_fields": row.input_fields,
        "source_schema_digest": row.source_schema_digest,
    }
    assert service.publication_content(row) == original
    assert row.digest == canonical_digest(
        {
            "schema": "airalogy.workflow-analysis-method.v1",
            "content": original,
            "source_pipeline_revision_id": str(row.source_pipeline_revision_id),
            "source_method_digest": row.source_method_digest,
        }
    )
    del row.project_contract
    assert service.publication_content(row) == original


def test_project_content_is_schema_only_with_no_private_origin_identifiers():
    row = method()
    payload = service.publication_payload(row)
    assert payload["protocol_id"] is None and payload["protocol_version_id"] is None
    assert payload["input_fields"] == [] and "compute_contract" not in payload
    serialized = json.dumps(payload)
    for private_key in (
        "source_pipeline_revision_id",
        "source_method_digest",
        "records",
        "question",
        "results",
        "source_selection",
    ):
        assert private_key not in serialized
    assert str(row.source_pipeline_revision_id) not in serialized
    payload["project_contract"]["slots"][0]["label"] = "Changed local copy"
    assert payload["project_contract"] != row.project_contract


@pytest.mark.parametrize(
    "changes",
    [
        {"protocol_version_id": uuid4()},
        {"compute_result_schema": {}},
        {"project_inputs": []},
        {"project_inputs": schema_inputs()[1][:1]},
        {"project_inputs": [schema_inputs()[1][0]] * 2},
    ],
)
def test_project_draft_rejects_ambiguous_or_missing_source_selection(changes):
    with pytest.raises(ValidationError):
        draft(**changes)


def test_version_selection_is_canonical_but_duplicate_versions_are_not_merged():
    ids = [uuid4(), uuid4()]
    item = service.ProjectMethodInput(
        slot_id="first", protocol_id=uuid4(), protocol_version_ids=ids
    )
    assert item.protocol_version_ids == sorted(ids, key=str)
    with pytest.raises(ValidationError):
        service.ProjectMethodInput(
            slot_id="first", protocol_id=uuid4(), protocol_version_ids=[ids[0], ids[0]]
        )


def test_schema_contract_validation_does_not_require_or_synthesize_records():
    recipe, inputs, versions = schema_inputs()
    contract = service.project_publication_contract(recipe, inputs, versions)
    fields = validate_project_method_inputs(recipe, contract, versions)
    assert set(fields) == {"assay", "treatment"}
    assert "records" not in json.dumps(contract)
    changed = deepcopy(contract)
    changed["slots"][0]["versions"][0]["fields"]["unexpected"] = True
    assert canonical_digest(changed) != canonical_digest(contract)
    with pytest.raises(ValueError):
        validate_project_method_inputs(recipe, changed, versions)


def test_preview_receipt_is_owner_revision_digest_expiry_bound():
    user_id, revision_id, digest = uuid4(), uuid4(), "f" * 64
    token, _ = service.sign_project_preview(
        user_id=user_id, revision_id=revision_id, digest=digest
    )
    service.verify_project_preview(
        token, user_id=user_id, revision_id=revision_id, digest=digest
    )
    for changes in (
        {"user_id": uuid4()},
        {"revision_id": uuid4()},
        {"digest": "e" * 64},
    ):
        with pytest.raises(HTTPException) as failure:
            service.verify_project_preview(
                token,
                **{
                    "user_id": user_id,
                    "revision_id": revision_id,
                    "digest": digest,
                    **changes,
                },
            )
        assert failure.value.status_code == 409
    expired, _ = service.sign_project_preview(
        user_id=user_id,
        revision_id=revision_id,
        digest=digest,
        now=datetime.now(UTC) - timedelta(hours=1),
    )
    for invalid in (None, expired, token + "invalid"):
        with pytest.raises(HTTPException) as failure:
            service.verify_project_preview(
                invalid, user_id=user_id, revision_id=revision_id, digest=digest
            )
        assert failure.value.status_code == 409


def preview_fixture(monkeypatch):
    recipe, inputs, versions = schema_inputs()
    params = draft(project_inputs=inputs)
    project = SimpleNamespace(id=params.project_id, name="Shared destination")
    pipeline = SimpleNamespace(id=uuid4(), protocol_id=None)
    revision = SimpleNamespace(
        id=params.pipeline_revision_id,
        revision=1,
        recipe=recipe.model_dump(mode="json"),
        provenance={
            "engine_version": service.PROJECT_ENGINE_VERSION,
            "method_digest": "d" * 64,
            "input_contracts": {
                "inputs": [
                    {
                        "slot_id": item.slot_id,
                        "protocol_id": str(item.protocol_id),
                        "schemas": [
                            {"id": str(version.id)}
                            for version in versions[item.slot_id]
                        ],
                    }
                    for item in inputs
                ]
            },
        },
    )
    monkeypatch.setattr(service, "_project_versions", AsyncMock(return_value=versions))
    return params, project, pipeline, revision, versions


def test_project_preview_seals_destination_and_only_copies_selected_versions(
    monkeypatch,
):
    async def exercise():
        params, project, pipeline, revision, versions = preview_fixture(monkeypatch)
        user = SimpleNamespace(id=uuid4())
        preview = await service._preview_project_publication(
            None, user, project, pipeline, revision, params
        )
        assert preview["publication"]["project_contract"]["slots"][0]["versions"][0][
            "id"
        ] == str(versions["assay"][0].id)
        assert preview["destination"]["project_name"] == project.name
        project.name = "Renamed destination"
        newer = await service._preview_project_publication(
            None, user, project, pipeline, revision, params
        )
        assert preview["preview_digest"] != newer["preview_digest"]

    asyncio.run(exercise())


def test_project_preview_rejects_protocol_reassignment(monkeypatch):
    async def exercise():
        params, project, pipeline, revision, _ = preview_fixture(monkeypatch)
        params.project_inputs[0].protocol_id = uuid4()
        with pytest.raises(HTTPException) as failure:
            await service._preview_project_publication(
                None, SimpleNamespace(id=uuid4()), project, pipeline, revision, params
            )
        assert failure.value.status_code == 422
        service._project_versions.assert_not_awaited()

    asyncio.run(exercise())


def test_published_project_read_checks_every_typed_reference(monkeypatch):
    async def exercise():
        row = method()
        _recipe, inputs, versions = schema_inputs()
        monkeypatch.setattr(
            service, "_project_versions", AsyncMock(return_value=versions)
        )
        references = [
            SimpleNamespace(
                slot_id=item.slot_id,
                protocol_id=item.protocol_id,
                protocol_version_id=version.id,
                schema_digest=service.schema_digest(version),
            )
            for item in inputs
            for version in versions[item.slot_id]
        ]
        db = SimpleNamespace(
            scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: references))
        )
        await service.verify_project_publication(
            db, SimpleNamespace(id=uuid4()), SimpleNamespace(id=row.project_id), row
        )
        references.pop()
        with pytest.raises(HTTPException) as failure:
            await service.verify_project_publication(
                db, SimpleNamespace(id=uuid4()), SimpleNamespace(id=row.project_id), row
            )
        assert failure.value.status_code == 409

    asyncio.run(exercise())


def test_migration_and_models_keep_relational_source_protection_and_downgrade_gate():
    import_models()
    migration = import_module("migrations.versions.0073_workflow_project_analysis")
    assert migration.down_revision == "0072_analysis_publications"
    assert set(migration.TABLE_NAMES) == {
        WorkflowAnalysisMethodProjectVersion.__tablename__
    }
    columns = WorkflowAnalysisMethod.__table__.c
    assert columns.protocol_id.nullable and columns.protocol_version_id.nullable
    assert not columns.project_contract.nullable
    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in WorkflowAnalysisMethod.__table__.constraints
        if hasattr(constraint, "sqltext")
    }
    assert (
        constraints["ck_workflow_analysis_method_project_scope"]
        == migration.SCOPE_CHECK
    )
    ddl = str(
        CreateTable(WorkflowAnalysisMethodProjectVersion.__table__).compile(
            dialect=postgresql.dialect()
        )
    )
    assert "REFERENCES protocol_versions (id) ON DELETE RESTRICT" in ddl
    assert "REFERENCES protocols (id) ON DELETE RESTRICT" in ddl


def test_downgrade_locks_methods_and_graphs_before_any_destructive_operation(
    monkeypatch,
):
    migration = import_module("migrations.versions.0073_workflow_project_analysis")
    statements = []
    connection = SimpleNamespace(
        execute=lambda statement: statements.append(str(statement)),
        scalar=lambda statement: statements.append(str(statement)) or True,
    )
    operations = Mock()
    operations.get_bind.return_value = connection
    monkeypatch.setattr(migration, "op", operations)
    with pytest.raises(RuntimeError, match="Cannot downgrade"):
        migration.downgrade()
    assert statements[0].startswith("LOCK TABLE")
    assert "workflow_revisions" in statements[0]
    assert "ACCESS EXCLUSIVE MODE" in statements[0]
    assert "graph ->> 'schema_version' = '6'" in statements[1]
    operations.drop_table.assert_not_called()


def test_project_identity_trigger_qualifies_json_columns_not_protocol_version_text(
    monkeypatch,
):
    migration = import_module("migrations.versions.0073_workflow_project_analysis")
    operations = Mock()
    monkeypatch.setattr(migration, "op", operations)
    migration.upgrade()
    trigger = next(
        str(call.args[0])
        for call in operations.execute.call_args_list
        if "CREATE FUNCTION check_workflow_project_method_version()"
        in str(call.args[0])
    )
    assert "AS slot_entry(slot_json)" in trigger
    assert "AS version_entry(version_json)" in trigger
    assert "slot_entry.slot_json ->> 'protocol_id'" in trigger
    assert "version_entry.version_json ->> 'id'" in trigger
    assert "version_entry.version_json ->> 'schema_digest'" in trigger
