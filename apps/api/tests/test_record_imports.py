import asyncio
import csv
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from airalogy.ingest import import_records
from fastapi import BackgroundTasks, HTTPException, UploadFile

from app.routers import records as router
from app.services import record_imports as service


SCHEMA = {"vars": {"properties": {
    "sample_id": {"type": "string", "title": "样本编号"},
    "score": {"type": "number", "title": "分数", "minimum": 0, "maximum": 100},
    "notes": {"type": "string", "title": "备注", "default": ""},
}, "required": ["sample_id", "score"]}}
AIMD = '{{var|sample_id: str}}\n{{var|score: float, ge=0, le=100}}\n{{var|notes: str = ""}}'


def prepare(text, schema=SCHEMA, fmt="csv"):
    return service.prepare_tabular(text.encode(), fmt, schema)


def test_template_has_only_canonical_headers_no_fabricated_values():
    assert list(csv.reader(io.StringIO(service.template_csv(SCHEMA)))) == [
        ["var.sample_id", "var.score", "var.notes"]]
    fields = service.import_fields(SCHEMA)
    assert [f["required"] for f in fields] == [True, True, False]
    assert fields[0]["title"] == "样本编号"


def test_bom_reordered_optional_omitted_and_zero_are_lossless():
    result = prepare('\ufeffvar.score,sample_id\r\n0,"ID,001"\r\n')
    assert not result["errors"]
    assert list(csv.reader(io.StringIO(result["content"].decode()))) == [
        ["var.score", "var.sample_id"], ["0", "ID,001"]]
    imported = import_records(aimd_content=AIMD, rows=list(csv.DictReader(io.StringIO(result["content"].decode()))))
    assert imported.ok and imported.records[0]["data"]["var"]["sample_id"] == "ID,001"


@pytest.mark.parametrize(("text", "code"), [
    ("样本编号,score\nA,1\n", "unknown_field"),
    ("sample_id,score,多余空列\nA,1,\n", "unknown_field"),
    ("Sample_id,score\nA,1\n", "unknown_field"),
    (" sample_id,score\nA,1\n", "unknown_field"),
    ("sample_id,sample_id\nA,B\n", "duplicate_header"),
    ("sample_id,var.sample_id,score\nA,B,1\n", "duplicate_target"),
    ("sample_id,,score\nA,,1\n", "blank_header"),
    ("sample_id,score\nA,1,extra\n", "row_width"),
    ("sample_id,score\nA\n", "row_width"),
    ('sample_id,score\n"A,1\n', "invalid_csv"),
    ("sample_id,score\n", "empty_file"),
    ("sample_id,score\nA,#REF!\n", "spreadsheet_error"),
])
def test_strict_header_and_structure_errors(text, code):
    result = prepare(text)
    assert code in [item["code"] for item in result["errors"]]


def test_multiline_records_report_physical_csv_line_numbers():
    result = prepare('sample_id,score,notes\nA,2,"first\nsecond"\nB,#REF!,\n')
    assert result["line_numbers"] == [2, 4]
    assert result["errors"][0]["line_number"] == 4
    assert service.format_errors([{"row_number": 2, "column": "score", "message": "Field required"}], result["line_numbers"])[0]["line_number"] == 4


def test_tsv_and_encoding_and_row_limit(monkeypatch):
    assert not prepare("score\tsample_id\n1\tA\n", fmt="tsv")["errors"]
    assert service.prepare_tabular(b"\xff", "csv", SCHEMA)["errors"][0]["code"] == "invalid_encoding"
    monkeypatch.setattr(service, "MAX_IMPORT_ROWS", 1)
    assert prepare("sample_id,score\nA,1\nB,2\n")["errors"][0]["code"] == "too_many_rows"


def test_identical_display_titles_do_not_make_aliases():
    schema = {"vars": {"properties": {"a": {"title": "总分"}, "b": {"title": "总分"}}}}
    assert prepare("总分\n1\n", schema)["errors"][0]["code"] == "unknown_field"


def test_preview_signature_expiry_tamper_and_binding(monkeypatch):
    version = SimpleNamespace(id="v1", json_schema=SCHEMA, fields={})
    digest = service.preview_fingerprint(b"file", {}, version, "user1")
    token = service.sign_preview(digest, "private-secret")
    assert service.verify_preview(token, digest, "private-secret")
    assert not service.verify_preview(token + "bad", digest, "private-secret")
    assert not service.verify_preview(token + "中文", digest, "private-secret")
    assert not service.verify_preview(token, digest, "different-secret")
    assert service.preview_fingerprint(b"file", {}, version, "user2") != digest
    assert service.preview_fingerprint(b"changed", {}, version, "user1") != digest
    version.id = "v2"
    assert service.preview_fingerprint(b"file", {}, version, "user1") != digest
    monkeypatch.setattr(service.time, "time", lambda: int(token.split(".")[0]) + 1)
    assert not service.verify_preview(token, digest, "private-secret")


def test_reserved_record_id_and_explicit_variable_id_remain_distinct():
    schema = {"vars": {"properties": {"record_id": {"type": "string"}}}}
    result = prepare("record_id,var.record_id\nidentifier,sample\n", schema)
    assert not result["errors"]
    assert result["content"].decode().splitlines()[0] == "record_id,var.record_id"


