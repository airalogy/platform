"""Attachment contracts and live authorization without storage or database servers."""

import asyncio
import copy
import hashlib
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response
from sqlalchemy.dialects import postgresql

from app.models.airalogy_file import AiralogyFile
from app.models.analysis_compute import AnalysisCompute, AnalysisComputeInputFile
from app.models.knowledge import ResearchFileBlob
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.research_execution import ResearchComputeJobInput
from app.services import analysis_compute_files as files
from app.services import record_analyses
from app.services.analysis_engine import AnalysisError


class Session:
    def __init__(self, rows=()):
        self.rows = {}
        self.written = []
        self.add = Mock(side_effect=self._add)
        self.flush = AsyncMock()
        for model, key, row in rows:
            self.rows[model, key] = row
        self.get = AsyncMock(
            side_effect=lambda model, key, **kwargs: self.rows.get((model, key))
        )
        self.scalars = AsyncMock(side_effect=self._scalars)

    def _add(self, value):
        self.written.append(value)
        key = (
            value.input_row_id
            if isinstance(value, AnalysisComputeInputFile)
            else value.id
        )
        self.rows[type(value), key] = value

    def _scalars(self, statement):
        model = statement.column_descriptions[0]["entity"]
        return SimpleNamespace(
            all=lambda: [value for (cls, _), value in self.rows.items() if cls is model]
        )


def case(monkeypatch, *, count=2, field=None):
    user, approver = SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())
    protocol_id, project_id, version_id = uuid4(), uuid4(), uuid4()
    schema = {
        "vars": {
            "type": "object",
            "properties": {
                "upload": field
                or {
                    "type": "string",
                    "airalogy_type": "FileId",
                    "file_extension": "csv",
                }
            },
        }
    }
    version = SimpleNamespace(
        id=version_id, protocol_id=protocol_id, version="1.0.0", json_schema=schema
    )
    snapshot = {
        "schema_version": 1,
        "protocol_id": str(protocol_id),
        "schemas": [
            {"id": str(version_id), "version": version.version, "json_schema": schema}
        ],
        "records": [],
        "fields": [],
    }
    rows, uploads = [(ProtocolVersion, version_id, version)], []
    for index in range(count):
        body = f"value\n{index + 1}\n".encode()
        uploaded = AiralogyFile(
            id=uuid4(),
            filename="data.csv",
            protocol_id=protocol_id,
            project_id=project_id,
            user_id=user.id,
            storage_backend="minio",
            size_bytes=len(body),
            checksum_sha256=hashlib.sha256(body).hexdigest(),
        )

        async def stream(content=body):
            yield content

        uploaded.get_file_with_stream = stream
        record = SimpleNamespace(
            id=uuid4(),
            version=1,
            protocol_id=protocol_id,
            protocol_version=version.version,
            user_id=user.id,
            hash=f"hash-{index}",
            deleted_at=None,
            data={"var": {"upload": uploaded.airalogy_id}},
        )
        snapshot["records"].append(
            {
                "record_id": str(record.id),
                "record_version": 1,
                "record_hash": record.hash,
                "protocol_version": record.protocol_version,
                "data": copy.deepcopy(record.data),
            }
        )
        rows.extend(
            [(Record, (record.id, 1), record), (AiralogyFile, uploaded.id, uploaded)]
        )
        uploads.append(uploaded)
    db = Session(rows)
    scopes = AsyncMock(
        return_value=(
            SimpleNamespace(id=protocol_id),
            SimpleNamespace(id=project_id),
            False,
        )
    )
    monkeypatch.setattr(record_analyses, "analysis_scope", scopes)
    acl = AsyncMock(return_value=None)
    monkeypatch.setattr(files, "authorized_file", acl)
    declarations = [{"input_id": "measurements", "field_path": ["var", "upload"]}]
    return SimpleNamespace(
        db=db,
        user=user,
        approver=approver,
        snapshot=snapshot,
        version=version,
        uploads=uploads,
        declarations=declarations,
        acl=acl,
        scopes=scopes,
    )


def run(value):
    return asyncio.run(value)


def test_no_attachment_operations_do_not_query_or_change_old_analysis(monkeypatch):
    db = Session()
    assert run(files.preview_input_files(db, {}, [], None)) is None
    assert (
        run(
            files.materialize_input_files(
                db, run=None, job=None, recipe={}, expected=None, user=None
            )
        )
        is None
    )
    run(files.authorize_input_files(db, SimpleNamespace(recipe={}), None))
    run(files.authorize_preview_input_files(db, {}, None, None))
    db.get.assert_not_awaited()
    db.scalars.assert_not_awaited()
    db.add.assert_not_called()


