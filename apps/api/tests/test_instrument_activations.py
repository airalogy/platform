from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.routers.instrument_activations import ActivationDraft
from app.services.access_control import ROLE_CAPABILITIES
from app.services.instrument_activation_contract import (
    SCHEMA,
    activation_digest,
    validate_activation_pin,
)


def draft():
    return {
        "id": str(uuid4()),
        "qualification_id": str(uuid4()),
        "commands": ["fixture.read@1.0.0"],
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "reason": "Synthetic independent activation",
        "activation_confirmed": True,
    }


@pytest.mark.parametrize(
    "change",
    [
        {"activation_confirmed": False},
        {"activation_confirmed": 1},
        {"commands": []},
        {"commands": ["fixture.read@1.0.0"] * 2},
        {"expires_at": "2026-09-09T00:00:00"},
        {"hardware_authorized": True},
        {"reason": " "},
    ],
)
def test_activation_is_explicit_bounded_and_typed(change):
    with pytest.raises(ValidationError):
        ActivationDraft.model_validate({**draft(), **change})


def test_activation_capability_is_separate_from_equipment_use():
    for role in ("lab_owner", "lab_admin"):
        assert "equipment.activate" in ROLE_CAPABILITIES[role]
    for role in ("resource_custodian", "resource_operator"):
        assert "equipment.activate" not in ROLE_CAPABILITIES[role]


def test_pin_binds_exact_installation_and_disallows_embedded_code_or_path():
    value = {
        "schema": SCHEMA,
        "id": str(uuid4()),
        "binding_id": str(uuid4()),
        "qualification_id": str(uuid4()),
        "authorization_digest": "a" * 64,
        "installation_id": "b" * 64,
        "target_digest": activation_digest({"target": "synthetic"}),
    }
    assert validate_activation_pin(value) == value
    for change in (
        {"code": "print(1)"},
        {"path": "/tmp/a"},
        {"id": "not-a-uuid"},
        {"installation_id": "../other"},
        {"target_digest": "z" * 64},
    ):
        with pytest.raises(ValueError):
            validate_activation_pin({**value, **change})
