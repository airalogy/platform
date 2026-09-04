import hashlib
import json
from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Request
from masterbrain.fastapi.usage import (
    UsageContextMiddleware,
    default_usage_context_factory,
)
from masterbrain.usage import (
    ModelUsageEvent as MasterbrainUsageEvent,
)
from masterbrain.usage import (
    UsageContext,
    configure_usage_sinks,
    get_usage_context,
)
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import sessionmanager
from app.libs.request_context import request_id_var
from app.models.model_usage import ModelUsageEvent
from app.models.research import (
    ResearchEvent,
    ResearchRun,
    ResearchRunStatus,
    ResearchTask,
    ResearchTaskOutcome,
    ResearchTaskStatus,
)
from app.models.research_execution import ResearchBudgetEntry, ResearchBudgetEntryKind
from app.services.research_budget import research_budget_snapshot

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

TERMINAL_RESEARCH_RUN_STATUSES = {
    ResearchRunStatus.COMPLETED.value,
    ResearchRunStatus.FAILED.value,
    ResearchRunStatus.CANCELLED.value,
}


def _optional_uuid(value: str | UUID | None) -> UUID | None:
    if value is None:
        return None
    return value if isinstance(value, UUID) else UUID(str(value))


def create_usage_context(
    *,
    feature: str,
    user_id: str | UUID,
    lab_id: str | UUID | None = None,
    project_id: str | UUID | None = None,
    chat_id: str | UUID | None = None,
    parent_operation_id: str | None = None,
    attributes: Mapping[str, str] | None = None,
) -> UsageContext:
    """Create metering identity only from authenticated Platform state."""

    return UsageContext(
        request_id=request_id_var.get(),
        parent_operation_id=parent_operation_id,
        feature=feature,
        tenant_id=str(lab_id) if lab_id is not None else None,
        user_id=str(user_id),
        project_id=str(project_id) if project_id is not None else None,
        chat_id=str(chat_id) if chat_id is not None else None,
        attributes=dict(attributes or {}),
    )


def platform_usage_context_factory(request: Request) -> UsageContext:
    """Preserve the trusted context bound by the in-process Platform caller."""

    return get_usage_context() or default_usage_context_factory(request)


def configure_embedded_masterbrain_app(app: FastAPI) -> None:
    """Replace correlation-only middleware with Platform's trusted factory."""

    matching_middleware = [
        middleware
        for middleware in app.user_middleware
        if middleware.cls is UsageContextMiddleware
    ]
    if len(matching_middleware) != 1:
        raise RuntimeError(
            "Expected exactly one Masterbrain UsageContextMiddleware instance"
        )
    if app.middleware_stack is not None:
        raise RuntimeError(
            "Masterbrain usage context must be configured before its first request"
        )
    matching_middleware[0].kwargs["context_factory"] = platform_usage_context_factory


def usage_event_values(event: MasterbrainUsageEvent) -> dict[str, Any]:
    usage = event.usage
    context = event.context
    json_event = event.to_dict()

    return {
        "event_id": event.event_id,
        "call_id": event.call_id,
        "operation_id": context.operation_id,
        "request_id": context.request_id,
        "parent_operation_id": context.parent_operation_id,
        "feature": context.feature,
        "lab_id": _optional_uuid(context.tenant_id),
        "user_id": _optional_uuid(context.user_id),
        "project_id": _optional_uuid(context.project_id),
        "chat_id": _optional_uuid(context.chat_id),
        "context_attributes": dict(context.attributes),
        "call_type": event.call_type,
        "status": event.status,
        "provider": usage.provider,
        "requested_model": usage.requested_model,
        "resolved_model": usage.resolved_model,
        "usage_source": usage.source,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
        "cached_input_tokens": usage.cached_input_tokens,
        "cache_creation_input_tokens": usage.cache_creation_input_tokens,
        "reasoning_tokens": usage.reasoning_tokens,
        "audio_input_tokens": usage.audio_input_tokens,
        "audio_output_tokens": usage.audio_output_tokens,
        "accepted_prediction_tokens": usage.accepted_prediction_tokens,
        "rejected_prediction_tokens": usage.rejected_prediction_tokens,
        "audio_seconds": usage.audio_seconds,
        "provider_cost": usage.provider_cost,
        "provider_cost_currency": usage.provider_cost_currency,
        "provider_cost_source": usage.provider_cost_source,
        "provider_request_id": event.provider_request_id,
        "error_type": event.error_type,
        "raw_usage": json_event["usage"]["raw_usage"],
        "metadata": dict(event.metadata),
        "started_at": event.started_at,
        "ended_at": event.ended_at,
        "latency_ms": event.latency_ms,
    }


