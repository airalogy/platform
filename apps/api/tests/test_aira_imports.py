import uuid

from app.routers.aira_imports import (
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