@pytest.mark.parametrize("wrapper", ["vars", "research_variable", "record"])
def test_file_catalog_uses_local_schema_not_string_display_catalog(
    monkeypatch, wrapper
):
    context = case(monkeypatch)
    variables = context.version.json_schema["vars"]
    variables["properties"]["plain"] = {"type": "string"}
    variables["$defs"] = {
        "File": {
            "type": "string",
            "airalogy_type": "FileIdCSV",
            "file_extension": "csv",
        }
    }
    variables["properties"]["upload"] = {
        "anyOf": [{"$ref": "#/$defs/File"}, {"type": "null"}]
    }
    schema = (
        {wrapper: variables}
        if wrapper != "record"
        else {
            "type": "object",
            "properties": {"var": variables},
            "$defs": variables["$defs"],
        }
    )
    context.snapshot["schemas"][0]["json_schema"] = schema
    context.snapshot["fields"] = [{"key": "plain", "type": "file"}]
    assert files.attachment_field_catalog(context.snapshot) == [
        {
            "field_path": ["var", "upload"],
            "title": "upload",
            "file_extensions": ["csv"],
            "nullable": True,
        }
    ]


@pytest.mark.parametrize(
    "field",
    [
        {"type": "string"},
        {"type": "array", "items": {"type": "string", "airalogy_type": "FileId"}},
        {"anyOf": [{"type": "string", "airalogy_type": "FileId"}, {"type": "string"}]},
        {"$ref": "https://example.test/private-schema"},
        {
            "type": "string",
            "airalogy_type": "FileId",
            "$id": "https://example.test/scope",
        },
    ],
)
def test_unsupported_or_untyped_attachment_fields_are_not_inferred(monkeypatch, field):
    context = case(monkeypatch, field=field)
    assert files.attachment_field_catalog(context.snapshot) == []
    with pytest.raises(HTTPException):
        run(
            files.preview_input_files(
                context.db, context.snapshot, context.declarations, context.user
            )
        )


def test_catalog_requires_every_exact_record_schema(monkeypatch):
    context = case(monkeypatch)
    old = copy.deepcopy(context.snapshot["schemas"][0])
    old["version"] = "0.9"
    old["json_schema"]["vars"]["properties"]["upload"] = {"type": "string"}
    context.snapshot["schemas"].append(old)
    context.snapshot["records"][0]["protocol_version"] = "0.9"
    assert files.attachment_field_catalog(context.snapshot) == []


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "https://example.test/file.csv",
        123,
        True,
        ["file"],
        {"file": "value"},
        "airalogy.id.file.INVALID.csv",
    ],
)
def test_every_record_requires_one_canonical_file_without_sample_dropping(
    monkeypatch, value
):
    context = case(monkeypatch)
    context.snapshot["records"][1]["data"]["var"]["upload"] = value
    with pytest.raises(HTTPException) as failure:
        run(
            files.preview_input_files(
                context.db, context.snapshot, context.declarations, context.user
            )
        )
    assert failure.value.status_code == 409
    context.db.add.assert_not_called()


def test_preview_is_read_only_full_cartesian_mapping_and_contains_no_storage(
    monkeypatch,
):
    context = case(monkeypatch)
    source_before = copy.deepcopy(context.snapshot)
    envelope = run(
        files.preview_input_files(
            context.db,
            context.snapshot,
            context.declarations,
            context.user,
            other_readers=(context.approver,),
        )
    )
    assert envelope["count"] == 2
    assert envelope["total_bytes"] == sum(x.size_bytes for x in context.uploads)
    assert {x["record_id"] for x in envelope["files"]} == {
        x["record_id"] for x in context.snapshot["records"]
    }
    assert len({x["mount_name"] for x in envelope["files"]}) == 2
    payload = files.manifest_bytes(envelope)
    assert (
        hashlib.sha256(payload).hexdigest() == envelope["manifest"]["checksum_sha256"]
    )
    assert len(payload) == envelope["manifest"]["byte_size"]
    assert (
        b"storage" not in payload
        and b"object_key" not in payload
        and b"http" not in payload
    )
    envelope["private"] = {"storage_object_key": "must-not-expose"}
    assert files.manifest_bytes(envelope) == payload
    assert context.snapshot == source_before
    assert context.acl.await_count == 4
    context.db.add.assert_not_called()
    context.db.flush.assert_not_awaited()