def research_model_cost_context(
    event: MasterbrainUsageEvent,
) -> dict[str, Any] | None:
    """Return trusted, ledger-ready model cost identity for a Research Task."""

    task_id = event.context.attributes.get("task_id")
    cost = event.usage.provider_cost
    raw_currency = event.usage.provider_cost_currency
    if (
        not (event.context.feature or "").startswith("research.")
        or task_id is None
        or cost is None
        or raw_currency is None
    ):
        return None
    try:
        normalized_task_id = UUID(str(task_id))
        normalized_run_id = _optional_uuid(event.context.attributes.get("run_id"))
        normalized_user_id = _optional_uuid(event.context.user_id)
        amount = Decimal(cost)
    except (TypeError, ValueError):
        return None
    currency = str(raw_currency).strip().upper()
    if (
        amount <= 0
        or len(currency) != 3
        or not currency.isascii()
        or not currency.isalpha()
    ):
        return None
    command = {
        "operation": "research_model_usage_cost",
        "event_id": event.event_id,
        "task_id": str(normalized_task_id),
        "run_id": str(normalized_run_id) if normalized_run_id is not None else None,
        "feature": event.context.feature,
        "provider": event.usage.provider,
        "model": event.usage.resolved_model,
        "amount": format(amount.normalize(), "f"),
        "currency": currency,
        "cost_source": event.usage.provider_cost_source,
    }
    command_digest = hashlib.sha256(
        json.dumps(
            command,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return {
        **command,
        "task_uuid": normalized_task_id,
        "run_uuid": normalized_run_id,
        "user_uuid": normalized_user_id,
        "amount_decimal": amount,
        "command_digest": command_digest,
    }


async def record_research_model_cost(
    db_session: AsyncSession,
    *,
    event: MasterbrainUsageEvent,
) -> bool:
    """Append one same-currency provider cost and enforce the Task stop gate."""

    context = research_model_cost_context(event)
    if context is None:
        return False
    task = (
        await db_session.scalars(
            select(ResearchTask)
            .where(ResearchTask.id == context["task_uuid"])
            .with_for_update()
        )
    ).first()
    if (
        task is None
        or task.budget_limit is None
        or task.budget_currency != context["currency"]
    ):
        return False
    idempotency_key = f"model-usage:{event.event_id}"
    existing = await ResearchBudgetEntry.find_by(
        db_session,
        [
            ResearchBudgetEntry.task_id == task.id,
            ResearchBudgetEntry.idempotency_key == idempotency_key,
        ],
    )
    if existing is not None:
        return False

    run = None
    if context["run_uuid"] is not None:
        run = (
            await db_session.scalars(
                select(ResearchRun)
                .where(
                    ResearchRun.id == context["run_uuid"],
                    ResearchRun.task_id == task.id,
                )
                .with_for_update()
            )
        ).first()
    entry = ResearchBudgetEntry(
        task_id=task.id,
        run_id=run.id if run is not None else None,
        action_id=None,
        kind=ResearchBudgetEntryKind.EXPENSE.value,
        amount=context["amount_decimal"],
        currency=context["currency"],
        source_type="model_usage",
        source_ref=event.event_id,
        description=(
            f"{event.context.feature or 'research'} model usage: "
            f"{event.usage.provider}/{event.usage.resolved_model}"
        ),
        command_digest=context["command_digest"],
        created_by_user_id=context["user_uuid"],
        idempotency_key=idempotency_key,
    )
    db_session.add(entry)
    await db_session.flush()
    budget = await research_budget_snapshot(db_session, task=task)
    db_session.add(
        ResearchEvent(
            task_id=task.id,
            run_id=run.id if run is not None else None,
            kind="model.usage_cost_recorded",
            actor_user_id=context["user_uuid"],
            payload={
                "usage_event_id": event.event_id,
                "feature": event.context.feature,
                "provider": event.usage.provider,
                "model": event.usage.resolved_model,
                "amount": context["amount"],
                "currency": context["currency"],
                "cost_source": event.usage.provider_cost_source,
            },
            idempotency_key=f"model-usage:{event.event_id}:cost-recorded",
        )
    )

    if (
        run is not None
        and run.status not in TERMINAL_RESEARCH_RUN_STATUSES
        and budget["remaining"] is not None
        and Decimal(budget["remaining"]) <= 0
    ):
        already_budget_paused = (
            run.status == ResearchRunStatus.PAUSED.value
            and task.status == ResearchTaskStatus.PAUSED.value
            and task.outcome == ResearchTaskOutcome.STOPPED_BUDGET.value
        )
        run.status = ResearchRunStatus.PAUSED.value
        run.last_error = "Research Task budget limit reached after model usage"
        task.status = ResearchTaskStatus.PAUSED.value
        task.outcome = ResearchTaskOutcome.STOPPED_BUDGET.value
        if not already_budget_paused:
            task.revision += 1
            db_session.add(
                ResearchEvent(
                    task_id=task.id,
                    run_id=run.id,
                    kind="run.operational_limit_reached",
                    actor_user_id=context["user_uuid"],
                    payload={
                        "limit": "budget",
                        "snapshot": budget,
                        "source": "model_usage",
                        "usage_event_id": event.event_id,
                    },
                    idempotency_key=(
                        f"run:{run.id}:limit:budget:model-usage:{event.event_id}"
                    ),
                )
            )
    return True


class PlatformUsageSink:
    """Persist Masterbrain events in their own idempotent DB transaction."""

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self._session_factory = session_factory or sessionmanager.session

    async def record_usage(self, event: MasterbrainUsageEvent) -> None:
        usage_table = ModelUsageEvent.__table__
        statement = (
            insert(usage_table)
            .values(**usage_event_values(event))
            .on_conflict_do_nothing(index_elements=[usage_table.c.event_id])
        )
        async with self._session_factory() as session:
            await session.execute(statement)
            await session.commit()
        if research_model_cost_context(event) is not None:
            async with self._session_factory() as session:
                await record_research_model_cost(session, event=event)
                await session.commit()


_platform_usage_sink = PlatformUsageSink()


def configure_platform_usage_tracking() -> None:
    configure_usage_sinks(_platform_usage_sink)


def clear_platform_usage_tracking() -> None:
    configure_usage_sinks()
