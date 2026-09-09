import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
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
from app.services.instrument_activations import file_delivery_block_reason


def test_existing_file_activation_cannot_bypass_runtime_gate(monkeypatch):
    import app.services.instrument_activations as service

    identity = uuid4()
    binding = SimpleNamespace(
        id=identity,
        gateway_id=identity,
        resource_id=identity,
        lab_id=identity,
        descriptor={},
        receipt={},
    )
    qualification = SimpleNamespace(binding_id=identity, confirmation_digest="a" * 64)
    row = SimpleNamespace(
        revoked_at=None,
        binding_id=identity,
        qualification_id=identity,
        gateway_id=identity,
        resource_id=identity,
        lab_id=identity,
        plan={
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "descriptor": {},
            "receipt": {},
            "qualification_digest": "a" * 64,
            "commands": [
                {"contract": {"outputs": [{"name": "raw.csv", "required": False}]}}
            ],
        },
    )

    class Database:
        async def get(self, model, _id):
            return (
                binding if model is service.InstrumentDeviceBinding else qualification
            )

    monkeypatch.setattr(
        service, "qualification_state", AsyncMock(return_value="qualified")
    )
    assert "raw files cannot be activated" in asyncio.run(
        service.activation_invalid_reason(Database(), row)
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


def test_declared_optional_files_are_not_silently_ignored_either():
    assert file_delivery_block_reason({"outputs": []}) is None
    for required in (True, False):
        assert "raw files cannot be activated" in file_delivery_block_reason(
            {
                "outputs": [
                    {
                        "name": "raw.csv",
                        "media_type": "text/csv",
                        "max_bytes": 1024,
                        "required": required,
                    }
                ]
            }
        )


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