@pytest.mark.parametrize(
    "mutate",
    ["external", "bytes", "filename", "record_data", "record_hash", "schema", "revoke"],
)
def test_changed_or_revoked_source_cannot_pass_preview(monkeypatch, mutate):
    context = case(monkeypatch)
    source = context.uploads[0]
    record = next(
        value for (model, _), value in context.db.rows.items() if model is Record
    )
    if mutate == "external":
        source.external_uri = "https://example.test/file.csv"
    elif mutate == "bytes":
        source.checksum_sha256 = "a" * 64
    elif mutate == "filename":
        source.filename = "../data.csv"
    elif mutate == "record_data":
        record.data = {"var": {"upload": context.uploads[1].airalogy_id}}
    elif mutate == "record_hash":
        record.hash = "tampered"
    elif mutate == "schema":
        context.version.json_schema = {"vars": {"properties": {}}}
    else:
        context.acl.side_effect = HTTPException(403, "permission revoked")
    with pytest.raises((HTTPException, ValueError)):
        run(
            files.preview_input_files(
                context.db, context.snapshot, context.declarations, context.user
            )
        )
    context.db.add.assert_not_called()


def test_own_only_permission_does_not_expand_through_an_attachment(monkeypatch):
    context = case(monkeypatch)
    context.scopes.return_value = (object(), object(), True)
    with pytest.raises(HTTPException) as failure:
        run(
            files.preview_input_files(
                context.db,
                context.snapshot,
                context.declarations,
                context.user,
                other_readers=(context.approver,),
            )
        )
    assert failure.value.status_code == 403
    context.acl.assert_not_awaited()


def test_file_count_is_bounded_before_any_storage_or_database_read(monkeypatch):
    context = case(monkeypatch, count=31)
    with pytest.raises(HTTPException) as failure:
        run(
            files.preview_input_files(
                context.db, context.snapshot, context.declarations, context.user
            )
        )
    assert failure.value.status_code == 413
    context.db.get.assert_not_awaited()


def test_per_file_and_total_limits_count_repeated_physical_files(monkeypatch):
    context = case(monkeypatch)
    monkeypatch.setattr(files, "MAX_ANALYSIS_FILE_BYTES", 1)
    with pytest.raises(HTTPException) as failure:
        run(
            files.preview_input_files(
                context.db, context.snapshot, context.declarations, context.user
            )
        )
    assert failure.value.status_code == 413
    monkeypatch.setattr(files, "MAX_ANALYSIS_FILE_BYTES", 100)
    monkeypatch.setattr(
        files, "MAX_ANALYSIS_TOTAL_FILE_BYTES", context.uploads[0].size_bytes
    )
    with pytest.raises(HTTPException) as failure:
        run(
            files.preview_input_files(
                context.db, context.snapshot, context.declarations, context.user
            )
        )
    assert failure.value.status_code == 413


def materialization_case(monkeypatch):
    context = case(monkeypatch)
    analysis = SimpleNamespace(
        id=uuid4(),
        source_snapshot=context.snapshot,
        recipe={"input_files": context.declarations},
    )
    job = SimpleNamespace(id=uuid4())
    first = ResearchComputeJobInput(
        id=uuid4(),
        compute_job_id=job.id,
        analysis_run_id=analysis.id,
        mount_name="records.json",
        position=1,
    )
    context.db._add(first)

    async def seal(db, source):
        blob = SimpleNamespace(
            id=uuid4(),
            size_bytes=source.size_bytes,
            checksum_sha256=source.checksum_sha256,
            content_type=source.content_type,
            storage_backend="minio",
            storage_namespace="private",
            storage_object_key=f"sealed/{source.id}",
        )
        db.rows[ResearchFileBlob, blob.id] = blob
        return blob

    monkeypatch.setattr(files, "seal_legacy_file", AsyncMock(side_effect=seal))
    monkeypatch.setattr(
        files,
        "verified_blob_spool",
        AsyncMock(side_effect=lambda *a, **kw: io_buffer()),
    )
    return context, analysis, job


def io_buffer():
    import io

    return io.BytesIO(b"value\n1\n")


