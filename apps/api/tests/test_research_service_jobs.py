from datetime import UTC, datetime, timedelta
from importlib import import_module
from types import SimpleNamespace
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
from app.services.research_external_services import service_order_command
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


def test_external_service_job_routes_are_registered():
    paths = {route.path for route in app.routes}

    assert "/research-tasks/{task_id}/service-actions/preview" in paths
    assert "/research-service-jobs/{job_id}/quotes/preview" in paths
    assert "/research-service-jobs/{job_id}/custody/preview" in paths
    assert "/research-service-jobs/{job_id}/result/preview" in paths
