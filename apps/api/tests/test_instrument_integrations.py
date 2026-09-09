import asyncio
import copy
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routers import instrument_integrations as router
from app.services.instrument_adapter_contract import example_bundle


def draft(**changes):
    return router.IntegrationDraft(
        **{
            "id": uuid4(),
            "gateway_id": uuid4(),
            "resource_id": uuid4(),
            "goal": "Read synthetic result",
            "bundle": example_bundle(),
            "reason": "Initial draft",
            **changes,
        }
    )


def test_strict_package_cannot_claim_control_or_import_code():
    bundle = example_bundle()
    bundle["package"]["enabled"] = True
    with pytest.raises(ValidationError):
        draft(bundle=bundle)
    with pytest.raises(ValidationError):
        draft(goal="  ")


def test_preview_binds_scope_actor_revision_and_all_content():
    params = draft()
    source = {"gateway_revision": 1, "user_id": "owner"}
    initial = router._preview(params, source)
    assert initial["hardware_authorized"] is False
    assert initial["report"]["simulation_only"] is True
    for changed in ({**source, "gateway_revision": 2}, {**source, "user_id": "other"}):
        assert (
            initial["preview_digest"]
            != router._preview(params, changed)["preview_digest"]
        )
    changed = params.model_copy(update={"reason": "Different review"})
    assert (
        initial["preview_digest"] != router._preview(changed, source)["preview_digest"]
    )


def test_simulation_failure_can_be_saved_for_review_without_authority():
    bundle = example_bundle()
    bundle["scenarios"][0]["observations"][0]["session"] = "locked"
    result = router._preview(draft(bundle=bundle), {})
    assert result["report"]["passed"] is False
    assert result["hardware_authorized"] is False


def test_context_rechecks_management_scope_and_revision(monkeypatch):
    params = draft()
    gateway = SimpleNamespace(id=params.gateway_id, revision=1)
    equipment = SimpleNamespace(id=params.resource_id)
    revision = SimpleNamespace(id=uuid4())
    gateway_check = AsyncMock(return_value=gateway)
    equipment_check = AsyncMock(return_value=(equipment, revision))
    monkeypatch.setattr(router, "_gateway_context", gateway_check)
    monkeypatch.setattr(router, "_equipment_context", equipment_check)
    db = SimpleNamespace(get=AsyncMock(return_value=None))
    user = SimpleNamespace(id=uuid4())
    asyncio.run(router._context(params, user, db, lock=True))
    assert gateway_check.call_args.kwargs["lock"] is True
    equipment_check.assert_awaited_once()
    db.get.return_value = SimpleNamespace(
        gateway_id=uuid4(), resource_id=params.resource_id, revision=1
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(router._context(params, user, db))
    assert error.value.status_code == 404
    db.get.return_value.gateway_id = params.gateway_id
    with pytest.raises(HTTPException) as error:
        asyncio.run(router._context(params, user, db))
    assert error.value.status_code == 409


def test_invalid_preview_never_writes_or_enables_commands(monkeypatch):
    params = router.IntegrationConfirm(**draft().model_dump(), preview_digest="0" * 64)
    monkeypatch.setattr(
        router, "_context", AsyncMock(return_value=(None, None, None, None, {}))
    )
    db = SimpleNamespace(commit=AsyncMock())
    with pytest.raises(HTTPException) as error:
        asyncio.run(router.save_integration(params, SimpleNamespace(id=uuid4()), db))
    assert error.value.status_code == 409
    db.commit.assert_not_awaited()


def test_aira_cannot_invent_target_control_or_authority():
    bundle = example_bundle()
    package = copy.deepcopy(bundle["package"])
    package["source"]["kind"] = "aira"
    assert router.validate_proposal(package, bundle) == package
    for field, value in [
        ("target", {**package["target"], "application": "Other"}),
        ("hardware_authorized", True),
    ]:
        with pytest.raises(ValueError):
            router.validate_proposal({**package, field: value}, bundle)
    package["commands"][0]["steps"][0]["control_id"] = "unknown"
    with pytest.raises(ValueError, match="unobserved"):
        router.validate_proposal(package, bundle)


@pytest.mark.parametrize(
    "enabled,consent,status", [(False, True, 409), (True, False, 422)]
)
def test_aira_disabled_or_without_processing_consent_never_calls_model(
    monkeypatch, enabled, consent, status
):
    params = router.AiraIntegrationRequest(
        **draft().model_dump(), model_processing_consent=consent
    )
    monkeypatch.setattr(router, "config", SimpleNamespace(effective_ai_enabled=enabled))
    monkeypatch.setattr(
        router, "_context", AsyncMock(return_value=(None, None, None, None, {}))
    )
    model = AsyncMock()
    monkeypatch.setattr(router, "aira_structured_proposal", model)
    with pytest.raises(HTTPException) as error:
        asyncio.run(router.draft_with_aira(params, None, None))
    assert error.value.status_code == status
    model.assert_not_awaited()


def test_aira_rechecks_scope_after_generation(monkeypatch):
    params = router.AiraIntegrationRequest(
        **draft().model_dump(), model_processing_consent=True
    )
    package = copy.deepcopy(params.bundle["package"])
    package["source"]["kind"] = "aira"
    gateway = SimpleNamespace(lab_id=uuid4())
    monkeypatch.setattr(
        router,
        "config",
        SimpleNamespace(effective_ai_enabled=True, CHAT_MODEL_FAST="test"),
    )
    monkeypatch.setattr(
        router,
        "_context",
        AsyncMock(
            side_effect=[
                (gateway, None, None, None, {"revision": 1}),
                (gateway, None, None, None, {"revision": 2}),
            ]
        ),
    )
    model = AsyncMock(return_value=package)
    monkeypatch.setattr(router, "aira_structured_proposal", model)
    db = SimpleNamespace(
        commit=AsyncMock(), expire_all=lambda: None, refresh=AsyncMock()
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(router.draft_with_aira(params, SimpleNamespace(id=uuid4()), db))
    assert error.value.status_code == 409
    model.assert_awaited_once()


def test_migration_is_chained_and_registered():
    migration = import_module("migrations.versions.0048_instrument_integration_drafts")
    assert migration.down_revision == "0047_instrument_control_sessions"
    from migrations.model_registry import MODEL_MODULES

    assert "app.models.instrument_integration" in MODEL_MODULES
