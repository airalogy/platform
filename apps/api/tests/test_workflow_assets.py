"""Exact Workflow DataAsset sources; permissions never follow physical dedup."""

import asyncio
import hashlib
import io
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.knowledge import ResearchFile, ResearchFileBlob
from app.models.project import Project
from app.models.protocol_version import ProtocolVersion
from app.models.research import ResearchRun, ResearchTask
from app.models.research_asset import DataAsset, DataAssetVersion
from app.models.workflow_asset import WorkflowRunAssetInput
from app.services import workflow_assets as service
from app.services import workflow_files
from app.services.analysis_engine import canonical_digest
from app.services.workflow_contracts import validate_workflow_graph


def fixture(monkeypatch, *, content=b'{"dose": 2}', filename="input.json"):
    now = datetime.now(UTC)
    user = SimpleNamespace(id=uuid4())
    project = Project(id=uuid4(), lab_id=uuid4(), deleted_at=None)
    asset = DataAsset(
        id=uuid4(),
        lab_id=project.lab_id,
        project_id=project.id,
        name="Synthetic source",
        kind="file",
        status="ready",
        current_version=1,
        archived_at=None,
    )
    blob = ResearchFileBlob(
        id=uuid4(),
        checksum_sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        content_type="application/json" if filename.endswith("json") else "text/csv",
        storage_backend="minio",
        storage_namespace="synthetic",
        storage_object_key="safe/synthetic",
    )
    file = ResearchFile(
        id=uuid4(),
        blob_id=blob.id,
        filename=filename,
        scope_type="project",
        owner_user_id=None,
        lab_id=project.lab_id,
        project_id=project.id,
        visibility="scope",
        uploaded_by_user_id=user.id,
        created_at=now,
        archived_at=None,
    )
    version = DataAssetVersion(
        id=uuid4(),
        data_asset_id=asset.id,
        version=1,
        research_file_id=file.id,
        external_uri="",
        media_type=blob.content_type,
        checksum=blob.checksum_sha256,
        byte_size=blob.size_bytes,
        data_schema={
            "type": "object",
            "properties": {"dose": {"type": "number", "unit": "mg"}},
            "required": ["dose"],
            "additionalProperties": False,
        },
        version_metadata={"dose": 99999},
        source={},
        change_summary="Created",
        created_by_user_id=user.id,
        created_at=now,
    )
    protocol_id = uuid4()
    target = ProtocolVersion(
        id=uuid4(),
        protocol_id=protocol_id,
        version="1.0.0",
        fields={},
        json_schema={
            "vars": {
                "type": "object",
                "properties": {
                    "dose": {"type": "number", "unit": "mg"},
                    "attachment": {"type": "string", "airalogy_type": "FileIdCSV"},
                },
            }
        },
    )
    task = ResearchTask(id=uuid4(), project_id=project.id, lab_id=project.lab_id)
    asset.task_id = task.id
    workflow_revision_id = uuid4()
    run = ResearchRun(
        id=uuid4(),
        task_id=task.id,
        environment_snapshot={
            "manual_workflow": {"revision_id": str(workflow_revision_id)}
        },
    )
    values = {
        (Project, project.id): project,
        (ProtocolVersion, target.id): target,
        (ResearchTask, task.id): task,
        (ResearchRun, run.id): run,
    }
    sources = {DataAssetVersion: version, ResearchFile: file, ResearchFileBlob: blob}

    def selected_rows(statement):
        source = sources.get(statement.column_descriptions[0]["entity"])
        return SimpleNamespace(all=lambda: [source] if source else [])

    db = SimpleNamespace(
        get=AsyncMock(
            side_effect=lambda model, identity, **_: values.get((model, identity))
        ),
        execute=AsyncMock(
            return_value=SimpleNamespace(first=lambda: (asset, version, file, blob))
        ),
        scalars=AsyncMock(side_effect=selected_rows),
        add=Mock(),
        flush=AsyncMock(),
    )
    permission = AsyncMock()
    monkeypatch.setattr(
        "app.services.research_runtime.require_research_capability", permission
    )
    monkeypatch.setattr(service, "authorize_research_file", AsyncMock())
    spool = AsyncMock(side_effect=lambda _blob: io.BytesIO(content))
    monkeypatch.setattr(workflow_files, "verified_blob_spool", spool)
    graph = validate_workflow_graph(
        {
            "schema_version": 5,
            "nodes": [
                {
                    "node_id": "measure",
                    "kind": "protocol",
                    "protocol_id": str(protocol_id),
                    "protocol_version_id": str(target.id),
                }
            ],
            "edges": [],
            "asset_inputs": [{"input_id": "source", "label": "Source"}],
            "asset_bindings": [
                {
                    "binding_id": "dose",
                    "input_id": "source",
                    "source_path": ["json", "dose"],
                    "target_node_id": "measure",
                    "target_path": ["var", "dose"],
                    "value_type": "number",
                    "unit": "mg",
                }
            ],
        }
    )
    return SimpleNamespace(
        user=user,
        project=project,
        asset=asset,
        version=version,
        file=file,
        blob=blob,
        target=target,
        task=task,
        run=run,
        workflow_revision_id=workflow_revision_id,
        db=db,
        graph=graph,
        permission=permission,
        spool=spool,
    )


