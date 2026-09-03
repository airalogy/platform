from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.main import app
from app.models.research import ResearchTaskServiceOffering
from app.models.research_execution import (
    ResearchServiceOffering,
    ResearchServiceOfferingRevision,
    ResearchServiceProvider,
    ResearchServiceProviderAudit,
)
from app.routers.research_services import ServiceOfferingDraft, ServiceProviderDraft
from app.services.access_control import ROLE_CAPABILITIES
from app.services.research_services import offering_snapshot


def compile_table(model) -> str:
    return str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))


def test_service_catalog_models_are_versioned_and_task_pinned():
    provider_ddl = compile_table(ResearchServiceProvider)
    audit_ddl = compile_table(ResearchServiceProviderAudit)
    offering_ddl = compile_table(ResearchServiceOffering)
    revision_ddl = compile_table(ResearchServiceOfferingRevision)
    task_link_ddl = compile_table(ResearchTaskServiceOffering)

    assert "uq_research_service_provider_key" in provider_ddl
    assert "uq_research_service_provider_audit_revision" in audit_ddl
    assert "uq_research_service_offering_key" in offering_ddl
    assert "uq_research_service_offering_revision" in revision_ddl
    assert "ck_research_service_offering_price_pair" in revision_ddl
    assert "service_offering_revision_id" in task_link_ddl
    assert "uq_research_task_service_offering" in task_link_ddl


def test_service_catalog_migration_follows_instrument_jobs():
    migration = import_module("migrations.versions.0028_research_service_catalog")

    assert migration.down_revision == "0027_research_instrument_jobs"
    assert migration.TABLE_NAMES == (
        "research_service_providers",
        "research_service_provider_audits",
        "research_service_offerings",
        "research_service_offering_revisions",
        "research_task_service_offerings",
    )


def test_service_contract_requires_local_object_schemas_and_price_pair():
    valid = ServiceOfferingDraft(
        provider_id=uuid4(),
        offering_key="rna-seq.standard",
        name="Standard RNA sequencing",
        service_version="2026.1",
        input_schema={
            "type": "object",
            "properties": {"sample_count": {"type": "integer", "minimum": 1}},
            "required": ["sample_count"],
            "additionalProperties": False,
        },
        result_schema={
            "type": "object",
            "properties": {"data_asset_ids": {"type": "array"}},
            "required": ["data_asset_ids"],
        },
        base_price=Decimal(1200),
        currency="usd",
        sla_hours=240,
    )

    assert valid.currency == "USD"
    with pytest.raises(ValidationError, match="provided together"):
        ServiceOfferingDraft(
            **{
                **valid.model_dump(),
                "currency": None,
            }
        )
    with pytest.raises(ValidationError, match="remote references"):
        ServiceOfferingDraft(
            **{
                **valid.model_dump(),
                "input_schema": {
                    "type": "object",
                    "$ref": "https://example.com/schema.json",
                },
            }
        )
    with pytest.raises(ValidationError, match="requires a catalog price"):
        ServiceOfferingDraft(
            **{
                **valid.model_dump(),
                "quote_required": False,
                "base_price": None,
                "currency": None,
            }
        )


def test_service_provider_rejects_non_http_website():
    with pytest.raises(ValidationError, match=r"HTTP\(S\)"):
        ServiceProviderDraft(
            lab_id=uuid4(),
            provider_key="vendor-a",
            name="Vendor A",
            website_url="file:///etc/passwd",
        )


def test_service_snapshot_preserves_provider_contract_and_exact_revision():
    provider = SimpleNamespace(
        id=uuid4(),
        lab_id=uuid4(),
        provider_key="vendor-a",
        name="Vendor A",
        description="Sequencing partner",
        contact_name="Operations",
        contact_email="ops@example.test",
        website_url="https://example.test",
        enabled=True,
        revision=3,
        archived_at=None,
    )
    offering = SimpleNamespace(
        id=uuid4(),
        lab_id=provider.lab_id,
        offering_key="rna-seq.standard",
        name="Standard RNA sequencing",
        description="Library prep and sequencing",
        enabled=True,
    )
    revision = SimpleNamespace(
        id=uuid4(),
        revision=4,
        service_version="2026.1",
        input_schema={"type": "object"},
        result_schema={"type": "object"},
        quote_required=True,
        base_price=Decimal("1200.00"),
        currency="USD",
        sla_hours=240,
        sample_requirements={"material": "total RNA"},
        logistics_policy={"temperature": "dry_ice"},
        terms="Lab-approved master service agreement",
        reason="Annual contract review",
        risk="medium",
    )

    snapshot = offering_snapshot(provider, offering, revision)

    assert snapshot["source_revision_id"] == str(revision.id)
    assert snapshot["metadata"]["offering_revision"] == 4
    assert snapshot["metadata"]["provider"]["revision"] == 3
    assert snapshot["metadata"]["base_price"] == "1200"
    assert snapshot["metadata"]["change_reason"] == "Annual contract review"


def test_service_capabilities_are_explicit_and_grantable():
    assert "research.service.use" in ROLE_CAPABILITIES["contributor"]
    assert "research.service.manage" not in ROLE_CAPABILITIES["contributor"]
    assert ROLE_CAPABILITIES["research_service_manager"] == {
        "research.read",
        "research.service.use",
        "research.service.manage",
    }


def test_service_catalog_routes_are_registered():
    paths = {route.path for route in app.routes}

    assert "/research-services" in paths
    assert "/research-services/providers/preview" in paths
    assert "/research-services/offerings/preview" in paths
