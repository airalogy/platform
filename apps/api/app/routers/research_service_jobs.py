"""Governed request, quote, custody, and result flow for research services."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select

from app.config import config
from app.database import DBSession
from app.models.lab import Lab
from app.models.project import Project
from app.models.research import (
    ResearchAction,
    ResearchActionKind,
    ResearchActionStatus,
    ResearchRun,
    ResearchRunStatus,
    ResearchTask,
    ResearchTaskStatus,
)
from app.models.research_asset import DataAsset, DataAssetVersion
from app.models.research_execution import (
    ResearchServiceCustodyEvent,
    ResearchServiceJob,
    ResearchServiceJobStatus,
    ResearchServiceQuote,
    ResearchServiceResultAsset,
)
from app.models.resource import Resource, ResourceContainer, ResourceVisibility
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.access_control import resolve_resource_access
from app.services.research_budget import (
    ResearchBudgetError,
    normalize_currency,
    reached_operational_limit,
)
from app.services.research_executor_bindings import (
    enforce_environment_binding_action_limit,
    executor_binding_command_ref,
)
from app.services.research_external_services import (
    latest_service_quote,
    pinned_service_executor_binding,
    pinned_service_job_context,
    release_service_budget,
    request_service_order_approval,
    service_job_snapshot,
    settle_service_budget,
    validate_quote_budget,
)
from app.services.research_instruments import validate_schema_payload
from app.services.research_runtime import (
    append_aira_result,
    canonical_digest,
    create_plan_version,
    emit_research_event,
    enqueue_research_advance,
    hold_or_release_aira_action_group,
    require_research_capability,
    utcnow,
)

router = APIRouter(tags=["research-service-jobs"])


class ServiceActionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_offering_id: UUID
    request_payload: dict[str, Any] = Field(default_factory=dict)
    title: str = Field(default="", max_length=255)
    description: str = Field(default="", max_length=20_000)
    idempotency_key: str = Field(min_length=8, max_length=160)

    @model_validator(mode="after")
    def normalize(self):
        self.title = self.title.strip()
        self.description = self.description.strip()
        self.idempotency_key = self.idempotency_key.strip()
        return self


class ServiceActionCreate(ServiceActionDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class ServiceQuoteDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    amount: Decimal = Field(ge=0, max_digits=38, decimal_places=18)
    currency: str = Field(min_length=3, max_length=16)
    provider_quote_ref: str = Field(default="", max_length=255)
    valid_until: datetime | None = None
    terms: str = Field(default="", max_length=20_000)

    @model_validator(mode="after")
    def normalize(self):
        self.currency = normalize_currency(self.currency)
        self.provider_quote_ref = self.provider_quote_ref.strip()
        self.terms = self.terms.strip()
        if self.valid_until is not None:
            if self.valid_until.tzinfo is None:
                self.valid_until = self.valid_until.replace(tzinfo=UTC)
            if self.valid_until <= utcnow():
                raise ValueError("Quote validity must end in the future")
        return self


class ServiceQuoteCreate(ServiceQuoteDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class ServiceProgressDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    status: Literal["in_fulfillment", "failed"]
    external_order_ref: str = Field(default="", max_length=255)
    provider_status: str = Field(default="", max_length=255)
    expected_completion_at: datetime | None = None
    reason: str = Field(default="", max_length=20_000)

    @model_validator(mode="after")
    def normalize(self):
        self.external_order_ref = self.external_order_ref.strip()
        self.provider_status = self.provider_status.strip()
        self.reason = self.reason.strip()
        if self.expected_completion_at is not None and self.expected_completion_at.tzinfo is None:
            self.expected_completion_at = self.expected_completion_at.replace(tzinfo=UTC)
        if self.status == "failed" and not self.reason:
            raise ValueError("Failure reason is required")
        return self


class ServiceProgressCreate(ServiceProgressDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class ServiceCustodyDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    kind: Literal[
        "prepared",
        "released_to_carrier",
        "received_by_provider",
        "returned_to_lab",
        "disposed_by_provider",
    ]
    resource_id: UUID
    container_id: UUID | None = None
    from_party: str = Field(min_length=1, max_length=255)
    to_party: str = Field(min_length=1, max_length=255)
    location: str = Field(default="", max_length=512)
    carrier: str = Field(default="", max_length=255)
    tracking_ref: str = Field(default="", max_length=255)
    condition: dict[str, Any] = Field(default_factory=dict)
    notes: str = Field(default="", max_length=20_000)
    occurred_at: datetime

    @model_validator(mode="after")
    def normalize(self):
        for field_name in (
            "from_party",
            "to_party",
            "location",
            "carrier",
            "tracking_ref",
            "notes",
        ):
            setattr(self, field_name, getattr(self, field_name).strip())
        if self.occurred_at.tzinfo is None:
            self.occurred_at = self.occurred_at.replace(tzinfo=UTC)
        if self.occurred_at > utcnow():
            raise ValueError("Custody event time cannot be in the future")
        if len(str(self.condition)) > 50_000:
            raise ValueError("Custody condition is too large")
        return self


class ServiceCustodyCreate(ServiceCustodyDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class ServiceResultDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    result: dict[str, Any] = Field(default_factory=dict)
    data_asset_version_ids: list[UUID] = Field(default_factory=list, max_length=100)
    actual_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=38, decimal_places=18
    )

    @model_validator(mode="after")
    def normalize(self):
        if len(set(self.data_asset_version_ids)) != len(self.data_asset_version_ids):
            raise ValueError("Result DataAsset versions contain duplicates")
        return self


class ServiceResultCreate(ServiceResultDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


async def _project(db_session: DBSession, project_id: UUID) -> Project:
    project = await Project.find_by(
        db_session, [Project.id == project_id, Project.deleted_at.is_(None)]
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _active_task_context(
    db_session: DBSession,
    current_user: User,
    task_id: UUID,
) -> tuple[ResearchTask, Project, Lab, ResearchRun]:
    task = await db_session.get(ResearchTask, task_id)
    if task is None or task.archived_at is not None:
        raise HTTPException(status_code=404, detail="Research Task not found")
    project = await _project(db_session, task.project_id)
    for capability in ("research.run", "research.service.use"):
        await require_research_capability(
            db_session, user=current_user, project=project, capability=capability
        )
    if task.status != ResearchTaskStatus.ACTIVE.value:
        raise HTTPException(status_code=409, detail="Research Task must be active")
    lab = await db_session.get(Lab, task.lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    run = (
        await db_session.scalars(
            select(ResearchRun)
            .where(ResearchRun.task_id == task.id)
            .order_by(ResearchRun.run_number.desc())
            .limit(1)
        )
    ).first()
    if run is None or run.status in {
        ResearchRunStatus.COMPLETED.value,
        ResearchRunStatus.FAILED.value,
        ResearchRunStatus.CANCELLED.value,
    }:
        raise HTTPException(status_code=409, detail="Active Research Run not found")
    operational_limit = await reached_operational_limit(db_session, task=task)
    if operational_limit is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Research Task {operational_limit[0]} limit has been reached",
        )
    return task, project, lab, run


async def _job_context(
    db_session: DBSession,
    current_user: User,
    job_id: UUID,
    *,
    lock: bool,
    manage: bool,
) -> tuple[ResearchServiceJob, ResearchAction, ResearchRun, ResearchTask, Project, Lab]:
    statement = select(ResearchServiceJob).where(ResearchServiceJob.id == job_id)
    if lock:
        statement = statement.with_for_update()
    job = (await db_session.scalars(statement)).first()
    action = await db_session.get(ResearchAction, job.action_id) if job else None
    run = await db_session.get(ResearchRun, action.run_id) if action else None
    task = await db_session.get(ResearchTask, run.task_id) if run else None
    if job is None or action is None or run is None or task is None:
        raise HTTPException(status_code=404, detail="External service job not found")
    project = await _project(db_session, task.project_id)
    await require_research_capability(
        db_session, user=current_user, project=project, capability="research.read"
    )
    lab = await db_session.get(Lab, task.lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    if manage:
        access = await resolve_resource_access(db_session, current_user.id, lab.id)
        if not access.allows("research.service.manage"):
            raise HTTPException(
                status_code=403, detail="Research service management access denied"
            )
    return job, action, run, task, project, lab


def _destination(
    *, task: ResearchTask, project: Project, lab: Lab, run: ResearchRun
) -> dict[str, Any]:
    return {
        "lab": {"id": str(lab.id), "uid": lab.uid, "name": lab.name},
        "project": {
            "id": str(project.id),
            "uid": project.uid,
            "name": project.name,
        },
        "task_id": str(task.id),
        "run_id": str(run.id),
    }


def _service_action_command(
    *,
    task: ResearchTask,
    run: ResearchRun,
    pinned: dict[str, Any],
    executor_binding: dict[str, Any],
    params: ServiceActionDraft,
) -> dict[str, Any]:
    return {
        "operation": "create_external_service_action",
        "task_id": str(task.id),
        "run_id": str(run.id),
        "service_offering_id": str(params.service_offering_id),
        "service_offering_revision_id": str(pinned["source_revision_id"]),
        "service_version": pinned["version"],
        "executor_binding": executor_binding_command_ref(executor_binding),
        "request_payload": params.request_payload,
        "title": params.title or f"Request {pinned['name']}",
        "description": params.description,
        "idempotency_key": params.idempotency_key,
    }


def _quote_command(job: ResearchServiceJob, params: ServiceQuoteDraft) -> dict[str, Any]:
    return {
        "operation": "record_external_service_quote",
        "service_job_id": str(job.id),
        "expected_revision": params.expected_revision,
        "quote_revision": (job.current_quote_revision or 0) + 1,
        "amount": str(params.amount),
        "currency": params.currency,
        "provider_quote_ref": params.provider_quote_ref,
        "valid_until": params.valid_until.isoformat() if params.valid_until else None,
        "terms": params.terms,
    }


def _progress_command(
    job: ResearchServiceJob, params: ServiceProgressDraft
) -> dict[str, Any]:
    return {
        "operation": "update_external_service_progress",
        "service_job_id": str(job.id),
        "expected_revision": params.expected_revision,
        "status": params.status,
        "external_order_ref": params.external_order_ref,
        "provider_status": params.provider_status,
        "expected_completion_at": (
            params.expected_completion_at.isoformat()
            if params.expected_completion_at
            else None
        ),
        "reason": params.reason,
    }


def _custody_command(
    job: ResearchServiceJob,
    sequence: int,
    params: ServiceCustodyDraft,
) -> dict[str, Any]:
    return {
        "operation": "append_external_service_custody_event",
        "service_job_id": str(job.id),
        "expected_revision": params.expected_revision,
        "sequence": sequence,
        "kind": params.kind,
        "resource_id": str(params.resource_id),
        "container_id": str(params.container_id) if params.container_id else None,
        "from_party": params.from_party,
        "to_party": params.to_party,
        "location": params.location,
        "carrier": params.carrier,
        "tracking_ref": params.tracking_ref,
        "condition": params.condition,
        "notes": params.notes,
        "occurred_at": params.occurred_at.isoformat(),
    }


async def _result_asset_versions(
    db_session: DBSession,
    *,
    task: ResearchTask,
    ids: list[UUID],
) -> list[tuple[DataAssetVersion, DataAsset]]:
    rows: list[tuple[DataAssetVersion, DataAsset]] = []
    for version_id in ids:
        version = await db_session.get(DataAssetVersion, version_id)
        asset = await db_session.get(DataAsset, version.data_asset_id) if version else None
        if (
            version is None
            or asset is None
            or asset.archived_at is not None
            or asset.task_id != task.id
            or asset.project_id != task.project_id
            or asset.lab_id != task.lab_id
        ):
            raise HTTPException(status_code=404, detail="Result DataAsset version not found")
        rows.append((version, asset))
    return rows


def _result_command(
    job: ResearchServiceJob,
    quote: ResearchServiceQuote,
    params: ServiceResultDraft,
) -> dict[str, Any]:
    actual_amount = params.actual_amount
    if actual_amount is None:
        actual_amount = Decimal(quote.amount)
    return {
        "operation": "complete_external_service_job",
        "service_job_id": str(job.id),
        "expected_revision": params.expected_revision,
        "quote_id": str(quote.id),
        "quote_revision": quote.revision,
        "result": params.result,
        "data_asset_version_ids": [str(item) for item in params.data_asset_version_ids],
        "actual_amount": str(actual_amount),
        "currency": quote.currency,
    }


@router.get("/research-tasks/{task_id}/service-actions/options")
async def list_service_action_options(
    task_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    _task, _project_context, _lab, run = await _active_task_context(
        db_session, current_user, task_id
    )
    return {"items": list((run.environment_snapshot or {}).get("services") or [])}


@router.post("/research-tasks/{task_id}/service-actions/preview")
async def preview_service_action(
    task_id: UUID,
    params: ServiceActionDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, project, lab, run = await _active_task_context(
        db_session, current_user, task_id
    )
    try:
        pinned, provider, _offering, revision = await pinned_service_job_context(
            db_session,
            run=run,
            service_offering_id=params.service_offering_id,
            lock=False,
        )
        executor_binding = pinned_service_executor_binding(
            task=task,
            run=run,
            pinned_service=pinned,
            provider_id=provider.id,
        )
        await enforce_environment_binding_action_limit(
            db_session, run=run, binding=executor_binding
        )
        validate_schema_payload(
            revision.input_schema, params.request_payload, "service request"
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    command = _service_action_command(
        task=task,
        run=run,
        pinned=pinned,
        executor_binding=executor_binding,
        params=params,
    )
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": _destination(task=task, project=project, lab=lab, run=run),
        "service": pinned,
        "executor_binding": executor_binding,
        "effects": [
            "Create a version-pinned external Service Job Action",
            (
                "Wait for an immutable provider quote"
                if revision.quote_required
                else "Create an approval request from the pinned catalog price"
            ),
            "Require explicit order approval before reserving budget or transferring samples",
            "Validate the returned result against the pinned contract",
        ],
    }


@router.post("/research-tasks/{task_id}/service-actions")
async def create_service_action(
    task_id: UUID,
    params: ServiceActionCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    task, _project_context, _lab, run = await _active_task_context(
        db_session, current_user, task_id
    )
    try:
        pinned, provider, offering, revision = await pinned_service_job_context(
            db_session,
            run=run,
            service_offering_id=params.service_offering_id,
            lock=True,
        )
        executor_binding = pinned_service_executor_binding(
            task=task,
            run=run,
            pinned_service=pinned,
            provider_id=provider.id,
        )
        await enforce_environment_binding_action_limit(
            db_session, run=run, binding=executor_binding
        )
        validate_schema_payload(
            revision.input_schema, params.request_payload, "service request"
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    command = _service_action_command(
        task=task,
        run=run,
        pinned=pinned,
        executor_binding=executor_binding,
        params=params,
    )
    digest = canonical_digest(command)
    if digest != params.preview_digest:
        raise HTTPException(status_code=409, detail="Service Action preview changed")
    existing = await ResearchAction.find_by(
        db_session,
        [
            ResearchAction.run_id == run.id,
            ResearchAction.idempotency_key == params.idempotency_key,
        ],
    )
    if existing is not None:
        existing_job = await ResearchServiceJob.find_by(
            db_session, [ResearchServiceJob.action_id == existing.id]
        )
        if (
            existing.kind != ResearchActionKind.EXTERNAL_SERVICE_JOB.value
            or existing_job is None
            or existing_job.creation_digest != digest
        ):
            raise HTTPException(
                status_code=409, detail="Action idempotency key is already in use"
            )
        return {
            **existing.as_dict(),
            "service_job": await service_job_snapshot(db_session, existing_job),
        }
    await create_plan_version(
        db_session,
        task=task,
        run=run,
        kind="manual",
        plan={"action": command, "previous_plan_version": run.plan_version},
        summary=f"Request {pinned['name']}",
    )
    action = ResearchAction(
        run_id=run.id,
        sequence=(
            await db_session.scalar(
                select(func.max(ResearchAction.sequence)).where(
                    ResearchAction.run_id == run.id
                )
            )
            or 0
        )
        + 1,
        plan_version=run.plan_version,
        kind=ResearchActionKind.EXTERNAL_SERVICE_JOB.value,
        status=ResearchActionStatus.WAITING.value,
        title=command["title"],
        description=command["description"],
        executor_type=executor_binding["executor_type"],
        input_data={
            "service_offering_id": str(offering.id),
            "service_offering_revision_id": str(revision.id),
            "request_payload": params.request_payload,
            "source": "manual",
            "resume_run": True,
        },
        requirements={
            "risk": revision.risk,
            "input_schema": revision.input_schema,
            "result_schema": revision.result_schema,
            "quote_required": revision.quote_required,
            "approval_policy": executor_binding["approval_policy"],
            "executor_binding": executor_binding,
        },
        policy_decision="ask",
        preview_digest=digest,
        idempotency_key=params.idempotency_key,
    )
    db_session.add(action)
    await db_session.flush()
    now = utcnow()
    job = ResearchServiceJob(
        action_id=action.id,
        provider_id=provider.id,
        service_offering_id=offering.id,
        service_offering_revision_id=revision.id,
        service_offering_revision=revision.revision,
        service_version=revision.service_version,
        provider_snapshot=pinned["metadata"]["provider"],
        offering_snapshot=pinned,
        request_payload=params.request_payload,
        input_schema=revision.input_schema,
        result_schema=revision.result_schema,
        risk=revision.risk,
        quote_required=revision.quote_required,
        creation_digest=digest,
        status=ResearchServiceJobStatus.AWAITING_QUOTE.value,
        quote_requested_at=now,
    )
    db_session.add(job)
    await db_session.flush()
    if revision.quote_required:
        run.status = ResearchRunStatus.WAITING_FOR_EVENT.value
        event_kind = "external_service.quote_requested"
    else:
        if revision.base_price is None or revision.currency is None:
            raise HTTPException(
                status_code=409, detail="Pinned service has no catalog price"
            )
        try:
            await validate_quote_budget(
                db_session,
                task=task,
                amount=Decimal(revision.base_price),
                currency=revision.currency,
            )
        except ResearchBudgetError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        quote_command = {
            "operation": "create_catalog_service_quote",
            "service_job_id": str(job.id),
            "amount": str(revision.base_price),
            "currency": revision.currency,
            "service_offering_revision_id": str(revision.id),
        }
        quote = ResearchServiceQuote(
            service_job_id=job.id,
            revision=1,
            amount=revision.base_price,
            currency=revision.currency,
            terms=revision.terms,
            source="catalog",
            quote_digest=canonical_digest(quote_command),
            created_by_user_id=current_user.id,
        )
        db_session.add(quote)
        await db_session.flush()
        await request_service_order_approval(
            db_session,
            task=task,
            run=run,
            action=action,
            job=job,
            quote=quote,
            requested_by_user_id=current_user.id,
            actor_user_id=current_user.id,
        )
        event_kind = "external_service.catalog_quote_created"
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind=event_kind,
        actor_user_id=current_user.id,
        payload={
            "service_job_id": str(job.id),
            "provider_id": str(provider.id),
            "service_offering_id": str(offering.id),
            "service_version": revision.service_version,
        },
        idempotency_key=f"service-job:{job.id}:created",
    )
    await db_session.commit()
    return {
        **action.as_dict(),
        "service_job": await service_job_snapshot(db_session, job),
    }


@router.post("/research-service-jobs/{job_id}/quotes/preview")
async def preview_service_quote(
    job_id: UUID,
    params: ServiceQuoteDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    job, _action, _run, task, _project_context, _lab = await _job_context(
        db_session, current_user, job_id, lock=False, manage=True
    )
    if job.status != ResearchServiceJobStatus.AWAITING_QUOTE.value:
        raise HTTPException(status_code=409, detail="Service Job is not awaiting a quote")
    if job.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Service Job has changed")
    try:
        budget = await validate_quote_budget(
            db_session, task=task, amount=params.amount, currency=params.currency
        )
    except ResearchBudgetError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    command = _quote_command(job, params)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "budget_after_approval": budget,
        "effects": [
            "Store the quote as an immutable provider response",
            "Request approval for the exact quote and pinned request",
            "Reserve budget only after approval",
        ],
    }


@router.post("/research-service-jobs/{job_id}/quotes")
async def create_service_quote(
    job_id: UUID,
    params: ServiceQuoteCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    job, action, run, task, _project_context, _lab = await _job_context(
        db_session, current_user, job_id, lock=True, manage=True
    )
    if task.status != ResearchTaskStatus.ACTIVE.value:
        raise HTTPException(status_code=409, detail="Research Task must be active")
    if job.status != ResearchServiceJobStatus.AWAITING_QUOTE.value:
        raise HTTPException(status_code=409, detail="Service Job is not awaiting a quote")
    if job.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Service Job has changed")
    command = _quote_command(job, params)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="Service quote preview changed")
    try:
        await validate_quote_budget(
            db_session, task=task, amount=params.amount, currency=params.currency
        )
    except ResearchBudgetError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    revision_number = (job.current_quote_revision or 0) + 1
    quote = ResearchServiceQuote(
        service_job_id=job.id,
        revision=revision_number,
        amount=params.amount,
        currency=params.currency,
        provider_quote_ref=params.provider_quote_ref,
        valid_until=params.valid_until,
        terms=params.terms,
        source="provider",
        quote_digest=params.preview_digest,
        created_by_user_id=current_user.id,
    )
    db_session.add(quote)
    await db_session.flush()
    await request_service_order_approval(
        db_session,
        task=task,
        run=run,
        action=action,
        job=job,
        quote=quote,
        requested_by_user_id=current_user.id,
        actor_user_id=current_user.id,
    )
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="external_service.quote_recorded",
        actor_user_id=current_user.id,
        payload={
            "service_job_id": str(job.id),
            "quote_id": str(quote.id),
            "quote_revision": quote.revision,
            "amount": str(quote.amount),
            "currency": quote.currency,
        },
        idempotency_key=f"service-job:{job.id}:quote:{quote.revision}:recorded",
    )
    await db_session.commit()
    return await service_job_snapshot(db_session, job)


@router.post("/research-service-jobs/{job_id}/progress/preview")
async def preview_service_progress(
    job_id: UUID,
    params: ServiceProgressDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    job, _action, _run, _task, _project_context, _lab = await _job_context(
        db_session, current_user, job_id, lock=False, manage=True
    )
    if job.status not in {
        ResearchServiceJobStatus.ORDERED.value,
        ResearchServiceJobStatus.IN_FULFILLMENT.value,
    }:
        raise HTTPException(status_code=409, detail="Service Job is not in fulfilment")
    if job.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Service Job has changed")
    command = _progress_command(job, params)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "effects": [
            (
                "Record provider progress without completing scientific work"
                if params.status == "in_fulfillment"
                else "Fail the Action, release its reserved quote, and resume planning"
            )
        ],
    }


@router.post("/research-service-jobs/{job_id}/progress")
async def create_service_progress(
    job_id: UUID,
    params: ServiceProgressCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    job, action, run, task, _project_context, _lab = await _job_context(
        db_session, current_user, job_id, lock=True, manage=True
    )
    if job.status not in {
        ResearchServiceJobStatus.ORDERED.value,
        ResearchServiceJobStatus.IN_FULFILLMENT.value,
    }:
        raise HTTPException(status_code=409, detail="Service Job is not in fulfilment")
    if job.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Service Job has changed")
    command = _progress_command(job, params)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="Service progress preview changed")
    now = utcnow()
    job.external_order_ref = params.external_order_ref or job.external_order_ref
    job.provider_status = params.provider_status
    job.expected_completion_at = params.expected_completion_at or job.expected_completion_at
    job.revision += 1
    if params.status == "failed":
        try:
            await release_service_budget(
                db_session,
                task=task,
                run=run,
                action=action,
                job=job,
                actor_user_id=current_user.id,
                suffix="failure-release",
            )
        except ResearchBudgetError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        job.status = ResearchServiceJobStatus.FAILED.value
        job.error = params.reason
        job.completed_at = now
        action.status = ResearchActionStatus.FAILED.value
        action.error = params.reason
        action.completed_at = now
        action.revision += 1
        append_aira_result(
            run,
            "service_results",
            {
                "action_id": str(action.id),
                "service_job_id": str(job.id),
                "status": "failed",
                "error": params.reason,
            },
        )
        graph_settled = await hold_or_release_aira_action_group(
            db_session,
            task=task,
            run=run,
            action=action,
        )
        if graph_settled and task.status == ResearchTaskStatus.ACTIVE.value:
            run.status = ResearchRunStatus.RUNNING.value
            run.last_error = None
            if config.effective_ai_enabled:
                await enqueue_research_advance(db_session, task=task, run=run)
            else:
                run.last_error = "AI is disabled; continue this Research Task manually."
                await emit_research_event(
                    db_session,
                    task_id=task.id,
                    run_id=run.id,
                    action_id=action.id,
                    kind="run.manual_control_required",
                    actor_user_id=None,
                    payload={"source": "external_service", "status": "failed"},
                    idempotency_key=f"service-job:{job.id}:manual-control:failed",
                )
        event_kind = "external_service.failed"
    else:
        job.status = ResearchServiceJobStatus.IN_FULFILLMENT.value
        job.started_at = job.started_at or now
        action.status = ResearchActionStatus.WAITING.value
        action.output_data = {
            **(action.output_data or {}),
            "service_job_id": str(job.id),
            "status": job.status,
            "external_order_ref": job.external_order_ref,
            "provider_status": job.provider_status,
            "expected_completion_at": (
                job.expected_completion_at.isoformat()
                if job.expected_completion_at
                else None
            ),
        }
        action.revision += 1
        event_kind = "external_service.in_fulfillment"
    task.revision += 1
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind=event_kind,
        actor_user_id=current_user.id,
        payload={
            "service_job_id": str(job.id),
            "external_order_ref": job.external_order_ref,
            "provider_status": job.provider_status,
            "reason": params.reason,
        },
        idempotency_key=f"service-job:{job.id}:revision:{job.revision}:{params.status}",
    )
    await db_session.commit()
    return await service_job_snapshot(db_session, job)


async def _custody_resource(
    db_session: DBSession,
    *,
    user: User,
    lab: Lab,
    params: ServiceCustodyDraft,
) -> tuple[Resource, ResourceContainer | None]:
    resource = await db_session.get(Resource, params.resource_id)
    if resource is None or resource.lab_id != lab.id or resource.archived_at is not None:
        raise HTTPException(status_code=404, detail="Custody resource not found")
    access = await resolve_resource_access(
        db_session,
        user.id,
        lab.id,
        resource_type_id=resource.resource_type_id,
        resource_id=resource.id,
    )
    if not access.allows("resource.custody"):
        raise HTTPException(status_code=403, detail="Resource custody access denied")
    if resource.visibility == ResourceVisibility.RESTRICTED.value and not any(
        source.scope_type in {"resource", "resource_type"}
        or source.role_key in {"lab_owner", "lab_admin"}
        for source in access.sources
    ):
        raise HTTPException(status_code=404, detail="Custody resource not found")
    container = None
    if params.container_id is not None:
        container = await db_session.get(ResourceContainer, params.container_id)
        if (
            container is None
            or container.lab_id != lab.id
            or container.resource_id != resource.id
            or container.archived_at is not None
        ):
            raise HTTPException(status_code=404, detail="Custody container not found")
    return resource, container


@router.post("/research-service-jobs/{job_id}/custody/preview")
async def preview_service_custody(
    job_id: UUID,
    params: ServiceCustodyDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    job, _action, _run, _task, _project_context, lab = await _job_context(
        db_session, current_user, job_id, lock=False, manage=True
    )
    if job.status not in {
        ResearchServiceJobStatus.ORDERED.value,
        ResearchServiceJobStatus.IN_FULFILLMENT.value,
    }:
        raise HTTPException(status_code=409, detail="Approve the service order first")
    if job.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Service Job has changed")
    resource, container = await _custody_resource(
        db_session, user=current_user, lab=lab, params=params
    )
    sequence = (
        await db_session.scalar(
            select(func.max(ResearchServiceCustodyEvent.sequence)).where(
                ResearchServiceCustodyEvent.service_job_id == job.id
            )
        )
        or 0
    ) + 1
    command = _custody_command(job, sequence, params)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "resource": {
            "id": str(resource.id),
            "name": resource.name,
            "code": resource.code,
            "container_id": str(container.id) if container else None,
            "container_code": container.code if container else None,
        },
        "effects": [
            "Append an immutable sample custody checkpoint",
            "Do not change inventory quantity or imply scientific acceptance",
        ],
    }


@router.post("/research-service-jobs/{job_id}/custody")
async def create_service_custody(
    job_id: UUID,
    params: ServiceCustodyCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    job, action, run, task, _project_context, lab = await _job_context(
        db_session, current_user, job_id, lock=True, manage=True
    )
    if job.status not in {
        ResearchServiceJobStatus.ORDERED.value,
        ResearchServiceJobStatus.IN_FULFILLMENT.value,
    }:
        raise HTTPException(status_code=409, detail="Approve the service order first")
    if job.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Service Job has changed")
    await _custody_resource(db_session, user=current_user, lab=lab, params=params)
    sequence = (
        await db_session.scalar(
            select(func.max(ResearchServiceCustodyEvent.sequence)).where(
                ResearchServiceCustodyEvent.service_job_id == job.id
            )
        )
        or 0
    ) + 1
    command = _custody_command(job, sequence, params)
    digest = canonical_digest(command)
    if digest != params.preview_digest:
        raise HTTPException(status_code=409, detail="Custody preview changed")
    event = ResearchServiceCustodyEvent(
        service_job_id=job.id,
        sequence=sequence,
        kind=params.kind,
        resource_id=params.resource_id,
        container_id=params.container_id,
        from_party=params.from_party,
        to_party=params.to_party,
        location=params.location,
        carrier=params.carrier,
        tracking_ref=params.tracking_ref,
        condition=params.condition,
        notes=params.notes,
        occurred_at=params.occurred_at,
        event_digest=digest,
        actor_user_id=current_user.id,
    )
    db_session.add(event)
    job.revision += 1
    task.revision += 1
    await db_session.flush()
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="external_service.custody_recorded",
        actor_user_id=current_user.id,
        payload={
            "service_job_id": str(job.id),
            "custody_event_id": str(event.id),
            "sequence": event.sequence,
            "kind": event.kind,
            "resource_id": str(event.resource_id),
        },
        idempotency_key=f"service-custody:{event.id}:recorded",
    )
    await db_session.commit()
    return await service_job_snapshot(db_session, job)


@router.post("/research-service-jobs/{job_id}/result/preview")
async def preview_service_result(
    job_id: UUID,
    params: ServiceResultDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    job, _action, _run, task, _project_context, _lab = await _job_context(
        db_session, current_user, job_id, lock=False, manage=True
    )
    if job.status not in {
        ResearchServiceJobStatus.ORDERED.value,
        ResearchServiceJobStatus.IN_FULFILLMENT.value,
    }:
        raise HTTPException(status_code=409, detail="Service Job cannot accept a result")
    if job.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Service Job has changed")
    try:
        validate_schema_payload(job.result_schema, params.result, "service result")
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    quote = await latest_service_quote(db_session, job.id)
    if quote is None:
        raise HTTPException(status_code=409, detail="Approved service quote not found")
    await _result_asset_versions(
        db_session, task=task, ids=params.data_asset_version_ids
    )
    command = _result_command(job, quote, params)
    actual_amount = Decimal(command["actual_amount"])
    if actual_amount > Decimal(quote.amount):
        raise HTTPException(
            status_code=409,
            detail="Actual service cost exceeds the approved quote; obtain a new approval",
        )
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "effects": [
            "Validate the result against the pinned result contract",
            "Link exact DataAsset versions without declaring them validated Evidence",
            "Replace the approved budget reservation with the confirmed actual cost",
            "Complete the Action and resume the Research Run",
        ],
    }


@router.post("/research-service-jobs/{job_id}/result")
async def create_service_result(
    job_id: UUID,
    params: ServiceResultCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    job, action, run, task, _project_context, _lab = await _job_context(
        db_session, current_user, job_id, lock=True, manage=True
    )
    if job.status not in {
        ResearchServiceJobStatus.ORDERED.value,
        ResearchServiceJobStatus.IN_FULFILLMENT.value,
    }:
        raise HTTPException(status_code=409, detail="Service Job cannot accept a result")
    if job.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Service Job has changed")
    try:
        validate_schema_payload(job.result_schema, params.result, "service result")
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    quote = await latest_service_quote(db_session, job.id, lock=True)
    if quote is None:
        raise HTTPException(status_code=409, detail="Approved service quote not found")
    assets = await _result_asset_versions(
        db_session, task=task, ids=params.data_asset_version_ids
    )
    command = _result_command(job, quote, params)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="Service result preview changed")
    actual_amount = Decimal(command["actual_amount"])
    try:
        await settle_service_budget(
            db_session,
            task=task,
            run=run,
            action=action,
            job=job,
            actual_amount=actual_amount,
            actor_user_id=current_user.id,
        )
    except ResearchBudgetError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    for version, _asset in assets:
        db_session.add(
            ResearchServiceResultAsset(
                service_job_id=job.id,
                data_asset_version_id=version.id,
            )
        )
    now = utcnow()
    job.result = params.result
    job.actual_amount = actual_amount
    job.status = ResearchServiceJobStatus.COMPLETED.value
    job.completed_at = now
    job.revision += 1
    action.status = ResearchActionStatus.COMPLETED.value
    action.output_data = {
        "service_job_id": str(job.id),
        "status": job.status,
        "result": params.result,
        "data_asset_version_ids": [str(item) for item in params.data_asset_version_ids],
        "actual_amount": str(actual_amount),
        "currency": quote.currency,
    }
    action.completed_at = now
    action.revision += 1
    append_aira_result(
        run,
        "service_results",
        {
            "action_id": str(action.id),
            "service_job_id": str(job.id),
            "service": job.offering_snapshot,
            "status": "completed",
            "result": params.result,
            "data_asset_version_ids": [str(item) for item in params.data_asset_version_ids],
        },
    )
    graph_settled = await hold_or_release_aira_action_group(
        db_session,
        task=task,
        run=run,
        action=action,
    )
    if graph_settled and task.status == ResearchTaskStatus.ACTIVE.value:
        run.status = ResearchRunStatus.RUNNING.value
        run.last_error = None
        if config.effective_ai_enabled:
            await enqueue_research_advance(db_session, task=task, run=run)
        else:
            run.last_error = "AI is disabled; continue this Research Task manually."
            await emit_research_event(
                db_session,
                task_id=task.id,
                run_id=run.id,
                action_id=action.id,
                kind="run.manual_control_required",
                actor_user_id=None,
                payload={"source": "external_service", "status": "completed"},
                idempotency_key=f"service-job:{job.id}:manual-control:completed",
            )
    task.revision += 1
    await db_session.flush()
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="external_service.completed",
        actor_user_id=current_user.id,
        payload={
            "service_job_id": str(job.id),
            "quote_id": str(quote.id),
            "actual_amount": str(actual_amount),
            "currency": quote.currency,
            "data_asset_version_ids": [str(item) for item in params.data_asset_version_ids],
        },
        idempotency_key=f"service-job:{job.id}:completed",
    )
    await db_session.commit()
    return await service_job_snapshot(db_session, job)