def test_materialize_seals_receipts_and_each_logical_input_without_dataassets(
    monkeypatch,
):
    context, analysis, job = materialization_case(monkeypatch)

    async def exercise():
        envelope = await files.preview_input_files(
            context.db, context.snapshot, context.declarations, context.user
        )
        actual = await files.materialize_input_files(
            context.db,
            run=analysis,
            job=job,
            recipe=analysis.recipe,
            expected=envelope,
            user=context.user,
        )
        assert actual == envelope
        context.db.rows[AnalysisCompute, analysis.id] = SimpleNamespace(
            input_file_manifest=actual
        )
        inputs = [
            row
            for row in context.db.written
            if isinstance(row, ResearchComputeJobInput)
        ]
        assert [row.position for row in inputs] == [1, 2, 3, 4]
        assert inputs[1].mount_name == "attachments.json"
        assert all(
            row.data_asset_id is None and row.data_asset_version_id is None
            for row in inputs
        )
        await files.verify_input_files(
            context.db, run=analysis, job=job, inputs=inputs, envelope=actual
        )
        await files.authorize_input_files(context.db, analysis, context.user)
        for input_row in inputs[2:]:
            receipt, blob = await files.sealed_input_file(
                context.db, analysis, input_row
            )
            assert receipt.snapshot["checksum_sha256"] == blob.checksum_sha256
        context.acl.side_effect = HTTPException(403, "revoked")
        with pytest.raises(HTTPException) as failure:
            await files.authorize_input_files(context.db, analysis, context.user)
        assert failure.value.status_code == 403
        assert files._ACTIVE_ANALYSES.get() == frozenset()

    run(exercise())


def test_stale_preview_does_not_create_inputs_or_blobs(monkeypatch):
    context, analysis, job = materialization_case(monkeypatch)
    envelope = run(
        files.preview_input_files(
            context.db, context.snapshot, context.declarations, context.user
        )
    )
    envelope["files"][0]["checksum_sha256"] = "a" * 64
    before = len(context.db.written)
    with pytest.raises(HTTPException):
        run(
            files.materialize_input_files(
                context.db,
                run=analysis,
                job=job,
                recipe=analysis.recipe,
                expected=envelope,
                user=context.user,
            )
        )
    assert len(context.db.written) == before
    files.seal_legacy_file.assert_not_awaited()


@pytest.mark.parametrize("mutate", ["receipt", "blob", "input", "manifest", "missing"])
def test_sealed_input_integrity_is_checked_again(monkeypatch, mutate):
    context, analysis, job = materialization_case(monkeypatch)

    async def exercise():
        expected = await files.preview_input_files(
            context.db, context.snapshot, context.declarations, context.user
        )
        envelope = await files.materialize_input_files(
            context.db,
            run=analysis,
            job=job,
            recipe=analysis.recipe,
            expected=expected,
            user=context.user,
        )
        inputs = [
            row
            for row in context.db.written
            if isinstance(row, ResearchComputeJobInput)
        ]
        receipt, blob = await files.sealed_input_file(context.db, analysis, inputs[2])
        if mutate == "receipt":
            receipt.snapshot = {**receipt.snapshot, "byte_size": 5}
        elif mutate == "blob":
            blob.storage_object_key = "changed"
        elif mutate == "input":
            inputs[2].mount_name = "other.csv"
        elif mutate == "manifest":
            envelope["total_bytes"] += 1
        else:
            inputs.pop()
        with pytest.raises(HTTPException):
            await files.verify_input_files(
                context.db, run=analysis, job=job, inputs=inputs, envelope=envelope
            )

    run(exercise())


def test_alias_uses_existing_authorized_blob_without_ordinary_storage(monkeypatch):
    context = case(monkeypatch, count=1)
    source = context.uploads[0]
    source.storage_backend = "workflow_reference"
    blob = SimpleNamespace(
        size_bytes=source.size_bytes, checksum_sha256=source.checksum_sha256
    )
    context.acl.return_value = (SimpleNamespace(digest="a" * 64), source, blob)
    monkeypatch.setattr(
        files,
        "verified_blob_spool",
        AsyncMock(side_effect=lambda *a, **kw: io_buffer()),
    )
    source.get_file_with_stream = Mock(
        side_effect=AssertionError("alias must not use raw storage")
    )
    envelope = run(
        files.preview_input_files(
            context.db, context.snapshot, context.declarations, context.user
        )
    )
    assert envelope["count"] == 1
    files.verified_blob_spool.assert_awaited_once()


