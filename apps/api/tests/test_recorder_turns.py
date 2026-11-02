import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services import recorder_turns as recorder


def target(**overrides):
    return recorder.RecorderTarget(
        form_id="example_form_0001",
        request_id="example_turn_0001",
        version="1.0",
        **overrides,
    )


def version():
    return SimpleNamespace(
        id=uuid4(),
        aimd="Synthetic",
        assigners={"output": {"mode": "auto"}},
        json_schema={
            "vars": {
                "properties": {
                    "temperature": {
                        "type": "number",
                        "minimum": -5,
                        "maximum": 100,
                        "unit": "°C",
                    },
                    "sample_id": {"type": "string"},
                    "used": {"type": "boolean"},
                    "output": {"type": "number"},
                    "attachment": {"type": "string", "airalogy_type": "FileId"},
                    "sample": {"$ref": "#/$defs/Sample"},
                }
            }
        },
    )


@pytest.mark.parametrize(
    ("spec", "raw", "source", "expected"),
    [
        ({"type": "number", "maximum": 10}, 11, "11", None),
        ({"type": "integer"}, 2, "2.1", None),
        ({"type": "integer"}, 0, "0", 0),
        ({"type": "string"}, "001", "001", "001"),
        ({"type": "string", "enum": ["blue"]}, "red", "red", None),
        ({"type": "boolean"}, False, "否", False),
        ({"type": "string", "format": "date"}, "2024-02-30", "2024-02-30", None),
    ],
)
def test_field_value_requires_source_and_schema(spec, raw, source, expected):
    assert recorder.grounded_value(spec, raw, source) == expected


def test_simulation_skips_non_scalars_derived_fields_and_filled_values(monkeypatch):
    response = {
        "intent": "simulate",
        "answer": "Preview",
        "references": [],
        "operations": [],
    }
    request = AsyncMock(return_value=response)
    monkeypatch.setattr(recorder, "json_request", request)
    chat = SimpleNamespace(model={"name": "test"}, context={}, messages=[])
    _, _, proposal = asyncio.run(
        recorder.plan_recorder_turn(
            chat, version(), target(filled=["sample_id"]), "simulate", None
        )
    )
    assert "sample_id" not in proposal["values"] and proposal["values"]["used"] is False
    assert set(proposal["skipped"]) == {"output", "attachment", "sample"}
    assert request.await_args.args[0] == "endpoints/chat/field_input/turn"


def test_untrusted_unknown_duplicate_or_ungrounded_slots_cannot_update(monkeypatch):
    def op(key, value, source):
        return {
            "operation": "update",
            "rf_name": key,
            "rf_value": value,
            "source": source,
        }

    response = {
        "intent": "fill",
        "answer": "",
        "references": ["temperature"],
        "operations": [
            op("sample_id", "001", "001"),
            op("temperature", 3, "3"),
            op("temperature", 4, "4"),
            op("output", 3, "3"),
            op("used", True, "yes"),
            op("invented", "001", "001"),
        ],
    }
    monkeypatch.setattr(recorder, "json_request", AsyncMock(return_value=response))
    chat = SimpleNamespace(model={"name": "test"}, context={}, messages=[])
    _, _, proposal = asyncio.run(
        recorder.plan_recorder_turn(chat, version(), target(), "Use 001, 3 or 4", None)
    )
    assert proposal["values"] == {"sample_id": "001"}
    assert set(proposal["skipped"]) == {"temperature", "output", "used", "invented"}


def test_revision_authority_and_exact_version(monkeypatch):
    actor = SimpleNamespace(id=uuid4())
    db = SimpleNamespace(
        scalar=AsyncMock(
            return_value=SimpleNamespace(user_id=uuid4(), protocol_version="1.0")
        )
    )
    check = AsyncMock()
    monkeypatch.setattr(recorder, "check_user_permission", check)
    args = db, actor, object(), SimpleNamespace(id=uuid4()), target(record_id=uuid4())
    with pytest.raises(HTTPException) as error:
        asyncio.run(recorder.recorder_scope(*args))
    assert error.value.status_code == 403 and not check.called
    db.scalar.return_value.user_id = actor.id
    db.scalar.return_value.protocol_version = "2.0"
    with pytest.raises(HTTPException) as error:
        asyncio.run(recorder.recorder_scope(*args))
    assert error.value.status_code == 409


def test_numeric_units_are_checked_without_silent_conversion():
    spec = {"type": "number", "unit": "min"}
    assert recorder.matching_unit("刚才的时长填20分钟", "20", spec)
    assert not recorder.matching_unit("实际是2 hours", "2", spec)
    assert not recorder.matching_unit("use 2 mm", "2", {"type": "number", "unit": "mM"})


def test_number_substrings_are_not_observations():
    assert not recorder.matching_unit("set it to -31", "1", {"type": "integer"})
    assert not recorder.matching_unit("set it to -31", "31", {"type": "integer"})
