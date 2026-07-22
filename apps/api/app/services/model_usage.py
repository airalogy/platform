from collections.abc import Callable, Mapping
from typing import Any, AsyncContextManager
from uuid import UUID

from fastapi import FastAPI, Request
from masterbrain.fastapi.usage import (
    UsageContextMiddleware,
    default_usage_context_factory,
)
from masterbrain.usage import (
    ModelUsageEvent as MasterbrainUsageEvent,
    UsageContext,
    configure_usage_sinks,
    get_usage_context,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import sessionmanager
from app.libs.request_context import request_id_var
from app.models.model_usage import ModelUsageEvent

SessionFactory = Callable[[], AsyncContextManager[AsyncSession]]


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


_platform_usage_sink = PlatformUsageSink()


def configure_platform_usage_tracking() -> None:
    configure_usage_sinks(_platform_usage_sink)


def clear_platform_usage_tracking() -> None:
    configure_usage_sinks()