async def preview(f):
    return await service.preview_asset_inputs(
        f.db,
        user=f.user,
        owner=f.user,
        project=f.project,
        graph=f.graph,
        asset_versions={"source": f.version.id},
    )


def test_asset_preview_reads_real_json_not_declared_metadata_and_seals_run(monkeypatch):
    f = fixture(monkeypatch)

    async def scenario():
        result = await preview(f)
        assert result[0]["snapshot"]["json_value"] == {"dose": 2}
        assert result[0]["snapshot"]["version"]["metadata"] == {"dose": 99999}
        assert result[0]["source_digest"] == canonical_digest(result[0]["snapshot"])
        rows = await service.materialize_asset_inputs(
            f.db,
            previews=result,
            workflow_revision_id=f.workflow_revision_id,
            task=f.task,
            run=f.run,
            user=f.user,
        )
        assert len(rows) == 1 and rows[0].source_digest == result[0]["source_digest"]
        assert await service.authorize_asset_input(f.db, rows[0], f.user) == (
            f.version,
            f.file,
            f.blob,
        )
        assert f.permission.await_count >= 6
        assert f.spool.await_count == 1
        changed = deepcopy(rows[0].snapshot)
        changed["json_value"]["dose"] = 99999
        rows[0].snapshot = changed
        with pytest.raises(HTTPException) as invalid:
            service.verify_asset_input_seal(rows[0])
        assert invalid.value.status_code == 409

    asyncio.run(scenario())


@pytest.mark.parametrize("constraint", [{"maximum": 1}, {"enum": [1, 3]}])
def test_asset_preview_enforces_actual_target_constraints(monkeypatch, constraint):
    f = fixture(monkeypatch)
    f.target.json_schema["vars"]["properties"]["dose"].update(constraint)
    with pytest.raises(HTTPException) as invalid:
        asyncio.run(preview(f))
    assert invalid.value.status_code == 422
    assert "pinned Protocol Schema" in invalid.value.detail


@pytest.mark.parametrize("kind", ["oversize", "deep", "nonfinite"])
def test_asset_source_metadata_is_bounded_before_copy_or_storage_io(monkeypatch, kind):
    f = fixture(monkeypatch)
    if kind == "oversize":
        f.version.version_metadata = {
            "private": "x" * service.MAX_SOURCE_SNAPSHOT_BYTES
        }
    elif kind == "deep":
        metadata = {}
        for _ in range(100):
            metadata = {"nested": metadata}
        f.version.source = metadata
    else:
        f.version.data_schema = {"private": float("nan")}
    with pytest.raises(HTTPException) as invalid:
        asyncio.run(preview(f))
    assert invalid.value.status_code == 422
    assert "source metadata exceeds" in invalid.value.detail
    assert "private" not in invalid.value.detail
    f.spool.assert_not_awaited()


def test_asset_source_snapshot_bounds_include_actual_json_and_metadata(monkeypatch):
    f = fixture(monkeypatch)
    # Each component fits on its own; the complete sealed input does not.
    limit = len(service._bounded_json(service._version_payload(f.version), 10000)) + 100
    monkeypatch.setattr(service, "MAX_SOURCE_SNAPSHOT_BYTES", limit)
    with pytest.raises(HTTPException) as invalid:
        asyncio.run(preview(f))
    assert invalid.value.status_code == 422
    assert f.spool.await_count == 1