@pytest.fixture
def api_context(monkeypatch, tmp_path):
    protocol = SimpleNamespace(id=uuid4(), project_id=uuid4(), latest_version="1.0.0", env_vars=None, name="Synthetic study")
    version = SimpleNamespace(id=uuid4(), version="1.0.0", package_name="fixture", json_schema=SCHEMA, fields={})
    project = SimpleNamespace(id=protocol.project_id, lab_id=uuid4())
    user = SimpleNamespace(id=uuid4(), api_key="synthetic-key")
    (tmp_path / "fixture").mkdir()
    monkeypatch.setattr(router.config, "PROTOCOL_DIR", str(tmp_path))
    monkeypatch.setattr(router.Protocol, "find", AsyncMock(return_value=protocol))
    monkeypatch.setattr(router.Project, "find", AsyncMock(return_value=project))
    monkeypatch.setattr(router.ProtocolVersion, "find_by", AsyncMock(return_value=version))
    permission = AsyncMock()
    monkeypatch.setattr(router, "check_user_permission", permission)
    monkeypatch.setattr(router, "prepare_protocol_package", AsyncMock())

    async def execute(action, package, params):
        assert action == "import_records"
        result = import_records(aimd_content=AIMD, input_path=tmp_path / package / params["input_filename"], input_format=params["input_format"])
        return {"success": True, "data": {"records": result.records, "errors": [vars(e) for e in result.errors]}}

    executor = AsyncMock(side_effect=execute)
    monkeypatch.setattr(router, "protocol_exec", executor)
    from app.services import workflow_files
    file_auth = AsyncMock()
    monkeypatch.setattr(workflow_files, "authorize_record_files", file_auth)
    monkeypatch.setattr(router, "commit_record_resources", AsyncMock())
    db = SimpleNamespace(scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])), scalar=AsyncMock(return_value=0),
                         add=lambda record: added.append(record), flush=AsyncMock(), commit=AsyncMock(), rollback=AsyncMock())
    added = []

    async def call(text="sample_id,score\nS-001,0\n", preview=True, token=""):
        return await router.import_protocol_records(protocol.id, db, user, BackgroundTasks(),
            file=UploadFile(filename="records.csv", file=io.BytesIO(text.encode())), input_format="csv",
            allow_extra_var_fields=False, require_complete_quiz=False, include_template_defaults=True,
            preview=preview, preview_token=token)
    return SimpleNamespace(call=call, db=db, added=added, executor=executor, permission=permission, version=version,
                           user=user, protocol=protocol, file_auth=file_auth, tmp_path=tmp_path)


def test_api_preview_then_confirm_and_template_authorization(api_context):
    c = api_context
    template = asyncio.run(router.get_record_import_template(c.protocol.id, c.db, c.user))
    assert template["csv"].startswith("var.sample_id,")
    c.permission.assert_awaited_once()
    result = asyncio.run(c.call())
    assert result["valid_count"] == 1 and result["preview_token"] and not result["errors"]
    assert c.added == []
    c.db.commit.assert_not_awaited()
    c.db.flush.assert_not_awaited()
    assert not list((c.tmp_path / "fixture").iterdir())
    confirmed = asyncio.run(c.call(preview=False, token=result["preview_token"]))
    assert confirmed["imported_count"] == 1 and len(c.added) == 1
    assert c.added[0].data["var"]["score"] == 0
    c.db.commit.assert_awaited_once()


def test_invalid_rows_never_partially_import(api_context):
    c = api_context
    text = "sample_id,score\nA,1\nB,#REF!\nC,101\nD,\n"
    result = asyncio.run(c.call(text))
    assert not result["preview_token"]
    assert {"spreadsheet_error", "number", "range", "required"} <= {e["code"] for e in result["errors"]}
    with pytest.raises(HTTPException):
        asyncio.run(c.call(text, preview=False))
    assert not c.added
    c.db.commit.assert_not_awaited()


def test_stale_file_or_protocol_and_revoked_permission_block_confirm(api_context):
    c = api_context
    token = asyncio.run(c.call())["preview_token"]
    with pytest.raises(HTTPException) as error:
        asyncio.run(c.call("sample_id,score\nchanged,2\n", preview=False, token=token))
    assert error.value.status_code == 409
    c.version.id = uuid4()
    with pytest.raises(HTTPException):
        asyncio.run(c.call(preview=False, token=token))
    c.permission.side_effect = HTTPException(403, "Not allowed")
    with pytest.raises(HTTPException) as error:
        asyncio.run(c.call())
    assert error.value.status_code == 403
    with pytest.raises(HTTPException):
        asyncio.run(router.get_record_import_template(c.protocol.id, c.db, c.user))
    assert not c.added


def test_preview_rechecks_attachment_access(api_context):
    c = api_context
    c.file_auth.side_effect = HTTPException(403, "Not allowed")
    with pytest.raises(HTTPException):
        asyncio.run(c.call())
    c.db.commit.assert_not_awaited()
    assert not c.added
