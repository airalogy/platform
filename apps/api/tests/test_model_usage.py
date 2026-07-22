import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, Request
from masterbrain.fastapi.usage import install_usage_context_middleware
from masterbrain.usage import (
    InMemoryUsageSink,
    ModelUsage,
    ModelUsageEvent,
    UsageCallTracker,
    UsageContext,
    bind_usage_context,
    bind_usage_sinks,
    get_usage_context,
)
from sqlalchemy.dialects import postgresql

from app.libs import masterbrain as masterbrain_client
from app.libs.request_context import request_id_var
from app.models.model_usage import ModelUsageEvent as StoredModelUsageEvent
from app.services.model_usage import (
    PlatformUsageSink,
    configure_embedded_masterbrain_app,
    create_usage_context,
    platform_usage_context_factory,
    usage_event_values,
)


def _usage_event(*, with_cost: bool = True) -> ModelUsageEvent:
    now = datetime.now(UTC)
    return ModelUsageEvent(
        event_id=str(uuid4()),
        call_id=str(uuid4()),
        context=UsageContext(
            operation_id=str(uuid4()),
            request_id="request-1",
            feature="chat.qa",
            tenant_id=str(uuid4()),
            user_id=str(uuid4()),
            project_id=str(uuid4()),
            chat_id=str(uuid4()),
            attributes={"surface": "recorder"},
        ),
        call_type="chat.completion",
        status="succeeded",
        usage=ModelUsage(
            provider="qwen",
            requested_model="qwen3.5-flash",
            resolved_model="qwen3.5-flash-2026-07-01",
            input_tokens=1200,
            output_tokens=300,
            cached_input_tokens=800,
            reasoning_tokens=100,
            total_tokens=1500,
            provider_cost=Decimal("0.0025") if with_cost else None,
            provider_cost_currency="CNY" if with_cost else None,
            provider_cost_source="provider" if with_cost else None,
            source="provider",
            raw_usage={"prompt_tokens": 1200, "completion_tokens": 300},
        ),
        started_at=now,
        ended_at=now,
        latency_ms=240,
        provider_request_id="provider-request-1",
        metadata={"transport": "litellm"},
    )


def test_usage_event_values_preserve_metering_and_optional_cost():
    event = _usage_event(with_cost=False)

    values = usage_event_values(event)

    assert values["event_id"] == event.event_id
    assert values["lab_id"] == UUID(event.context.tenant_id)
    assert values["user_id"] == UUID(event.context.user_id)
    assert values["input_tokens"] == 1200
    assert values["cached_input_tokens"] == 800
    assert values["provider_cost"] is None
    assert values["provider_cost_currency"] is None
    assert values["raw_usage"] == {
        "prompt_tokens": 1200,
        "completion_tokens": 300,
    }

    priced_values = usage_event_values(_usage_event())
    assert priced_values["provider_cost"] == Decimal("0.0025")
    assert priced_values["provider_cost_currency"] == "CNY"
    assert priced_values["provider_cost_source"] == "provider"


def test_create_usage_context_uses_server_request_and_authenticated_identity():
    user_id = uuid4()
    lab_id = uuid4()
    project_id = uuid4()
    chat_id = uuid4()
    token = request_id_var.set("platform-request-id")
    try:
        context = create_usage_context(
            feature="chat.qa",
            user_id=user_id,
            lab_id=lab_id,
            project_id=project_id,
            chat_id=chat_id,
        )
    finally:
        request_id_var.reset(token)

    assert context.request_id == "platform-request-id"
    assert context.user_id == str(user_id)
    assert context.tenant_id == str(lab_id)
    assert context.project_id == str(project_id)
    assert context.chat_id == str(chat_id)


def test_platform_factory_preserves_bound_context_and_ignores_identity_headers():
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/chat",
            "headers": [
                (b"x-platform-user-id", str(uuid4()).encode()),
                (b"x-masterbrain-operation-id", b"client-operation"),
            ],
            "query_string": b"",
            "server": ("test", 80),
            "client": ("test", 123),
            "scheme": "http",
        }
    )
    trusted_context = UsageContext(
        operation_id="trusted-operation",
        user_id=str(uuid4()),
    )

    with bind_usage_context(trusted_context):
        assert platform_usage_context_factory(request) is trusted_context

    unbound_context = platform_usage_context_factory(request)
    assert unbound_context.operation_id == "client-operation"
    assert unbound_context.user_id is None


def test_embedded_masterbrain_app_uses_platform_context_factory():
    app = FastAPI()
    install_usage_context_middleware(app)

    configure_embedded_masterbrain_app(app)

    middleware = next(
        item
        for item in app.user_middleware
        if item.cls.__name__ == "UsageContextMiddleware"
    )
    assert middleware.kwargs["context_factory"] is platform_usage_context_factory


def test_platform_usage_sink_uses_idempotent_insert():
    statements = []
    commits = 0

    class FakeSession:
        async def execute(self, statement):
            statements.append(statement)

        async def commit(self):
            nonlocal commits
            commits += 1

    @asynccontextmanager
    async def session_factory():
        yield FakeSession()

    asyncio.run(PlatformUsageSink(session_factory).record_usage(_usage_event()))

    assert commits == 1
    compiled = statements[0].compile(dialect=postgresql.dialect())
    assert "ON CONFLICT (event_id) DO NOTHING" in str(compiled)


def test_usage_model_is_append_only_without_operational_foreign_keys():
    table = StoredModelUsageEvent.__table__

    assert not table.c.lab_id.foreign_keys
    assert not table.c.user_id.foreign_keys
    assert not table.c.project_id.foreign_keys
    assert not table.c.chat_id.foreign_keys
    assert {
        constraint.name
        for constraint in table.constraints
        if constraint.name is not None
    } >= {
        "ck_model_usage_events_status",
        "ck_model_usage_events_usage_source",
        "ck_model_usage_events_non_negative_tokens",
    }


def test_json_request_binds_usage_context_and_correlation_headers(monkeypatch):
    app = FastAPI()
    install_usage_context_middleware(app)
    configure_embedded_masterbrain_app(app)
    captured = {}
    sink = InMemoryUsageSink()

    @app.post("/api/test")
    async def inspect_context(request: Request):
        captured["context"] = get_usage_context()
        captured["operation_id"] = request.headers.get(
            "X-Masterbrain-Operation-Id"
        )
        captured["request_id"] = request.headers.get("X-Request-Id")
        tracker = UsageCallTracker(
            provider="qwen",
            requested_model="qwen3.5-flash",
            call_type="chat.completion",
        )
        await tracker.succeed(
            resolved_model="qwen3.5-flash-2026-07-01",
            raw_usage={"prompt_tokens": 4, "completion_tokens": 2},
        )
        return {"ok": True}

    @asynccontextmanager
    async def mock_masterbrain_client():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://masterbrain.local",
        ) as client:
            yield client

    monkeypatch.setattr(
        masterbrain_client, "_masterbrain_client", mock_masterbrain_client
    )
    context = UsageContext(
        operation_id="operation-1",
        request_id="request-1",
        user_id=str(uuid4()),
    )

    with bind_usage_sinks(sink):
        result = asyncio.run(
            masterbrain_client.json_request(
                "test",
                {},
                usage_context=context,
            )
        )

    assert result == {"ok": True}
    assert captured == {
        "context": context,
        "operation_id": "operation-1",
        "request_id": "request-1",
    }
    assert len(sink.events) == 1
    assert sink.events[0].context is context
    assert sink.events[0].usage.input_tokens == 4
    assert sink.events[0].usage.output_tokens == 2