def test_asset_preview_validates_bound_values_with_static_initial_values(monkeypatch):
    f = fixture(monkeypatch)
    schema = f.target.json_schema["vars"]
    schema["properties"]["mode"] = {"type": "string", "enum": ["low", "high"]}
    schema["allOf"] = [
        {
            "if": {"properties": {"mode": {"const": "low"}}, "required": ["mode"]},
            "then": {"properties": {"dose": {"maximum": 1}}},
        }
    ]
    payload = f.graph.model_dump(mode="json")
    payload["nodes"][0]["initial_values"] = {"mode": "low"}
    f.graph = validate_workflow_graph(payload)
    with pytest.raises(HTTPException) as invalid:
        asyncio.run(preview(f))
    assert invalid.value.status_code == 422
    assert "pinned Protocol Schema" in invalid.value.detail


@pytest.mark.parametrize(
    "change",
    [
        "checksum",
        "size",
        "external",
        "private",
        "restricted",
        "archived",
        "wrong_project",
        "draft",
        "unsafe_backend",
    ],
)
def test_asset_preview_rejects_wrong_or_unavailable_source_before_reading_bytes(
    monkeypatch, change
):
    f = fixture(monkeypatch)
    if change == "checksum":
        f.version.checksum = "f" * 64
    elif change == "size":
        f.version.byte_size += 1
    elif change == "external":
        f.version.external_uri = "https://example.test/data"
    elif change in {"private", "restricted"}:
        f.file.visibility = change
    elif change == "archived":
        f.file.archived_at = datetime.now(UTC)
    elif change == "wrong_project":
        f.asset.project_id = uuid4()
    elif change == "draft":
        f.asset.status = "draft"
    else:
        f.blob.storage_backend = "external"
    with pytest.raises(HTTPException):
        asyncio.run(preview(f))
    f.spool.assert_not_awaited()


def test_asset_preview_rechecks_both_recipients_after_storage_io(monkeypatch):
    f = fixture(monkeypatch)

    async def revoke(_blob):
        f.file.visibility = "restricted"
        return io.BytesIO(b'{"dose": 2}')

    f.spool.side_effect = revoke
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(preview(f))
    assert rejected.value.status_code == 403


@pytest.mark.parametrize(
    "content",
    [b'{"dose": true}', b'{"dose": 1, "dose": 2}', b'{"dose": NaN}', b"not json"],
)
def test_asset_json_binding_requires_actual_valid_typed_bytes(monkeypatch, content):
    f = fixture(monkeypatch, content=content)
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(preview(f))
    assert rejected.value.status_code == 422


def test_pinned_ready_asset_survives_later_draft_but_not_its_own_readiness_revocation(
    monkeypatch,
):
    f = fixture(monkeypatch)

    async def scenario():
        rows = await service.materialize_asset_inputs(
            f.db,
            previews=await preview(f),
            workflow_revision_id=f.workflow_revision_id,
            task=f.task,
            run=f.run,
            user=f.user,
        )
        row = rows[0]
        f.asset.current_version = 2
        f.asset.status = "draft"
        assert (await service.authorize_asset_input(f.db, row, f.user))[0] is f.version
        with pytest.raises(HTTPException):
            await preview(f)  # A new pin still requires current READY approval.
        f.asset.current_version = 1
        with pytest.raises(HTTPException) as revoked:
            await service.authorize_asset_input(f.db, row, f.user)
        assert revoked.value.status_code == 409
        f.asset.current_version = 2
        f.asset.archived_at = datetime.now(UTC)
        with pytest.raises(HTTPException) as archived:
            await service.authorize_asset_input(f.db, row, f.user)
        assert archived.value.status_code == 403

    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["version", "file", "blob", "run_scope"])
def test_pinned_asset_detects_metadata_drift(monkeypatch, change):
    f = fixture(monkeypatch)

    async def scenario():
        rows = await service.materialize_asset_inputs(
            f.db,
            previews=await preview(f),
            workflow_revision_id=f.workflow_revision_id,
            task=f.task,
            run=f.run,
            user=f.user,
        )
        if change == "version":
            f.version.data_schema = {}
        elif change == "file":
            f.file.filename = "changed.json"
        elif change == "blob":
            f.blob.storage_object_key = "another-key"
        else:
            f.run.environment_snapshot = {
                "manual_workflow": {"revision_id": str(uuid4())}
            }
        with pytest.raises(HTTPException) as invalid:
            await service.authorize_asset_input(f.db, rows[0], f.user)
        assert invalid.value.status_code == 409

    asyncio.run(scenario())


