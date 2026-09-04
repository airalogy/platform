"""Deterministic lifecycle helpers for external research-service Actions."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research import (
    ResearchAction,
    ResearchActionStatus,
    ResearchApproval,
    ResearchApprovalStatus,
    ResearchRun,
    ResearchRunStatus,
    ResearchTask,
)
from app.models.research_asset import DataAsset, DataAssetVersion
from app.models.research_execution import (
    ResearchBudgetEntry,
    ResearchBudgetEntryKind,
    ResearchServiceCustodyEvent,
    ResearchServiceJob,
    ResearchServiceJobStatus,
    ResearchServiceOffering,
    ResearchServiceOfferingRevision,
    ResearchServiceProvider,
    ResearchServiceQuote,
    ResearchServiceResultAsset,
)
from app.services.research_budget import (
    ResearchBudgetError,
    project_budget_change,
    research_budget_snapshot,
)
from app.services.research_instruments import validate_schema_payload
from app.services.research_runtime import canonical_digest, emit_research_event, utcnow

TERMINAL_SERVICE_JOB_STATUSES = {
    ResearchServiceJobStatus.COMPLETED.value,
    ResearchServiceJobStatus.FAILED.value,
    ResearchServiceJobStatus.CANCELLED.value,
}


def service_order_command(
    job: ResearchServiceJob, quote: ResearchServiceQuote
) -> dict[str, Any]:
    return {
        "operation": "approve_external_service_order",
        "service_job_id": str(job.id),
        "job_revision": job.revision,
        "provider_id": str(job.provider_id),
        "service_offering_id": str(job.service_offering_id),
        "service_offering_revision_id": str(job.service_offering_revision_id),
        "service_version": job.service_version,
        "request_payload": job.request_payload,
        "quote_id": str(quote.id),
        "quote_revision": quote.revision,
        "quote_digest": quote.quote_digest,
        "amount": str(quote.amount),
        "currency": quote.currency,
        "valid_until": quote.valid_until.isoformat() if quote.valid_until else None,
    }


async def request_service_order_approval(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
    action: ResearchAction,
    job: ResearchServiceJob,
    quote: ResearchServiceQuote,
    requested_by_user_id: UUID,
    actor_user_id: UUID | None,
    reason: str | None = None,
) -> ResearchApproval:
    """Move one exact quote into the shared digest-bound order gate."""

    job.status = ResearchServiceJobStatus.AWAITING_APPROVAL.value
    job.current_quote_revision = quote.revision
    job.revision += 1
    command = service_order_command(job, quote)
    action.preview_digest = canonical_digest(command)
    action.status = ResearchActionStatus.PROPOSED.value
    action.policy_decision = "ask"
    action.revision += 1
    approval = ResearchApproval(
        action_id=action.id,
        approver_user_id=task.owner_user_id,
        requested_by_user_id=requested_by_user_id,
        status=ResearchApprovalStatus.PENDING.value,
        preview_digest=action.preview_digest,
        reason=reason
        or f"Approve external service order for {quote.amount} {quote.currency}",
    )
    db_session.add(approval)
    run.status = ResearchRunStatus.WAITING_FOR_APPROVAL.value
    run.last_error = None
    task.revision += 1
    await db_session.flush()
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="approval.requested",
        actor_user_id=actor_user_id,
        payload={
            "approval_id": str(approval.id),
            "approver_user_id": str(approval.approver_user_id),
            "preview_digest": approval.preview_digest,
            "reason": approval.reason,
            "service_job_id": str(job.id),
            "quote_id": str(quote.id),
        },
        idempotency_key=f"service-job:{job.id}:quote:{quote.revision}:approval",
    )
    return approval


def _money(value: Decimal) -> str:
    return format(value.normalize(), "f") if value else "0"


async def latest_service_quote(
    db_session: AsyncSession,
    job_id: UUID,
    *,
    lock: bool = False,
) -> ResearchServiceQuote | None:
    statement = (
        select(ResearchServiceQuote)
        .where(ResearchServiceQuote.service_job_id == job_id)
        .order_by(ResearchServiceQuote.revision.desc())
        .limit(1)
    )
    if lock:
        statement = statement.with_for_update()
    return (await db_session.scalars(statement)).first()


async def service_job_snapshot(
    db_session: AsyncSession,
    job: ResearchServiceJob,
) -> dict[str, Any]:
    quote = await latest_service_quote(db_session, job.id)
    custody = list(
        (
            await db_session.scalars(
                select(ResearchServiceCustodyEvent)
                .where(ResearchServiceCustodyEvent.service_job_id == job.id)
                .order_by(ResearchServiceCustodyEvent.sequence)
            )
        ).all()
    )
    result_asset_rows = list(
        (
            await db_session.execute(
                select(ResearchServiceResultAsset, DataAssetVersion, DataAsset)
                .join(
                    DataAssetVersion,
                    DataAssetVersion.id
                    == ResearchServiceResultAsset.data_asset_version_id,
                )
                .join(DataAsset, DataAsset.id == DataAssetVersion.data_asset_id)
                .where(ResearchServiceResultAsset.service_job_id == job.id)
                .order_by(DataAsset.name, DataAssetVersion.version)
            )
        ).all()
    )
    return {
        **job.as_dict(),
        "actual_amount": (
            _money(Decimal(job.actual_amount))
            if job.actual_amount is not None
            else None
        ),
        "quote": (
            {
                **quote.as_dict(),
                "amount": _money(Decimal(quote.amount)),
            }
            if quote is not None
            else None
        ),
        "custody_events": [item.as_dict() for item in custody],
        "result_assets": [
            {
                "data_asset_version_id": str(link.data_asset_version_id),
                "data_asset_id": str(asset.id),
                "name": asset.name,
                "kind": asset.kind,
                "status": asset.status,
                "version": version.version,
            }
            for link, version, asset in result_asset_rows
        ],
    }


async def pinned_service_job_context(
    db_session: AsyncSession,
    *,
    run: ResearchRun,
    service_offering_id: UUID,
    lock: bool,
) -> tuple[
    dict[str, Any],
    ResearchServiceProvider,
    ResearchServiceOffering,
    ResearchServiceOfferingRevision,
]:
    pinned = next(
        (
            item
            for item in list((run.environment_snapshot or {}).get("services") or [])
            if str(item.get("source_id") or "") == str(service_offering_id)
        ),
        None,
    )
    if pinned is None:
        raise ValueError("Service is not pinned in this Research Environment")
    provider_id = UUID(str((pinned.get("metadata") or {}).get("provider", {}).get("id")))
    revision_id = UUID(str(pinned.get("source_revision_id")))
    offering_statement = select(ResearchServiceOffering).where(
        ResearchServiceOffering.id == service_offering_id
    )
    provider_statement = select(ResearchServiceProvider).where(
        ResearchServiceProvider.id == provider_id
    )
    revision_statement = select(ResearchServiceOfferingRevision).where(
        ResearchServiceOfferingRevision.id == revision_id
    )
    if lock:
        offering_statement = offering_statement.with_for_update()
        provider_statement = provider_statement.with_for_update()
        revision_statement = revision_statement.with_for_update()
    offering = (await db_session.scalars(offering_statement)).first()
    provider = (await db_session.scalars(provider_statement)).first()
    revision = (await db_session.scalars(revision_statement)).first()
    if offering is None or provider is None or revision is None:
        raise ValueError("Pinned external service contract is unavailable")
    if (
        offering.provider_id != provider.id
        or offering.lab_id != provider.lab_id
        or revision.offering_id != offering.id
        or revision.revision
        != int((pinned.get("metadata") or {}).get("offering_revision") or 0)
        or revision.service_version != str(pinned.get("version") or "")
    ):
        raise ValueError("Pinned external service contract no longer matches")
    if (
        provider.archived_at is not None
        or offering.archived_at is not None
        or not provider.enabled
        or not offering.enabled
    ):
        raise ValueError("Pinned external service is disabled")
    return pinned, provider, offering, revision


def pinned_service_executor_binding(
    *,
    task: ResearchTask,
    run: ResearchRun,
    pinned_service: dict[str, Any],
    provider_id: UUID,
) -> dict[str, Any]:
    """Resolve the Task-captured provider policy, with a legacy-safe default."""

    from app.services.research_executor_bindings import (
        derived_executor_binding,
        environment_executor_binding,
        validate_pinned_executor_target,
    )

    try:
        binding = environment_executor_binding(
            run.environment_snapshot or {},
            str(pinned_service["key"]),
            str(pinned_service["version"]),
            legacy_capability=pinned_service,
            owner_user_id=task.owner_user_id,
        )
    except ValueError as error:
        if "missing" not in str(error):
            raise
        # Environments captured before Service bindings existed keep their
        # original always-ask behavior; new Tasks always pin the exact policy.
        binding = derived_executor_binding(
            capability=pinned_service,
            owner_user_id=task.owner_user_id,
        )
    validate_pinned_executor_target(
        binding,
        executor_type="external_service",
        executor_ref_type="service_provider",
        executor_ref_id=provider_id,
        mode="governed_order",
    )
    return binding


async def validate_quote_budget(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    amount: Decimal,
    currency: str,
) -> dict[str, Any] | None:
    if task.budget_limit is None:
        return None
    snapshot = await research_budget_snapshot(db_session, task=task)
    return project_budget_change(
        task=task,
        snapshot=snapshot,
        kind=ResearchBudgetEntryKind.RESERVE.value,
        amount=amount,
        currency=currency,
    )


async def _append_budget_entry(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
    action: ResearchAction,
    job: ResearchServiceJob,
    quote: ResearchServiceQuote,
    kind: str,
    amount: Decimal,
    actor_user_id: UUID | None,
    suffix: str,
) -> ResearchBudgetEntry | None:
    if task.budget_limit is None or amount <= 0:
        return None
    idempotency_key = f"service-job:{job.id}:quote:{quote.revision}:{suffix}"
    existing = await ResearchBudgetEntry.find_by(
        db_session,
        [
            ResearchBudgetEntry.task_id == task.id,
            ResearchBudgetEntry.idempotency_key == idempotency_key,
        ],
    )
    if existing is not None:
        return existing
    entry_command = {
        "operation": f"external_service_budget_{kind}",
        "task_id": str(task.id),
        "run_id": str(run.id),
        "action_id": str(action.id),
        "service_job_id": str(job.id),
        "quote_id": str(quote.id),
        "quote_revision": quote.revision,
        "amount": _money(amount),
        "currency": quote.currency,
        "kind": kind,
    }
    entry = ResearchBudgetEntry(
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind=kind,
        amount=amount,
        currency=quote.currency,
        source_type="external_service_quote",
        source_ref=str(quote.id),
        description=f"External service {job.service_version}",
        command_digest=canonical_digest(entry_command),
        created_by_user_id=actor_user_id,
        idempotency_key=idempotency_key,
    )
    db_session.add(entry)
    return entry


async def activate_service_order(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
    action: ResearchAction,
    actor_user_id: UUID,
) -> tuple[ResearchServiceJob, ResearchServiceQuote]:
    job = (
        await db_session.scalars(
            select(ResearchServiceJob)
            .where(ResearchServiceJob.action_id == action.id)
            .with_for_update()
        )
    ).first()
    if job is None or job.status != ResearchServiceJobStatus.AWAITING_APPROVAL.value:
        raise ValueError("External service job is not awaiting approval")
    quote = await latest_service_quote(db_session, job.id, lock=True)
    if quote is None or quote.revision != job.current_quote_revision:
        raise ValueError("External service quote is unavailable")
    if canonical_digest(service_order_command(job, quote)) != action.preview_digest:
        raise ValueError("External service order approval is stale")
    now = utcnow()
    if quote.valid_until is not None and quote.valid_until <= now:
        raise ValueError("External service quote has expired")
    pinned_service, provider, _offering, _revision = await pinned_service_job_context(
        db_session,
        run=run,
        service_offering_id=job.service_offering_id,
        lock=True,
    )
    executor_binding = pinned_service_executor_binding(
        task=task,
        run=run,
        pinned_service=pinned_service,
        provider_id=provider.id,
    )
    captured_binding = dict((action.requirements or {}).get("executor_binding") or {})
    if captured_binding and canonical_digest(captured_binding) != canonical_digest(
        executor_binding
    ):
        raise ValueError("External Service Executor Binding changed after preview")
    validate_schema_payload(job.input_schema, job.request_payload, "service request")
    await validate_quote_budget(
        db_session,
        task=task,
        amount=Decimal(quote.amount),
        currency=quote.currency,
    )
    await _append_budget_entry(
        db_session,
        task=task,
        run=run,
        action=action,
        job=job,
        quote=quote,
        kind=ResearchBudgetEntryKind.RESERVE.value,
        amount=Decimal(quote.amount),
        actor_user_id=actor_user_id,
        suffix="reserve",
    )
    job.status = ResearchServiceJobStatus.ORDERED.value
    job.approved_at = now
    job.ordered_at = now
    sla_hours = (job.offering_snapshot.get("metadata") or {}).get("sla_hours")
    if sla_hours:
        job.expected_completion_at = now + timedelta(hours=int(sla_hours))
    job.revision += 1
    action.status = ResearchActionStatus.WAITING.value
    action.output_data = {
        "service_job_id": str(job.id),
        "status": job.status,
        "quote_id": str(quote.id),
        "amount": _money(Decimal(quote.amount)),
        "currency": quote.currency,
    }
    action.revision += 1
    run.status = ResearchRunStatus.WAITING_FOR_EVENT.value
    run.last_error = None
    return job, quote


async def release_service_budget(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
    action: ResearchAction,
    job: ResearchServiceJob,
    actor_user_id: UUID | None,
    suffix: str,
) -> ResearchBudgetEntry | None:
    quote = await latest_service_quote(db_session, job.id, lock=True)
    if quote is None:
        return None
    if task.budget_limit is not None and Decimal(quote.amount) > 0:
        snapshot = await research_budget_snapshot(db_session, task=task)
        project_budget_change(
            task=task,
            snapshot=snapshot,
            kind=ResearchBudgetEntryKind.RELEASE.value,
            amount=Decimal(quote.amount),
            currency=quote.currency,
        )
    return await _append_budget_entry(
        db_session,
        task=task,
        run=run,
        action=action,
        job=job,
        quote=quote,
        kind=ResearchBudgetEntryKind.RELEASE.value,
        amount=Decimal(quote.amount),
        actor_user_id=actor_user_id,
        suffix=suffix,
    )


async def settle_service_budget(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
    action: ResearchAction,
    job: ResearchServiceJob,
    actual_amount: Decimal,
    actor_user_id: UUID,
) -> None:
    quote = await latest_service_quote(db_session, job.id, lock=True)
    if quote is None:
        raise ResearchBudgetError("External service quote is unavailable")
    if actual_amount > Decimal(quote.amount):
        raise ResearchBudgetError(
            "Actual service cost exceeds the approved quote; obtain a new approval"
        )
    if task.budget_limit is not None and Decimal(quote.amount) > 0:
        snapshot = await research_budget_snapshot(db_session, task=task)
        released = project_budget_change(
            task=task,
            snapshot=snapshot,
            kind=ResearchBudgetEntryKind.RELEASE.value,
            amount=Decimal(quote.amount),
            currency=quote.currency,
        )
        if actual_amount > 0:
            project_budget_change(
                task=task,
                snapshot=released,
                kind=ResearchBudgetEntryKind.EXPENSE.value,
                amount=actual_amount,
                currency=quote.currency,
            )
    await _append_budget_entry(
        db_session,
        task=task,
        run=run,
        action=action,
        job=job,
        quote=quote,
        kind=ResearchBudgetEntryKind.RELEASE.value,
        amount=Decimal(quote.amount),
        actor_user_id=actor_user_id,
        suffix="settle-release",
    )
    await _append_budget_entry(
        db_session,
        task=task,
        run=run,
        action=action,
        job=job,
        quote=quote,
        kind=ResearchBudgetEntryKind.EXPENSE.value,
        amount=actual_amount,
        actor_user_id=actor_user_id,
        suffix="settle-expense",
    )
