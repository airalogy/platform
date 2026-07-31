import asyncio
import csv
import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from airalogy.archive import ARCHIVE_MANIFEST_PATH, validate_archive
from airalogy.record.hash import get_data_sha1
from fastapi import HTTPException
from pydantic import ValidationError

from app.main import app
from app.models.lab import Lab
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.record import Record
from app.models.record_export import RecordExport
from app.models.user import User
from app.routers import record_exports as record_exports_router
from app.routers.record_exports import (
    RecordExportParams,
    _build_export,
    _reauthorize_export_download,
    _resolve_scope_and_authorize,
)
from app.services import record_exports
from app.services.access_control import ROLE_CAPABILITIES
from app.services.record_exports import (
    RecordExportError,
    _flatten_csv_data,
    _walk_file_ids,
    _write_export_file,
    record_export_download_url,
    record_export_query,
    serialize_record,
)


def write_protocol(protocol_dir: Path) -> None:
    protocol_dir.mkdir()
    (protocol_dir / "protocol.aimd").write_text(
        "# Export fixture\n\n{{var|sample_name}}\n\n"
        "{{var|attachment_a}}\n\n{{var|attachment_b}}\n",
        encoding="utf-8",
    )
    (protocol_dir / "model.py").write_text(
        "from pydantic import BaseModel\n\n"
        "class VarModel(BaseModel):\n"
        "    sample_name: str\n"
        "    attachment_a: str | None = None\n"
        "    attachment_b: str | None = None\n",
        encoding="utf-8",
    )
    (protocol_dir / "protocol.toml").write_text(
        "[airalogy_protocol]\n"
        'id = "export_fixture"\n'
        'version = "1.0.0"\n'
        'name = "Export fixture"\n',
        encoding="utf-8",
    )


def export_models():
    lab = Lab(id=uuid4(), uid="fixture_lab", name="Fixture Lab", create_user_id=uuid4())
    project = Project(
        id=uuid4(),
        uid="fixture_project",
        name="Fixture Project",
        lab_id=lab.id,
        create_user_id=lab.create_user_id,
        type=1,
    )
    protocol = Protocol(
        id=uuid4(),
        uid="export_fixture",
        name="Export fixture",
        project_id=project.id,
        user_id=lab.create_user_id,
    )
    user = User(
        id=uuid4(),
        username="exporter",
        password_hash="hash",
        api_key_iv="iv",
    )
    data = {
        "var": {"sample_name": "水样"},
        "step": {},
        "check": {},
        "quiz": {},
    }
    record = Record(
        id=uuid4(),
        version=1,
        protocol_id=protocol.id,
        protocol_version="1.0.0",
        user_id=user.id,
        data=data,
        report="Original report",
        number=3,
        hash=get_data_sha1({"data": data}),
        created_at=datetime.now(UTC).replace(tzinfo=None),
        revision_kind="initial",
        revision_reason="",
    )
    return record, protocol, project, lab, user


def export_job(
    lab: Lab,
    project: Project,
    protocol: Protocol,
    user: User,
    *,
    export_format: str,
) -> RecordExport:
    return RecordExport(
        id=uuid4(),
        lab_id=lab.id,
        scope_type="protocol",
        project_id=project.id,
        protocol_id=protocol.id,
        export_format=export_format,
        include_revision_history=False,
        include_attachments=export_format == "aira",
        options={},
        snapshot_at=datetime.now(UTC),
        requested_by_user_id=user.id,
        status="running",
        progress_current=0,
        progress_total=1,
    )


def test_export_params_enforce_scope_and_csv_contract():
    lab_id = uuid4()
    project_id = uuid4()
    protocol_id = uuid4()

    assert RecordExportParams(scope_type="lab", lab_id=lab_id).export_format == "aira"
    with pytest.raises(ValidationError):
        RecordExportParams(scope_type="lab", lab_id=lab_id, project_id=project_id)
    with pytest.raises(ValidationError):
        RecordExportParams(scope_type="project", lab_id=lab_id, export_format="csv")
    with pytest.raises(ValidationError):
        RecordExportParams(
            scope_type="protocol",
            lab_id=lab_id,
            project_id=project_id,
            protocol_id=protocol_id,
            export_format="csv",
            include_revision_history=True,
        )


def test_only_project_manager_roles_receive_bulk_export_capability():
    assert "record.export" in ROLE_CAPABILITIES["project_manager"]
    assert "record.export" not in ROLE_CAPABILITIES["protocol_editor"]
    assert "record.export" not in ROLE_CAPABILITIES["viewer"]


def test_default_aira_export_includes_attachments_and_uses_snapshot():
    params = RecordExportParams(scope_type="lab", lab_id=uuid4())
    item = _build_export(params, uuid4())

    assert item.include_revision_history is False
    assert item.include_attachments is True
    assert item.snapshot_at.tzinfo is not None


