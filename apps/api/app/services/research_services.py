"""Versioned external research-service catalog helpers."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_execution import (
    ResearchServiceOffering,
    ResearchServiceOfferingRevision,
    ResearchServiceProvider,
)

SERVICE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")


def provider_snapshot(provider: ResearchServiceProvider) -> dict[str, Any]:
    return {
        "id": str(provider.id),
        "lab_id": str(provider.lab_id),
        "provider_key": provider.provider_key,
        "name": provider.name,
        "description": provider.description,
        "contact_name": provider.contact_name,
        "contact_email": provider.contact_email,
        "website_url": provider.website_url,
        "enabled": provider.enabled,
        "revision": provider.revision,
        "archived_at": (
            provider.archived_at.isoformat() if provider.archived_at else None
        ),
    }


def _money(value: Decimal | None) -> str | None:
    return format(value.normalize(), "f") if value is not None else None


def offering_snapshot(
    provider: ResearchServiceProvider,
    offering: ResearchServiceOffering,
    revision: ResearchServiceOfferingRevision,
) -> dict[str, Any]:
    return {
        "key": f"service:{offering.id}",
        "version": revision.service_version,
        "kind": "service",
        "name": offering.name,
        "description": offering.description,
        "source_type": "research_service_offering_revision",
        "source_id": str(offering.id),
        "source_revision_id": str(revision.id),
        "executor_types": ["external_service"],
        "risk": revision.risk,
        "input_schema": revision.input_schema,
        "output_schema": revision.result_schema,
        "available": bool(provider.enabled and offering.enabled),
        "unavailable_reason": (
            "" if provider.enabled and offering.enabled else "Provider or offering disabled"
        ),
        "metadata": {
            "lab_id": str(offering.lab_id),
            "provider": provider_snapshot(provider),
            "offering_id": str(offering.id),
            "offering_key": offering.offering_key,
            "offering_enabled": offering.enabled,
            "offering_revision": revision.revision,
            "quote_required": revision.quote_required,
            "base_price": _money(revision.base_price),
            "currency": revision.currency,
            "sla_hours": revision.sla_hours,
            "sample_requirements": revision.sample_requirements,
            "logistics_policy": revision.logistics_policy,
            "terms": revision.terms,
            "change_reason": revision.reason,
        },
    }


async def latest_service_offering_rows(
    db_session: AsyncSession,
    *,
    lab_id: UUID,
    enabled_only: bool,
) -> list[
    tuple[
        ResearchServiceProvider,
        ResearchServiceOffering,
        ResearchServiceOfferingRevision,
    ]
]:
    latest = (
        select(
            ResearchServiceOfferingRevision.offering_id.label("offering_id"),
            func.max(ResearchServiceOfferingRevision.revision).label("revision"),
        )
        .group_by(ResearchServiceOfferingRevision.offering_id)
        .subquery()
    )
    statement = (
        select(
            ResearchServiceProvider,
            ResearchServiceOffering,
            ResearchServiceOfferingRevision,
        )
        .join(
            ResearchServiceOffering,
            ResearchServiceOffering.provider_id == ResearchServiceProvider.id,
        )
        .join(latest, latest.c.offering_id == ResearchServiceOffering.id)
        .join(
            ResearchServiceOfferingRevision,
            (ResearchServiceOfferingRevision.offering_id == latest.c.offering_id)
            & (ResearchServiceOfferingRevision.revision == latest.c.revision),
        )
        .where(
            ResearchServiceProvider.lab_id == lab_id,
            ResearchServiceProvider.archived_at.is_(None),
            ResearchServiceOffering.archived_at.is_(None),
        )
        .order_by(
            ResearchServiceProvider.name,
            ResearchServiceOffering.name,
            ResearchServiceOffering.id,
        )
    )
    if enabled_only:
        statement = statement.where(
            ResearchServiceProvider.enabled.is_(True),
            ResearchServiceOffering.enabled.is_(True),
        )
    return list((await db_session.execute(statement)).all())


async def latest_service_offering_revision(
    db_session: AsyncSession,
    offering_id: UUID,
    *,
    lock: bool = False,
) -> ResearchServiceOfferingRevision | None:
    statement = (
        select(ResearchServiceOfferingRevision)
        .where(ResearchServiceOfferingRevision.offering_id == offering_id)
        .order_by(ResearchServiceOfferingRevision.revision.desc())
        .limit(1)
    )
    if lock:
        statement = statement.with_for_update()
    return (await db_session.scalars(statement)).first()
