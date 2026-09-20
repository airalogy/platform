"""Resource receipts stay separate from executed source Actions and full JSON."""

import asyncio
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.libs import lab_force_delete as cleanup
from app.services import workflow_asset_runtime as runtime
from app.services import workflow_assets, workflow_files
from app.services.research_runtime import canonical_digest
from app.services.workflow_contracts import WorkflowGraph
from app.services.workflow_definitions import WorkflowRunDraft
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql


def graph():
    return WorkflowGraph.model_validate(
        {
            "schema_version": 5,
            "nodes": [
                {
                    "node_id": "measure",
                    "kind": "protocol",
                    "protocol_id": str(uuid4()),
                    "protocol_version_id": str(uuid4()),
                }
            ],
            "asset_inputs": [{"input_id": "sample", "label": "Exact source"}],
            "asset_bindings": [
                {
                    "binding_id": "amount",
                    "input_id": "sample",
                    "source_path": ["json", "amount"],
                    "target_node_id": "measure",
                    "target_path": ["var", "value"],
                    "value_type": "number",
                    "unit": "mg",
                    "cardinality": "one",
                }
            ],
        }
    )


def test_preview_exposes_only_declared_values_not_entire_source_document():
    preview = {
        key: str(uuid4())
        for key in ("data_asset_id", "data_asset_version_id", "research_file_id")
    }
    preview.update(
        input_id="sample",
        name="Calibration",
        version=1,
        filename="calibration.json",
        media_type="application/json",
        byte_size=42,
        sha256="a" * 64,
        source_digest="b" * 64,
        snapshot={
            "json_value": {"amount": 3.5, "private_note": "not a requested field"},
            "version": {
                "data_schema": {
                    "type": "object",
                    "properties": {"amount": {"type": "number", "unit": "mg"}},
                }
            },
        },
    )
    result = runtime.asset_preview_summary(graph(), [preview])
    assert result[0]["bindings"][0]["value"] == 3.5
    assert result[0]["bindings"][0]["value_digest"] == canonical_digest(3.5)
    assert "snapshot" not in result[0] and "private_note" not in str(result)
    assert result[0]["data_asset_version_id"] == preview["data_asset_version_id"]


def test_old_run_requests_keep_their_exact_serialized_contract():
    draft = WorkflowRunDraft(
        workflow_revision_id=uuid4(), task_id=uuid4(), expected_task_revision=1
    )
    assert "asset_versions" not in draft.model_dump(mode="json")
    version = uuid4()
    selected = draft.model_copy(update={"asset_versions": {"sample": version}})
    assert selected.model_dump(mode="json")["asset_versions"] == {
        "sample": str(version)
    }


def source_row():
    return SimpleNamespace(
        id=uuid4(),
        input_id="sample",
        data_asset_version_id=uuid4(),
        research_file_id=uuid4(),
        snapshot={"version": {"version": 1, "data_asset_id": str(uuid4())}},
        source_digest="a" * 64,
        digest="b" * 64,
    )


def test_asset_lineage_has_no_fabricated_action_or_record():
    row = source_row()
    ref = runtime.asset_source_ref(row)
    assert ref["kind"] == "data_asset" and ref["asset_input_id"] == str(row.id)
    assert "action_id" not in ref and "record_id" not in ref


def test_execution_rechecks_permission_after_slow_blob_read(monkeypatch):
    row = source_row()
    ref = runtime.asset_source_ref(row)
    monkeypatch.setattr(
        runtime,
        "asset_rows_for_run",
        AsyncMock(return_value=({"sample": row}, graph())),
    )
    revoked = False

    async def authorize(*args):
        if revoked:
            raise HTTPException(403, "Revoked during storage IO")
        return None, None, object()

    async def read(*args):
        nonlocal revoked
        revoked = True
        return io.BytesIO(b"verified")

    monkeypatch.setattr(workflow_assets, "authorize_asset_input", authorize)
    monkeypatch.setattr(workflow_files, "verified_blob_spool", read)
    db = SimpleNamespace(get=AsyncMock(return_value=object()))
    resolution = SimpleNamespace(
        node_id="measure", state="ready", receipt={"asset_sources": {"sample": ref}}
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            runtime.verify_asset_resolution(
                db,
                task=SimpleNamespace(owner_user_id=uuid4()),
                run=SimpleNamespace(requested_by_user_id=uuid4()),
                action=SimpleNamespace(assignee_user_id=uuid4()),
                resolution=resolution,
            )
        )
    assert error.value.status_code == 403


