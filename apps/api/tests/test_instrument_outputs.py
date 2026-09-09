"""Small intake boundary checks; persistence/ACL coverage is in real integration."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routers.instrument_outputs import AssociationDraft, CaptureRequest
from app.routers.research_instrument_jobs import GatewayLease
from app.services.instrument_outputs import authorize_intake
from app.services.research_runtime import evaluate_research_action_policy


def test_file_capability_is_explicit_and_versioned():
    assert GatewayLease().file_delivery_version is None
    assert GatewayLease(
        file_delivery_version="airalogy.instrument-output-plan.v1"
    ).file_delivery_version
    for value in (True, 1, "v2", ""):
        with pytest.raises(ValidationError):
            GatewayLease(file_delivery_version=value)


@pytest.mark.parametrize("version", [True, 0, -1, "1", 1.5])
def test_record_association_requires_an_exact_integer_version(version):
    with pytest.raises(ValidationError):
        AssociationDraft(id=uuid4(), record_id=uuid4(), record_version=version)


def test_receiving_scope_is_not_client_controlled():
    with pytest.raises(ValidationError):
        CaptureRequest(capture={}, project_id=uuid4())
    with pytest.raises(ValidationError):
        AssociationDraft(
            id=uuid4(), record_id=uuid4(), record_version=1, overwrite_record=True
        )
    with pytest.raises(HTTPException) as denied:
        asyncio.run(authorize_intake(None, None, SimpleNamespace()))
    assert denied.value.status_code == 403


def test_required_file_preview_cannot_be_skipped_by_autopilot(monkeypatch):
    import app.services.research_autonomy_policy as policy

    monkeypatch.setattr(
        policy,
        "evaluate_automatic_action",
        lambda **_kwargs: ("allow", "synthetic broad policy"),
    )
    for level in ("assisted", "bounded_autopilot", "autonomous_within_policy"):
        result = evaluate_research_action_policy(
            autonomy_level=level,
            source="aira",
            executor_type="instrument",
            requirements={"approval_policy": "always_ask"},
        )
        assert result[0] == "ask"
