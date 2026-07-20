import asyncio
import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from airalogy.record.hash import get_data_sha1
from app.routers import aira_imports
from app.routers.aira_imports import (
    AiraArchiveImporter,
    PendingRecord,
    _filename_from_file_ref,
    _record_protocol_uid,
    _record_protocol_version,
    _record_uuid,
    _record_version,
    _replace_record_value,
    _set_record_field_path,
)
from app.models.protocol_version import ProtocolMetadata


def test_record_identity_accepts_airalogy_record_id():
    payload = {
        "airalogy_record_id": "airalogy.id.record.00000000-0000-0000-0000-000000000001.v.3"
    }

    assert _record_uuid(payload, {}) == uuid.UUID(
        "00000000-0000-0000-0000-000000000001"
    )
    assert _record_version(payload, {}) == 3


def test_record_identity_prefers_payload_record_id():
    payload = {
        "record_id": "00000000-0000-0000-0000-000000000002",
        "airalogy_record_id": "airalogy.id.record.00000000-0000-0000-0000-000000000001.v.3",
        "record_version": 2,
    }

    assert _record_uuid(payload, {}) == uuid.UUID(
        "00000000-0000-0000-0000-000000000002"
    )
    assert _record_version(payload, {}) == 2


def test_record_protocol_identity_accepts_airalogy_protocol_id():
    payload = {
        "metadata": {
            "airalogy_protocol_id": "airalogy.id.lab.lab_a.project.project_a.protocol.meeting_notes.v.1.2.3"
        }
    }

    assert _record_protocol_uid(payload, {}) == "meeting_notes"
    assert _record_protocol_version(payload, {}) == "1.2.3"


def test_record_protocol_identity_prefers_explicit_protocol_id():
    payload = {
        "metadata": {
            "protocol_id": "explicit_protocol",
            "protocol_version": "2.0.0",
            "airalogy_protocol_id": "airalogy.id.lab.lab_a.project.project_a.protocol.meeting_notes.v.1.2.3",
        }
    }

    assert _record_protocol_uid(payload, {}) == "explicit_protocol"
    assert _record_protocol_version(payload, {}) == "2.0.0"


def test_protocol_metadata_accepts_descriptive_snake_case_id():
    metadata = ProtocolMetadata(
        id="participant_rehabilitation_record",
        version="1.0.0",
    )

    assert metadata.id == "participant_rehabilitation_record"


def test_set_record_field_path_handles_data_prefix():
    data = {"var": {"sample_name": "old"}}

    _set_record_field_path(
        data,
        "data.var.sample_file",
        "airalogy.id.file.00000000-0000-0000-0000-000000000003.txt",
    )

    assert data == {
        "var": {
            "sample_name": "old",
            "sample_file": "airalogy.id.file.00000000-0000-0000-0000-000000000003.txt",
        }
    }


def test_replace_record_value_rewrites_nested_file_ids():
    old = "airalogy.id.file.00000000-0000-0000-0000-000000000001.txt"
    new = "airalogy.id.file.00000000-0000-0000-0000-000000000002.txt"
    data = {
        "var": {
            "main": old,
            "table": [{"file": old}, {"file": "unchanged"}],
        }
    }

    assert _replace_record_value(data, old, new) == {
        "var": {
            "main": new,
            "table": [{"file": new}, {"file": "unchanged"}],
        }
    }


def test_filename_from_file_ref_uses_source_uri_basename():
    assert (
        _filename_from_file_ref({"source_uri": "oss://bucket/path/sample-note.txt"})
        == "sample-note.txt"
    )


def test_create_records_restores_matching_record_with_restored_protocol(monkeypatch):
    protocol_id = uuid.uuid4()
    record_id = uuid.uuid4()
    data = {"step": {}, "var": {"sample": "A"}, "check": {}}
    protocol = SimpleNamespace(id=protocol_id, uid="test_protocol")
    protocol_version = SimpleNamespace(id=uuid.uuid4(), version="1.0.0")
    pending_record = PendingRecord(
        archive_path="records/record.json",
        payload={},
        manifest_entry={},
        protocol=protocol,
        protocol_version=protocol_version,
        record_id=record_id,
        record_version=1,
        data=data,
        report="Existing report",
    )
    existing_record = SimpleNamespace(
        id=record_id,
        version=1,
        protocol_id=protocol_id,
        protocol_version="1.0.0",
        hash=get_data_sha1({"data": data}),
        report="Existing report",
        number=7,
        deleted_at=datetime.now(),
    )
    monkeypatch.setattr(
        aira_imports.Record,
        "find_by",
        AsyncMock(return_value=existing_record),
    )
    importer = AiraArchiveImporter(
        db_session=SimpleNamespace(),
        project=SimpleNamespace(),
        lab=SimpleNamespace(),
        user=SimpleNamespace(),
        background_tasks=SimpleNamespace(),
    )
    importer.restored_protocol_ids.add(protocol_id)

    asyncio.run(importer._create_records([pending_record]))

    assert existing_record.deleted_at is None
    assert importer.record_results == [
        {
            "id": str(record_id),
            "version": 1,
            "protocol_id": str(protocol_id),
            "protocol_uid": "test_protocol",
            "protocol_version": "1.0.0",
            "number": 7,
            "restored": True,
        }
    ]
