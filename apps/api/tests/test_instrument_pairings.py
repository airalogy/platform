import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routers import instrument_pairings as router
from app.services.research_runtime import utcnow


def context():
    gateway = SimpleNamespace(
        id=uuid4(),
        lab_id=uuid4(),
        name="Synthetic",
        enabled=False,
        revision=1,
        revoked_at=None,
        token_digest="a" * 64,
    )
    row = SimpleNamespace(
        id=uuid4(),
        gateway_id=gateway.id,
        gateway_revision=1,
        state="pending",
        expires_at=utcnow() + timedelta(minutes=10),
        client_name=None,
        credential_digest=None,
    )
    return row, gateway


def test_state_fails_closed_on_expiry_change_and_rotation():
    row, gateway = context()
    assert router._snapshot(row, gateway)["state"] == "pending"
    gateway.enabled = True
    assert router._snapshot(row, gateway)["state"] == "stale"
    gateway.enabled = False
    row.expires_at = utcnow() - timedelta(seconds=1)
    with pytest.raises(HTTPException):
        router._assert_pending(row, gateway)
    row.state = "confirmed"
    row.credential_digest = gateway.token_digest
    assert router._snapshot(row, gateway)["state"] == "confirmed"
    gateway.token_digest = "b" * 64
    assert router._snapshot(row, gateway)["state"] == "superseded"


def test_fingerprint_binds_local_identity_without_exposing_key():
    row, gateway = context()
    row.credential_digest = "c" * 64
    row.client_name = "Local reader"
    snapshot = router._snapshot(row, gateway)
    assert "credential_digest" not in snapshot
    assert "code_digest" not in snapshot
    initial = snapshot["fingerprint"]
    for field, value in [
        ("client_name", "Other"),
        ("credential_digest", "d" * 64),
        ("gateway_id", uuid4()),
        ("id", uuid4()),
    ]:
        old = getattr(row, field)
        setattr(row, field, value)
        assert router._fingerprint(row) != initial
        setattr(row, field, old)


@pytest.mark.parametrize("enabled,count", [(True, 0), (False, 1)])
def test_pairing_cannot_interrupt_enabled_or_active_gateway(enabled, count):
    _row, gateway = context()
    gateway.enabled = enabled
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            router._idle(gateway, SimpleNamespace(scalar=AsyncMock(return_value=count)))
        )
    assert error.value.status_code == 409


def test_preview_binds_actor_and_reason_and_strict_input():
    draft = router.PairingDraft(
        gateway_id=uuid4(), expected_revision=1, reason="Local setup"
    )
    actor = SimpleNamespace(id=uuid4())
    initial = router._create_digest(draft, actor)
    assert router._create_digest(draft, SimpleNamespace(id=uuid4())) != initial
    assert (
        router._create_digest(draft.model_copy(update={"reason": "Different"}), actor)
        != initial
    )
    with pytest.raises(ValidationError):
        router.PairingDraft(
            gateway_id=draft.gateway_id, expected_revision=1, reason="  "
        )
    with pytest.raises(ValidationError):
        router.PairingClaim(
            code="123456",
            gateway_id=uuid4(),
            lab_id=uuid4(),
            client_name="untrusted",
            credential_digest="a" * 64,
            credential_hint="abcdefgh",
        )
