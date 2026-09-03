"""Governed Lab catalog for external research-service providers and offerings."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.database import DBSession
from app.models.lab import Lab
from app.models.research_execution import (
    ResearchServiceOffering,
    ResearchServiceOfferingRevision,
    ResearchServiceProvider,
    ResearchServiceProviderAudit,
)
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.access_control import resolve_resource_access
from app.services.research_budget import normalize_currency
from app.services.research_instruments import validate_bounded_schema
from app.services.research_runtime import canonical_digest, utcnow
from app.services.research_services import (
    SERVICE_KEY_RE,
    latest_service_offering_revision,
    latest_service_offering_rows,
    offering_snapshot,
    provider_snapshot,
)

router = APIRouter(prefix="/research-services", tags=["research-services"])


def _clean_url(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Provider website must be an HTTP(S) URL")
    return cleaned


class ServiceProviderDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lab_id: UUID
    provider_key: str = Field(min_length=2, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=4000)
    contact_name: str = Field(default="", max_length=255)
    contact_email: str = Field(default="", max_length=320)
    website_url: str = Field(default="", max_length=2048)
    enabled: bool = True
    reason: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def normalize(self):
        self.provider_key = self.provider_key.strip().lower()
        self.name = self.name.strip()
        self.description = self.description.strip()
        self.contact_name = self.contact_name.strip()
        self.contact_email = self.contact_email.strip().lower()
        self.website_url = _clean_url(self.website_url)
        self.reason = self.reason.strip()
        if not SERVICE_KEY_RE.fullmatch(self.provider_key):
            raise ValueError("Invalid service provider key")
        if self.contact_email and (
            "@" not in self.contact_email or self.contact_email.startswith("@")
        ):
            raise ValueError("Invalid service provider contact email")
        return self


class ServiceProviderCreate(ServiceProviderDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class ServiceProviderUpdateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=4000)
    contact_name: str = Field(default="", max_length=255)
    contact_email: str = Field(default="", max_length=320)
    website_url: str = Field(default="", max_length=2048)
    enabled: bool
    reason: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def normalize(self):
        self.name = self.name.strip()
        self.description = self.description.strip()
        self.contact_name = self.contact_name.strip()
        self.contact_email = self.contact_email.strip().lower()
        self.website_url = _clean_url(self.website_url)
        self.reason = self.reason.strip()
        if self.contact_email and (
            "@" not in self.contact_email or self.contact_email.startswith("@")
        ):
            raise ValueError("Invalid service provider contact email")
        return self


class ServiceProviderUpdate(ServiceProviderUpdateDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class ServiceOfferingDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: UUID
    offering_key: str = Field(min_length=2, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=4000)
    service_version: str = Field(min_length=1, max_length=64)
    input_schema: dict[str, Any]
    result_schema: dict[str, Any]
    quote_required: bool = True
    base_price: Decimal | None = Field(
        default=None, ge=0, max_digits=38, decimal_places=18
    )
    currency: str | None = Field(default=None, max_length=16)
    sla_hours: int | None = Field(default=None, ge=1, le=87600)
    sample_requirements: dict[str, Any] = Field(default_factory=dict)
    logistics_policy: dict[str, Any] = Field(default_factory=dict)
    terms: str = Field(default="", max_length=20_000)
    risk: Literal["low", "medium", "high"] = "medium"
    enabled: bool = True
    reason: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def normalize(self):
        self.offering_key = self.offering_key.strip().lower()
        self.name = self.name.strip()
        self.description = self.description.strip()
        self.service_version = self.service_version.strip()
        self.terms = self.terms.strip()
        self.reason = self.reason.strip()
        if not SERVICE_KEY_RE.fullmatch(self.offering_key):
            raise ValueError("Invalid service offering key")
        self.input_schema = validate_bounded_schema(self.input_schema, "service input")
        self.result_schema = validate_bounded_schema(
            self.result_schema, "service result"
        )
        if (self.base_price is None) != (self.currency is None):
            raise ValueError("Base price and currency must be provided together")
        if not self.quote_required and self.base_price is None:
            raise ValueError("A service without provider quotes requires a catalog price")
        if self.currency is not None:
            self.currency = normalize_currency(self.currency)
        if len(str(self.sample_requirements)) > 50_000:
            raise ValueError("Sample requirements are too large")
        if len(str(self.logistics_policy)) > 50_000:
            raise ValueError("Logistics policy is too large")
        return self


class ServiceOfferingCreate(ServiceOfferingDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class ServiceOfferingRevisionDraft(ServiceOfferingDraft):
    expected_revision: int = Field(ge=1)


class ServiceOfferingRevisionCreate(ServiceOfferingRevisionDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


async def _lab_access(
    db_session: DBSession,
    *,
    user: User,
    lab_id: UUID,
    capability: str,
) -> Lab:
    lab = await db_session.get(Lab, lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    access = await resolve_resource_access(db_session, user.id, lab_id)
    if not access.allows(capability):
        raise HTTPException(status_code=403, detail="Research service access denied")
    return lab


async def _provider_context(
    db_session: DBSession,
    *,
    user: User,
    provider_id: UUID,
    lock: bool,
) -> ResearchServiceProvider:
    statement = select(ResearchServiceProvider).where(
        ResearchServiceProvider.id == provider_id,
        ResearchServiceProvider.archived_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    provider = (await db_session.scalars(statement)).first()
    if provider is None:
        raise HTTPException(status_code=404, detail="Research service provider not found")
    await _lab_access(
        db_session,
        user=user,
        lab_id=provider.lab_id,
        capability="research.service.manage",
    )
    return provider


async def _offering_context(
    db_session: DBSession,
    *,
    user: User,
    offering_id: UUID,
    lock: bool,
) -> tuple[
    ResearchServiceProvider,
    ResearchServiceOffering,
    ResearchServiceOfferingRevision,
]:
    statement = select(ResearchServiceOffering).where(
        ResearchServiceOffering.id == offering_id,
        ResearchServiceOffering.archived_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    offering = (await db_session.scalars(statement)).first()
    if offering is None:
        raise HTTPException(status_code=404, detail="Research service offering not found")
    provider = await _provider_context(
        db_session, user=user, provider_id=offering.provider_id, lock=lock
    )
    revision = await latest_service_offering_revision(
        db_session, offering.id, lock=lock
    )
    if revision is None:
        raise HTTPException(status_code=409, detail="Service offering has no revision")
    return provider, offering, revision


def _provider_create_command(params: ServiceProviderDraft) -> dict[str, Any]:
    return {
        "operation": "create_research_service_provider",
        "lab_id": str(params.lab_id),
        "provider_key": params.provider_key,
        "name": params.name,
        "description": params.description,
        "contact_name": params.contact_name,
        "contact_email": params.contact_email,
        "website_url": params.website_url,
        "enabled": params.enabled,
    }


def _provider_update_command(
    provider: ResearchServiceProvider,
    params: ServiceProviderUpdateDraft,
) -> dict[str, Any]:
    return {
        "operation": "update_research_service_provider",
        "provider_id": str(provider.id),
        "expected_revision": params.expected_revision,
        "name": params.name,
        "description": params.description,
        "contact_name": params.contact_name,
        "contact_email": params.contact_email,
        "website_url": params.website_url,
        "enabled": params.enabled,
    }


def _offering_command(
    provider: ResearchServiceProvider,
    params: ServiceOfferingDraft,
    *,
    operation: str,
    offering_id: UUID | None = None,
    offering_revision: int,
) -> dict[str, Any]:
    return {
        "operation": operation,
        "provider_id": str(provider.id),
        "provider_revision": provider.revision,
        "offering_id": str(offering_id) if offering_id else None,
        "offering_revision": offering_revision,
        "offering_key": params.offering_key,
        "name": params.name,
        "description": params.description,
        "service_version": params.service_version,
        "input_schema": params.input_schema,
        "result_schema": params.result_schema,
        "quote_required": params.quote_required,
        "base_price": str(params.base_price) if params.base_price is not None else None,
        "currency": params.currency,
        "sla_hours": params.sla_hours,
        "sample_requirements": params.sample_requirements,
        "logistics_policy": params.logistics_policy,
        "terms": params.terms,
        "risk": params.risk,
        "enabled": params.enabled,
    }


def _provider_audit(
    provider: ResearchServiceProvider,
    *,
    actor_user_id: UUID,
    action: str,
    reason: str,
) -> ResearchServiceProviderAudit:
    return ResearchServiceProviderAudit(
        provider_id=provider.id,
        lab_id=provider.lab_id,
        revision=provider.revision,
        action=action,
        snapshot=provider_snapshot(provider),
        reason=reason,
        actor_user_id=actor_user_id,
    )


@router.get("")
async def list_research_services(
    lab_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _lab_access(
        db_session,
        user=current_user,
        lab_id=lab_id,
        capability="research.service.manage",
    )
    providers = list(
        (
            await db_session.scalars(
                select(ResearchServiceProvider)
                .where(
                    ResearchServiceProvider.lab_id == lab_id,
                    ResearchServiceProvider.archived_at.is_(None),
                )
                .order_by(ResearchServiceProvider.name, ResearchServiceProvider.id)
            )
        ).all()
    )
    offering_rows = await latest_service_offering_rows(
        db_session, lab_id=lab_id, enabled_only=False
    )
    offerings_by_provider: dict[UUID, list[dict[str, Any]]] = {}
    for provider, offering, revision in offering_rows:
        offerings_by_provider.setdefault(provider.id, []).append(
            offering_snapshot(provider, offering, revision)
        )
    return {
        "providers": [
            {
                **provider_snapshot(provider),
                "offerings": offerings_by_provider.get(provider.id, []),
            }
            for provider in providers
        ]
    }


@router.post("/providers/preview")
async def preview_service_provider(
    params: ServiceProviderDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    lab = await _lab_access(
        db_session,
        user=current_user,
        lab_id=params.lab_id,
        capability="research.service.manage",
    )
    command = _provider_create_command(params)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": {"lab_id": str(lab.id), "lab_uid": lab.uid, "name": lab.name},
        "effects": [
            "Create a Lab-scoped external research-service provider",
            "Expose no executable service until an offering revision is added",
            "Record an immutable configuration audit event",
        ],
    }


@router.post("/providers")
async def create_service_provider(
    params: ServiceProviderCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _lab_access(
        db_session,
        user=current_user,
        lab_id=params.lab_id,
        capability="research.service.manage",
    )
    command = _provider_create_command(params)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="Service provider preview changed")
    if await ResearchServiceProvider.exists(
        db_session,
        [
            ResearchServiceProvider.lab_id == params.lab_id,
            ResearchServiceProvider.provider_key == params.provider_key,
        ],
    ):
        raise HTTPException(status_code=409, detail="Service provider key is in use")
    provider = ResearchServiceProvider(
        lab_id=params.lab_id,
        provider_key=params.provider_key,
        name=params.name,
        description=params.description,
        contact_name=params.contact_name,
        contact_email=params.contact_email,
        website_url=params.website_url,
        enabled=params.enabled,
        created_by_user_id=current_user.id,
        updated_by_user_id=current_user.id,
    )
    db_session.add(provider)
    await db_session.flush()
    db_session.add(
        _provider_audit(
            provider,
            actor_user_id=current_user.id,
            action="provider.created",
            reason=params.reason,
        )
    )
    await db_session.commit()
    return provider_snapshot(provider)


@router.post("/providers/{provider_id}/preview")
async def preview_service_provider_update(
    provider_id: UUID,
    params: ServiceProviderUpdateDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    provider = await _provider_context(
        db_session, user=current_user, provider_id=provider_id, lock=False
    )
    if provider.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Service provider changed")
    command = _provider_update_command(provider, params)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "current": provider_snapshot(provider),
        "effects": [
            "Create a new provider configuration revision",
            "Block new service selection immediately when disabled",
            "Keep existing Research Environments pinned to their captured contract",
        ],
    }


@router.put("/providers/{provider_id}")
async def update_service_provider(
    provider_id: UUID,
    params: ServiceProviderUpdate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    provider = await _provider_context(
        db_session, user=current_user, provider_id=provider_id, lock=True
    )
    if provider.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Service provider changed")
    command = _provider_update_command(provider, params)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="Service provider preview changed")
    provider.name = params.name
    provider.description = params.description
    provider.contact_name = params.contact_name
    provider.contact_email = params.contact_email
    provider.website_url = params.website_url
    provider.enabled = params.enabled
    provider.revision += 1
    provider.updated_by_user_id = current_user.id
    provider.updated_at = utcnow()
    db_session.add(
        _provider_audit(
            provider,
            actor_user_id=current_user.id,
            action="provider.updated",
            reason=params.reason,
        )
    )
    await db_session.commit()
    return provider_snapshot(provider)


@router.post("/offerings/preview")
async def preview_service_offering(
    params: ServiceOfferingDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    provider = await _provider_context(
        db_session, user=current_user, provider_id=params.provider_id, lock=False
    )
    if not provider.enabled:
        raise HTTPException(status_code=409, detail="Service provider is disabled")
    command = _offering_command(
        provider,
        params,
        operation="create_research_service_offering",
        offering_revision=1,
    )
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "provider": provider_snapshot(provider),
        "effects": [
            "Create a stable service identity and immutable first contract revision",
            "Validate all future requests and results against the pinned JSON Schemas",
            "Make the offering selectable only while both provider and offering are enabled",
        ],
    }


@router.post("/offerings")
async def create_service_offering(
    params: ServiceOfferingCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    provider = await _provider_context(
        db_session, user=current_user, provider_id=params.provider_id, lock=True
    )
    if not provider.enabled:
        raise HTTPException(status_code=409, detail="Service provider is disabled")
    command = _offering_command(
        provider,
        params,
        operation="create_research_service_offering",
        offering_revision=1,
    )
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="Service offering preview changed")
    if await ResearchServiceOffering.exists(
        db_session,
        [
            ResearchServiceOffering.lab_id == provider.lab_id,
            ResearchServiceOffering.offering_key == params.offering_key,
        ],
    ):
        raise HTTPException(status_code=409, detail="Service offering key is in use")
    offering = ResearchServiceOffering(
        provider_id=provider.id,
        lab_id=provider.lab_id,
        offering_key=params.offering_key,
        name=params.name,
        description=params.description,
        enabled=params.enabled,
        created_by_user_id=current_user.id,
    )
    db_session.add(offering)
    await db_session.flush()
    revision = ResearchServiceOfferingRevision(
        offering_id=offering.id,
        revision=1,
        service_version=params.service_version,
        input_schema=params.input_schema,
        result_schema=params.result_schema,
        quote_required=params.quote_required,
        base_price=params.base_price,
        currency=params.currency,
        sla_hours=params.sla_hours,
        sample_requirements=params.sample_requirements,
        logistics_policy=params.logistics_policy,
        terms=params.terms,
        reason=params.reason,
        risk=params.risk,
        created_by_user_id=current_user.id,
    )
    db_session.add(revision)
    await db_session.flush()
    await db_session.commit()
    return offering_snapshot(provider, offering, revision)


@router.post("/offerings/{offering_id}/revisions/preview")
async def preview_service_offering_revision(
    offering_id: UUID,
    params: ServiceOfferingRevisionDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    provider, offering, current = await _offering_context(
        db_session, user=current_user, offering_id=offering_id, lock=False
    )
    if params.provider_id != provider.id or params.offering_key != offering.offering_key:
        raise HTTPException(status_code=422, detail="Stable service identity cannot change")
    if params.expected_revision != current.revision:
        raise HTTPException(status_code=409, detail="Service offering changed")
    command = _offering_command(
        provider,
        params,
        operation="revise_research_service_offering",
        offering_id=offering.id,
        offering_revision=current.revision + 1,
    )
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "current": offering_snapshot(provider, offering, current),
        "effects": [
            "Create a new immutable service contract revision",
            "Keep existing Research Environments pinned to the earlier revision",
            "Use the new revision only for newly created Tasks",
        ],
    }


@router.post("/offerings/{offering_id}/revisions")
async def create_service_offering_revision(
    offering_id: UUID,
    params: ServiceOfferingRevisionCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    provider, offering, current = await _offering_context(
        db_session, user=current_user, offering_id=offering_id, lock=True
    )
    if params.provider_id != provider.id or params.offering_key != offering.offering_key:
        raise HTTPException(status_code=422, detail="Stable service identity cannot change")
    if params.expected_revision != current.revision:
        raise HTTPException(status_code=409, detail="Service offering changed")
    command = _offering_command(
        provider,
        params,
        operation="revise_research_service_offering",
        offering_id=offering.id,
        offering_revision=current.revision + 1,
    )
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="Service offering preview changed")
    duplicate_version = await ResearchServiceOfferingRevision.exists(
        db_session,
        [
            ResearchServiceOfferingRevision.offering_id == offering.id,
            ResearchServiceOfferingRevision.service_version == params.service_version,
        ],
    )
    if duplicate_version:
        raise HTTPException(status_code=409, detail="Service version already exists")
    offering.name = params.name
    offering.description = params.description
    offering.enabled = params.enabled
    offering.updated_at = utcnow()
    revision = ResearchServiceOfferingRevision(
        offering_id=offering.id,
        revision=current.revision + 1,
        service_version=params.service_version,
        input_schema=params.input_schema,
        result_schema=params.result_schema,
        quote_required=params.quote_required,
        base_price=params.base_price,
        currency=params.currency,
        sla_hours=params.sla_hours,
        sample_requirements=params.sample_requirements,
        logistics_policy=params.logistics_policy,
        terms=params.terms,
        reason=params.reason,
        risk=params.risk,
        created_by_user_id=current_user.id,
    )
    db_session.add(revision)
    await db_session.flush()
    await db_session.commit()
    return offering_snapshot(provider, offering, revision)