@pytest.mark.parametrize("extension", ["csv", "json"])
def test_asset_file_preview_validates_actual_extension_against_pinned_target(
    monkeypatch, extension
):
    f = fixture(
        monkeypatch, content=b"value\n2\n", filename=f"measurements.{extension}"
    )
    raw = f.graph.model_dump(mode="json")
    raw["asset_bindings"] = [
        {
            "binding_id": "file",
            "input_id": "source",
            "source_path": ["file"],
            "target_node_id": "measure",
            "target_path": ["var", "attachment"],
            "value_type": "file",
        }
    ]
    f.graph = validate_workflow_graph(raw)
    if extension == "json":
        with pytest.raises(HTTPException) as wrong:
            asyncio.run(preview(f))
        assert wrong.value.status_code == 422
    else:
        result = asyncio.run(preview(f))
        assert "json_value" not in result[0]["snapshot"]


def test_asset_catalog_exposes_fields_without_storage_or_reading_bytes(monkeypatch):
    f = fixture(monkeypatch)
    f.db.scalars.side_effect = None
    f.db.scalars.return_value = SimpleNamespace(all=lambda: [f.version.id])
    result = asyncio.run(
        service.list_asset_versions(f.db, user=f.user, project=f.project)
    )
    assert result["items"][0]["version_id"] == str(f.version.id)
    assert {tuple(field["path"]) for field in result["items"][0]["fields"]} == {
        ("json", "dose"),
        ("file",),
    }
    assert not {"storage_object_key", "blob_id", "json_value"}.intersection(
        result["items"][0]
    )
    assert "storage_object_key" not in str(result)
    f.spool.assert_not_awaited()
    assert f.db.scalars.call_args.args[0]._for_update_arg is None


def test_asset_confirmation_locks_only_exact_deduplicated_sources_in_table_order(
    monkeypatch,
):
    f = fixture(monkeypatch)

    async def scenario():
        previews = await preview(f)
        assert all(
            call.args[0]._for_update_arg is None for call in f.db.execute.call_args_list
        )
        repeated = deepcopy(previews[0])
        repeated["input_id"] = "second"
        await service.materialize_asset_inputs(
            f.db,
            previews=[repeated, previews[0]],
            workflow_revision_id=f.workflow_revision_id,
            task=f.task,
            run=f.run,
            user=f.user,
        )
        locks = [
            call.args[0]
            for call in f.db.scalars.call_args_list
            if call.args[0]._for_update_arg is not None
        ]
        assert [statement.column_descriptions[0]["entity"] for statement in locks] == [
            DataAssetVersion,
            ResearchFile,
            ResearchFileBlob,
        ]
        for statement, identity in zip(
            locks, [f.version.id, f.file.id, f.blob.id], strict=True
        ):
            assert statement._for_update_arg.read is True
            assert list(statement.compile().params.values()) == [[identity]]
            assert next(iter(statement._order_by_clauses)).name == "id"
            assert statement.get_execution_options()["populate_existing"] is True

    asyncio.run(scenario())


def test_asset_missing_declared_input_does_not_guess_current_version(monkeypatch):
    f = fixture(monkeypatch)
    with pytest.raises(HTTPException) as missing:
        asyncio.run(
            service.preview_asset_inputs(
                f.db,
                user=f.user,
                owner=f.user,
                project=f.project,
                graph=f.graph,
                asset_versions={},
            )
        )
    assert missing.value.status_code == 422
    f.db.execute.assert_not_awaited()


def test_asset_model_and_file_alias_have_real_exclusive_foreign_keys():
    from app.models.workflow_file import WorkflowFileBinding

    assert {
        fk.target_fullname
        for fk in WorkflowRunAssetInput.__table__.c.data_asset_version_id.foreign_keys
    } == {"data_asset_versions.id"}
    assert WorkflowFileBinding.__table__.c.source_action_id.nullable
    assert {
        fk.target_fullname
        for fk in WorkflowFileBinding.__table__.c.asset_input_id.foreign_keys
    } == {"workflow_run_asset_inputs.id"}
    constraint = next(
        item
        for item in WorkflowFileBinding.__table__.constraints
        if item.name == "ck_workflow_file_source"
    )
    assert "source_action_id IS NULL" in str(
        constraint.sqltext
    ) and "asset_input_id IS NULL" in str(constraint.sqltext)