@pytest.mark.parametrize("kind", ["managed", "alias"])
@pytest.mark.parametrize("filename", ["fake.pdf", "../private/unsafe.csv"])
def test_file_header_errors_are_safe_business_errors_for_both_storage_kinds(
    monkeypatch, kind, filename
):
    context = case(monkeypatch, count=1)
    source = context.uploads[0]
    source.filename = filename
    binding = None
    spool = io_buffer()
    if kind == "alias":
        binding = (SimpleNamespace(), source, SimpleNamespace())
        monkeypatch.setattr(files, "verified_blob_spool", AsyncMock(return_value=spool))
    with pytest.raises(AnalysisError) as failure:
        run(files._file_bytes(source, binding))
    assert "unsafe filename" in str(failure.value)
    assert filename not in str(failure.value)
    assert "private/" not in str(failure.value)
    if kind == "alias":
        assert spool.closed


def test_attachment_header_failure_maps_to_preview_422_without_commit(monkeypatch):
    from app.routers import analysis_compute as api

    context = case(monkeypatch, count=1)
    source = context.uploads[0]
    source.filename = "fake.pdf"

    async def invalid_preview(*args, **kwargs):
        await files._file_bytes(source, None)

    monkeypatch.setattr(api, "preview_compute", invalid_preview)
    db = SimpleNamespace(commit=AsyncMock())
    with pytest.raises(HTTPException) as failure:
        run(api.preview_analysis_compute(None, db, context.user, Response()))
    assert failure.value.status_code == 422
    assert "fake.pdf" not in failure.value.detail
    db.commit.assert_not_awaited()


def test_preview_reader_guard_rechecks_metadata_and_acl_without_reading_bytes(
    monkeypatch,
):
    context = case(monkeypatch)
    envelope = run(
        files.preview_input_files(
            context.db, context.snapshot, context.declarations, context.user
        )
    )
    for source in context.uploads:
        source.get_file_with_stream = Mock(
            side_effect=AssertionError("no byte I/O on read authorization")
        )
    run(
        files.authorize_preview_input_files(
            context.db, context.snapshot, envelope, context.approver
        )
    )
    context.uploads[0].filename = "changed.csv"
    with pytest.raises(HTTPException):
        run(
            files.authorize_preview_input_files(
                context.db, context.snapshot, envelope, context.approver
            )
        )


def test_migration_protects_receipts_sources_manifest_and_downgrade(monkeypatch):
    migration = import_module("migrations.versions.0069_analysis_compute_input_files")
    assert migration.down_revision == "0068_workflow_file_bindings"
    assert len(migration.revision) <= 32
    sql = []
    monkeypatch.setattr(migration.op, "add_column", Mock())
    monkeypatch.setattr(migration.op, "create_table", Mock())
    monkeypatch.setattr(migration.op, "create_index", Mock())
    monkeypatch.setattr(
        migration.op, "execute", lambda statement: sql.append(statement)
    )
    migration.upgrade()
    assert any(
        "immutable_analysis_compute_input_files" in statement for statement in sql
    )
    assert any("protect_analysis_attachment_manifest" in statement for statement in sql)
    assert any("research_file_blobs" in statement for statement in sql)
    connection = SimpleNamespace(execute=Mock(), scalar=Mock(return_value=True))
    monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
    with pytest.raises(RuntimeError, match="Cannot downgrade"):
        migration.downgrade()
    assert "LOCK TABLE" in str(connection.execute.call_args.args[0])


def test_lab_cleanup_removes_only_exact_lab_receipts_not_shared_blobs(monkeypatch):
    from app.libs.lab_force_delete import _delete_lab_analysis_input_file_references

    lab_id = uuid4()
    db = SimpleNamespace(scalar=AsyncMock(return_value=None), execute=AsyncMock())
    run(_delete_lab_analysis_input_file_references(db, lab_id))
    statement = str(
        db.execute.call_args.args[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert statement.startswith("DELETE FROM analysis_compute_input_files")
    assert str(lab_id) in statement
    assert "research_file_blobs" not in statement
    db.scalar.return_value = uuid4()
    db.execute.reset_mock()
    with pytest.raises(ValueError, match="Another Lab"):
        run(_delete_lab_analysis_input_file_references(db, lab_id))
    db.execute.assert_not_awaited()
