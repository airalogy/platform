import asyncio
from datetime import UTC, datetime, timedelta
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.main import app
from app.models.research_execution import (
    ResearchServiceCustodyEvent,
    ResearchServiceJob,
    ResearchServiceQuote,
    ResearchServiceResultAsset,
)
from app.routers.research_service_jobs import (
    ServiceCustodyDraft,
    ServiceQuoteDraft,
    ServiceResultDraft,
    _custody_command,
)
from app.services import research_external_services
from app.services.research_external_services import (
    request_service_order_approval,
    service_order_command,
)
from app.services.research_runtime import canonical_digest


def compile_table(model) -> str:
    return str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))


def test_external_service_job_models_are_typed_and_append_only():
    job_ddl = compile_table(ResearchServiceJob)
    quote_ddl = compile_table(ResearchServiceQuote)
    custody_ddl = compile_table(ResearchServiceCustodyEvent)
    asset_ddl = compile_table(ResearchServiceResultAsset)

    assert "ck_research_service_job_status" in job_ddl
    assert "creation_digest" in job_ddl
    assert "uq_research_service_quote_revision" in quote_ddl
    assert "quote_digest" in quote_ddl
    assert "uq_research_service_custody_sequence" in custody_ddl
    assert "event_digest" in custody_ddl
    assert "uq_research_service_result_asset" in asset_ddl


def test_external_service_job_migration_follows_catalog():
    migration = import_module("migrations.versions.0029_research_service_jobs")

    assert migration.down_revision == "0028_research_service_catalog"
    assert migration.TABLE_NAMES == (
        "research_service_jobs",
        "research_service_quotes",
        "research_service_custody_events",
        "research_service_result_assets",
    )


def test_quote_normalizes_currency_and_rejects_expired_validity():
    draft = ServiceQuoteDraft(
        expected_revision=1,
        amount="1250.00",
        currency="usd",
        valid_until=datetime.now(UTC) + timedelta(days=7),
    )

    assert draft.currency == "USD"
    with pytest.raises(ValidationError, match="end in the future"):
        ServiceQuoteDraft(
            expected_revision=1,
            amount="1250.00",
            currency="USD",
            valid_until=datetime.now(UTC) - timedelta(seconds=1),
        )


def test_custody_event_rejects_future_time_and_result_assets_are_unique():
    common = {
        "expected_revision": 2,
        "kind": "released_to_carrier",
        "resource_id": uuid4(),
        "from_party": "Lab",
        "to_party": "Provider",
        "occurred_at": datetime.now(UTC),
    }
    custody = ServiceCustodyDraft(**common)
    assert custody.from_party == "Lab"

    with pytest.raises(ValidationError, match="cannot be in the future"):
        ServiceCustodyDraft(
            **{**common, "occurred_at": datetime.now(UTC) + timedelta(hours=1)}
        )

    version_id = uuid4()
    with pytest.raises(ValidationError, match="contain duplicates"):
        ServiceResultDraft(
            expected_revision=2,
            result={},
            data_asset_version_ids=[version_id, version_id],
        )


def test_order_and_custody_commands_bind_exact_versions_and_state():
    quote = SimpleNamespace(
        id=uuid4(),
        revision=3,
        quote_digest="a" * 64,
        amount="1250",
        currency="USD",
        valid_until=None,
    )
    job = SimpleNamespace(
        id=uuid4(),
        revision=4,
        provider_id=uuid4(),
        service_offering_id=uuid4(),
        service_offering_revision_id=uuid4(),
        service_version="2026.1",
        request_payload={"sample_count": 4},
    )
    approval = service_order_command(job, quote)
    assert approval["quote_revision"] == 3
    assert approval["service_offering_revision_id"] == str(
        job.service_offering_revision_id
    )

    custody = ServiceCustodyDraft(
        expected_revision=4,
        kind="released_to_carrier",
        resource_id=uuid4(),
        from_party="Airalogy Lab",
        to_party="Sequencing Provider",
        occurred_at=datetime.now(UTC),
    )
    command = _custody_command(job, 2, custody)
    assert command["sequence"] == 2
    assert len(canonical_digest(command)) == 64


def test_manual_and_aira_service_orders_share_the_same_approval_gate(monkeypatch):
    added = []
    db_session = SimpleNamespace(
        add=added.append,
        flush=AsyncMock(),
    )
    task = SimpleNamespace(id=uuid4(), owner_user_id=uuid4(), revision=7)
    run = SimpleNamespace(id=uuid4(), status="waiting_for_event", last_error="old")
    action = SimpleNamespace(
        id=uuid4(),
        preview_digest="a" * 64,
        status="waiting",
        policy_decision="allow",
        revision=2,
    )
    job = SimpleNamespace(
        id=uuid4(),
        revision=4,
        status="awaiting_quote",
        current_quote_revision=None,
        provider_id=uuid4(),
        service_offering_id=uuid4(),
        service_offering_revision_id=uuid4(),
        service_version="2026.1",
        request_payload={"sample_count": 4},
    )
    quote = SimpleNamespace(
        id=uuid4(),
        revision=3,
        quote_digest="b" * 64,
        amount="1250",
        currency="USD",
        valid_until=None,
    )
    event = AsyncMock()
    monkeypatch.setattr(research_external_services, "emit_research_event", event)

    approval = asyncio.run(
        request_service_order_approval(
            db_session,
            task=task,
            run=run,
            action=action,
            job=job,
            quote=quote,
            requested_by_user_id=uuid4(),
            actor_user_id=None,
            reason="Approve Aira service order",
        )
    )

    assert approval in added
    assert approval.preview_digest == action.preview_digest
    assert approval.reason == "Approve Aira service order"
    assert job.status == "awaiting_approval"
    assert job.current_quote_revision == 3
    assert job.revision == 5
    assert action.status == "proposed"
    assert action.policy_decision == "ask"
    assert action.revision == 3
    assert run.status == "waiting_for_approval"
    assert run.last_error is None
    assert task.revision == 8
    event.assert_awaited_once()


def test_external_service_job_routes_are_registered():
    paths = {route.path for route in app.routes}

    assert "/research-tasks/{task_id}/service-actions/preview" in paths
    assert "/research-service-jobs/{job_id}/quotes/preview" in paths
    assert "/research-service-jobs/{job_id}/custody/preview" in paths
    assert "/research-service-jobs/{job_id}/result/preview" in paths
