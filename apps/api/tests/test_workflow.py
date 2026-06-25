import uuid

from app.routers.workflow import (
    _extract_airalogy_record_id,
    _logic_as_text,
    _parse_record_airalogy_id,
    _path_status_after_step,
)


def test_path_status_after_strategy_step():
    assert (
        _path_status_after_step(
            "waiting_for_research_strategy",
            {"data": {"researchable": True}},
        )
        == "waiting_for_next_protocol"
    )
    assert (
        _path_status_after_step(
            "waiting_for_research_strategy",
            {"data": {"researchable": False}},
        )
        == "end_after_generating_research_strategy"
    )


def test_path_status_after_next_protocol_step():
    assert (
        _path_status_after_step(
            "waiting_for_next_protocol",
            {"data": {"end_path": False}},
        )
        == "waiting_for_initial_values_for_fields_in_next_protocol"
    )
    assert (
        _path_status_after_step(
            "waiting_for_next_protocol",
            {"data": {"end_path": True}},
        )
        == "end_after_selecting_next_protocol"
    )


def test_extract_airalogy_record_id_from_record_payload():
    record_id = "airalogy.id.record.00000000-0000-0000-0000-000000000000.v.2"
    assert _extract_airalogy_record_id({"airalogy_record_id": record_id}) == record_id
    assert _extract_airalogy_record_id({"data": {"airalogy_id": record_id}}) == record_id


def test_parse_record_airalogy_id():
    record_uuid, version = _parse_record_airalogy_id(
        "airalogy.id.record.00000000-0000-0000-0000-000000000000.v.2"
    )
    assert record_uuid == uuid.UUID("00000000-0000-0000-0000-000000000000")
    assert version == 2


def test_logic_as_text():
    assert _logic_as_text(["first", "", "second"]) == "first\nsecond"
    assert _logic_as_text("single") == "single"
