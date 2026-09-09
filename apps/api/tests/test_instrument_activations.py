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


@pytest.mark.parametrize("required", [True, False])
def test_file_job_requires_exact_pinned_intake(monkeypatch, required):
    import app.services.instrument_activations as service
    import app.services.instrument_installations as installations

    identity = uuid4()
    row = SimpleNamespace(
        id=identity,
        plan={
            "commands": [
                {
                    "contract": {
                        "key": "read",
                        "version": "1",
                        "outputs": [
                            {
                                "name": "raw.csv",
                                "media_type": "text/csv",
                                "max_bytes": 1024,
                                "required": required,
                            }
                        ],
                    }
                }
            ],
        },
    )
    pinned = SimpleNamespace(activation_id=identity, pin={"fixture": True})

    class Database:
        async def get(self, model, _id):
            return pinned if model is service.InstrumentJobActivation else None

    monkeypatch.setattr(
        installations,
        "managed_execution_block_reason",
        AsyncMock(return_value="managed"),
    )
    monkeypatch.setattr(
        service, "executable_activation", AsyncMock(return_value=(row, None))
    )
    monkeypatch.setattr(service, "activation_pin", lambda _row: pinned.pin)
    assert "no matching pinned file intake plan" in asyncio.run(
        service.execution_block_reason(
            Database(),
            identity,
            identity,
            SimpleNamespace(command_key="read", command_version="1"),
            SimpleNamespace(id=identity),
        )
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
