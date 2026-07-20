import asyncio
import uuid
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.config import config
from app.libs import masterbrain
from app.routers.chats.utils import build_chat_stream_error_data


def test_production_model_timeout_hides_exception_detail(monkeypatch):
    monkeypatch.setattr(config, "APP_ENV", "production")

    data = build_chat_stream_error_data(
        httpx.ReadTimeout("internal upstream timeout detail"),
        chat_id=uuid.uuid4(),
        model="qwen3.5-plus",
    )

    assert data["code"] == "MODEL_TIMEOUT"
    assert data["stage"] == "model"
    assert data["model"] == "qwen3.5-plus"
    assert data["retryable"] is True
    assert "debug" not in data


def test_development_model_error_includes_debug_detail(monkeypatch):
    monkeypatch.setattr(config, "APP_ENV", "development")

    data = build_chat_stream_error_data(
        HTTPException(status_code=401, detail="invalid upstream credential"),
        chat_id=uuid.uuid4(),
        model="gpt-4.1",
    )

    assert data["code"] == "MODEL_AUTHENTICATION_FAILED"
    assert data["http_status"] == 401
    assert data["retryable"] is False
    assert data["debug"] == {
        "exception": "HTTPException",
        "detail": "invalid upstream credential",
    }


def test_model_connection_failure_is_retryable(monkeypatch):
    monkeypatch.setattr(config, "APP_ENV", "production")
    request = httpx.Request("POST", "http://masterbrain.local/api/chat")

    data = build_chat_stream_error_data(
        httpx.ConnectError("connection refused", request=request),
        chat_id=uuid.uuid4(),
        model="qwen3.5-flash",
    )

    assert data["code"] == "MODEL_UNAVAILABLE"
    assert data["retryable"] is True


def test_stream_request_preserves_upstream_http_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={"detail": "upstream quota exceeded"},
            request=request,
        )

    @asynccontextmanager
    async def mock_masterbrain_client():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://masterbrain.local",
        ) as client:
            yield client

    async def consume_stream():
        return [chunk async for chunk in masterbrain.stream_request("chat", {})]

    monkeypatch.setattr(masterbrain, "_masterbrain_client", mock_masterbrain_client)

    with pytest.raises(HTTPException) as error:
        asyncio.run(consume_stream())

    assert error.value.status_code == 429
    assert error.value.detail == "upstream quota exceeded"


def test_stream_request_reads_package_transport_error_body(monkeypatch):
    app = FastAPI()

    @app.post("/api/chat")
    async def reject_request():
        return JSONResponse(
            status_code=400,
            content={"detail": "model request was rejected"},
        )

    @asynccontextmanager
    async def mock_masterbrain_client():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://masterbrain.local",
        ) as client:
            yield client

    async def consume_stream():
        return [chunk async for chunk in masterbrain.stream_request("chat", {})]

    monkeypatch.setattr(masterbrain, "_masterbrain_client", mock_masterbrain_client)

    with pytest.raises(HTTPException) as error:
        asyncio.run(consume_stream())

    assert error.value.status_code == 400
    assert error.value.detail == "model request was rejected"