def test_current_export_selects_latest_revision_before_applying_record_filters():
    params = RecordExportParams(
        scope_type="protocol",
        lab_id=uuid4(),
        project_id=uuid4(),
        protocol_id=uuid4(),
        protocol_version="1.0.0",
    )
    item = _build_export(params, uuid4())
    current_sql = str(record_export_query(item))

    assert "max(records.version)" in current_sql
    assert current_sql.rfind("records.protocol_version") > current_sql.rfind("anon_1")

    item.include_revision_history = True
    history_sql = str(record_export_query(item))
    assert "max(records.version)" not in history_sql


def test_only_lab_owner_can_export_entire_lab(monkeypatch):
    lab = SimpleNamespace(id=uuid4())
    session = SimpleNamespace(get=AsyncMock(return_value=lab))
    params = RecordExportParams(scope_type="lab", lab_id=lab.id)
    monkeypatch.setattr(
        record_exports_router.LabUser,
        "find_by",
        AsyncMock(return_value=SimpleNamespace(role=2)),
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(_resolve_scope_and_authorize(session, params, uuid4()))

    assert error.value.status_code == 403


def test_project_manager_can_export_only_matching_project(monkeypatch):
    lab = SimpleNamespace(id=uuid4())
    project = SimpleNamespace(id=uuid4(), lab_id=lab.id)

    async def get_model(model, _id):
        return lab if model is Lab else project

    session = SimpleNamespace(get=get_model)
    params = RecordExportParams(
        scope_type="project",
        lab_id=lab.id,
        project_id=project.id,
    )
    monkeypatch.setattr(
        record_exports_router.LabUser,
        "find_by",
        AsyncMock(return_value=SimpleNamespace(role=3)),
    )
    monkeypatch.setattr(
        record_exports_router,
        "resolve_structured_access",
        AsyncMock(
            return_value=SimpleNamespace(
                role_keys={"project_manager"},
                allows=lambda capability: capability == "export_records",
            )
        ),
    )

    result = asyncio.run(_resolve_scope_and_authorize(session, params, uuid4()))

    assert result == (lab, project, None)


def test_project_export_rejects_cross_lab_target(monkeypatch):
    lab = SimpleNamespace(id=uuid4())
    project = SimpleNamespace(id=uuid4(), lab_id=uuid4())

    async def get_model(model, _id):
        return lab if model is Lab else project

    session = SimpleNamespace(get=get_model)
    params = RecordExportParams(
        scope_type="project",
        lab_id=lab.id,
        project_id=project.id,
    )
    monkeypatch.setattr(
        record_exports_router.LabUser,
        "find_by",
        AsyncMock(return_value=SimpleNamespace(role=1)),
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(_resolve_scope_and_authorize(session, params, uuid4()))

    assert error.value.status_code == 404


def test_download_permission_is_rechecked_for_the_original_scope(monkeypatch):
    _record, protocol, project, lab, user = export_models()
    item = export_job(lab, project, protocol, user, export_format="aira")
    authorize = AsyncMock()
    monkeypatch.setattr(
        record_exports_router,
        "_resolve_scope_and_authorize",
        authorize,
    )

    asyncio.run(
        _reauthorize_export_download(SimpleNamespace(), item, user.id)
    )

    params = authorize.await_args.args[1]
    assert params.scope_type == "protocol"
    assert params.lab_id == lab.id
    assert params.project_id == project.id
    assert params.protocol_id == protocol.id


def test_file_reference_scanner_keeps_nested_field_paths():
    file_id = "airalogy.id.file.11111111-1111-4111-8111-111111111111.pdf"
    found = list(
        _walk_file_ids(
            {"var": {"table": [{"attachment": file_id}]}},
        )
    )

    assert found == [
        (
            UUID("11111111-1111-4111-8111-111111111111"),
            file_id,
            "data.var.table.0.attachment",
        )
    ]


def test_csv_columns_are_namespaced_and_nested_values_remain_json():
    flattened = _flatten_csv_data(
        {
            "var": {
                "record_id": "protocol-value",
                "table": [{"name": "样本", "value": 1}],
                "optional": None,
            },
            "step": {"prepare": True},
        }
    )

    assert flattened["var.record_id"] == "protocol-value"
    assert flattened["var.table"] == '[{"name":"样本","value":1}]'
    assert flattened["var.optional"] == ""
    assert flattened["step.prepare"] is True


def test_record_serializer_preserves_original_data_report_and_versions():
    record, protocol, project, lab, user = export_models()

    payload = serialize_record(record, protocol, project, lab, user)

    assert payload["format"] == "airalogy.record"
    assert payload["data"]["var"]["sample_name"] == "水样"
    assert payload["report"] == "Original report"
    assert payload["record_version"] == 1
    assert payload["metadata"]["protocol_version"] == "1.0.0"
    assert payload["metadata"]["revision_kind"] == "initial"


def test_jsonl_export_writes_one_standard_record_envelope(monkeypatch, tmp_path):
    record, protocol, project, lab, user = export_models()

    async def rows(*_args, **_kwargs):
        yield record, protocol, project, lab, user

    monkeypatch.setattr(record_exports, "iter_export_rows", rows)
    output, warnings = asyncio.run(
        _write_export_file(
            SimpleNamespace(),
            export_job(lab, project, protocol, user, export_format="jsonl"),
            tmp_path,
        )
    )

    payloads = [json.loads(line) for line in output.read_text().splitlines()]
    assert warnings == []
    assert len(payloads) == 1
    assert payloads[0]["format"] == "airalogy.record"
    assert payloads[0]["metadata"]["protocol_version"] == "1.0.0"


def test_csv_export_is_bom_prefixed_and_keeps_nested_values_as_json(
    monkeypatch,
    tmp_path,
):
    record, protocol, project, lab, user = export_models()
    record.data["var"]["measurements"] = [{"name": "温度", "value": 25}]

    async def rows(*_args, **_kwargs):
        yield record, protocol, project, lab, user

    monkeypatch.setattr(record_exports, "iter_export_rows", rows)
    output, warnings = asyncio.run(
        _write_export_file(
            SimpleNamespace(),
            export_job(lab, project, protocol, user, export_format="csv"),
            tmp_path,
        )
    )

    assert warnings == []
    assert output.read_bytes().startswith(b"\xef\xbb\xbf")
    with output.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    assert rows[0]["var.sample_name"] == "水样"
    assert rows[0]["var.measurements"] == '[{"name":"温度","value":25}]'


def test_expired_export_cannot_create_a_download_url():
    _record, protocol, project, lab, user = export_models()
    item = export_job(lab, project, protocol, user, export_format="jsonl")
    item.status = "succeeded"
    item.output_object_key = "record-exports/example.jsonl"
    item.expires_at = datetime.now(UTC) - timedelta(seconds=1)

    with pytest.raises(RecordExportError, match="not available"):
        asyncio.run(record_export_download_url(item))


def test_platform_aira_export_round_trip_embeds_exact_protocol(monkeypatch, tmp_path):
    record, protocol, project, lab, user = export_models()
    protocol_dir = tmp_path / "protocol"
    write_protocol(protocol_dir)
    attachment_bytes = (b"large-attachment-fixture\x00" * 100_000) + b"end"
    attachment_path = tmp_path / "attachment.bin"
    attachment_path.write_bytes(attachment_bytes)
    attachment_ids = [
        f"airalogy.id.file.{uuid4()}.bin",
        f"airalogy.id.file.{uuid4()}.bin",
    ]
    record.data["var"].update(
        {
            "attachment_a": attachment_ids[0],
            "attachment_b": attachment_ids[1],
        }
    )
    record.hash = get_data_sha1({"data": record.data})

    async def rows(*_args, **_kwargs):
        yield record, protocol, project, lab, user

    async def protocol_dirs(*_args, **_kwargs):
        return [protocol_dir]

    async def file_payloads(_db_session, record_paths, _directory, **_kwargs):
        return [
            {
                "file_id": file_id,
                "filename": attachment_path.name,
                "mime_type": "application/octet-stream",
                "source_path": record_paths[0].name,
                "source_index": 1,
                "field_path": f"data.var.attachment_{suffix}",
                "path": str(attachment_path),
            }
            for file_id, suffix in zip(attachment_ids, ("a", "b"), strict=True)
        ], []

    monkeypatch.setattr(record_exports, "iter_export_rows", rows)
    monkeypatch.setattr(record_exports, "_prepare_protocol_dirs", protocol_dirs)
    monkeypatch.setattr(record_exports, "_file_payload_specs", file_payloads)

    record_export = export_job(
        lab,
        project,
        protocol,
        user,
        export_format="aira",
    )
    output, warnings = asyncio.run(
        _write_export_file(SimpleNamespace(), record_export, tmp_path / "work")
    )

    assert warnings == []
    assert validate_archive(output) == (True, [])
    with zipfile.ZipFile(output) as archive:
        manifest = json.loads(archive.read(ARCHIVE_MANIFEST_PATH))
        assert manifest["kind"] == "records"
        assert manifest["records"][0]["protocol_version"] == "1.0.0"
        assert manifest["protocols"][0]["protocol_id"] == "export_fixture"
        assert len(manifest["files"]) == 2
        assert len(manifest["blobs"]) == 1
        assert manifest["files"][0]["blob_id"] == manifest["files"][1]["blob_id"]
        assert archive.read(manifest["blobs"][0]["archive_path"]) == attachment_bytes
        record_payload = json.loads(archive.read(manifest["records"][0]["path"]))
        assert record_payload["data"]["var"]["sample_name"] == "水样"
        assert record_payload["report"] == "Original report"
        export_manifest = json.loads(archive.read("platform/export-manifest.json"))
        assert export_manifest["scope"]["type"] == "protocol"
        assert export_manifest["statistics"]["records"] == 1
        assert export_manifest["options"]["include_attachments"] is True


def test_openapi_exposes_record_export_job_contract():
    paths = app.openapi()["paths"]
    assert "/record-exports/preview" in paths
    assert "/record-exports" in paths
    assert "/record-exports/{export_id}" in paths
    assert "/record-exports/{export_id}/download-url" in paths