def test_alias_creation_rechecks_permission_after_storage_before_writing(monkeypatch):
    from app.services import knowledge

    monkeypatch.setattr(
        workflow_files, "verified_blob_spool", AsyncMock(return_value=io.BytesIO(b"{}"))
    )
    monkeypatch.setattr(
        workflow_assets,
        "authorize_asset_input",
        AsyncMock(side_effect=HTTPException(403, "Revoked during storage IO")),
    )
    quota = AsyncMock()
    monkeypatch.setattr(knowledge, "assert_research_file_upload_quota", quota)
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=None),
        get=AsyncMock(return_value=object()),
        add=AsyncMock(),
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            runtime.materialize_asset_file(
                db,
                task=SimpleNamespace(owner_user_id=uuid4()),
                run=SimpleNamespace(requested_by_user_id=uuid4()),
                node=None,
                action=SimpleNamespace(id=uuid4(), assignee_user_id=uuid4()),
                binding=SimpleNamespace(binding_id="input"),
                row=source_row(),
                file=SimpleNamespace(filename="input.json"),
                blob=object(),
            )
        )
    assert error.value.status_code == 403
    quota.assert_not_awaited()
    db.add.assert_not_called()


def test_per_card_authorization_does_not_borrow_unrelated_input_permissions(
    monkeypatch,
):
    row = source_row()
    other = source_row()
    other.input_id = "unrelated"
    selected_graph = graph()
    monkeypatch.setattr(
        runtime,
        "asset_rows_for_run",
        AsyncMock(return_value=({"sample": row, "unrelated": other}, selected_graph)),
    )
    authorize = AsyncMock()
    monkeypatch.setattr(workflow_assets, "authorize_asset_input", authorize)
    user = object()
    asyncio.run(
        runtime.authorize_run_asset_inputs(
            None, task=None, run=None, user=user, node_id="measure"
        )
    )
    authorize.assert_awaited_once_with(None, row, user)


@pytest.mark.parametrize("mutation", ["missing", "extra", "digest"])
def test_changed_asset_resolution_receipt_is_rejected_before_source_read(
    monkeypatch, mutation
):
    row = source_row()
    ref = runtime.asset_source_ref(row)
    refs = {"sample": ref}
    if mutation == "missing":
        refs = {}
    elif mutation == "extra":
        refs["unexpected"] = ref
    else:
        ref["source_digest"] = "c" * 64
    monkeypatch.setattr(
        runtime,
        "asset_rows_for_run",
        AsyncMock(return_value=({"sample": row}, graph())),
    )
    authorize = AsyncMock()
    monkeypatch.setattr(workflow_assets, "authorize_asset_input", authorize)
    resolution = SimpleNamespace(
        node_id="measure", state="ready", receipt={"asset_sources": refs}
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            runtime.verify_asset_resolution(
                None,
                task=None,
                run=None,
                action=None,
                resolution=resolution,
                user=object(),
            )
        )
    assert error.value.status_code == 409
    authorize.assert_not_awaited()


def test_asset_cleanup_works_without_any_file_alias_and_never_deletes_shared_blob():
    lab_id, project_id, task_id, file_id, blob_id = [uuid4() for _ in range(5)]
    row = SimpleNamespace(
        id=uuid4(),
        task_id=task_id,
        data_asset_version_id=uuid4(),
        research_file_id=file_id,
        blob_id=blob_id,
    )
    db = SimpleNamespace(
        scalar=AsyncMock(side_effect=[None, None]),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [row])),
        get=AsyncMock(
            side_effect=[
                SimpleNamespace(project_id=project_id),
                SimpleNamespace(id=project_id, lab_id=lab_id),
                SimpleNamespace(data_asset_id=uuid4(), research_file_id=file_id),
                SimpleNamespace(project_id=project_id, lab_id=lab_id),
                SimpleNamespace(
                    id=file_id, project_id=project_id, lab_id=lab_id, blob_id=blob_id
                ),
            ]
        ),
        execute=AsyncMock(),
    )
    asyncio.run(cleanup._delete_lab_workflow_asset_inputs(db, lab_id))
    db.execute.assert_awaited_once()
    sql = str(
        db.execute.await_args.args[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert sql.startswith("DELETE FROM workflow_run_asset_inputs")
    assert str(row.id) in sql and str(lab_id) in sql
    assert "research_file_blobs" not in sql


def test_asset_cleanup_blocks_cross_lab_references_before_writes():
    db = SimpleNamespace(scalar=AsyncMock(return_value=uuid4()), execute=AsyncMock())
    with pytest.raises(ValueError, match="Another Lab"):
        asyncio.run(cleanup._delete_lab_workflow_asset_inputs(db, uuid4()))
    db.execute.assert_not_awaited()
