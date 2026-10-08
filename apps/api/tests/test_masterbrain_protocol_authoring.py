"""Exercise the installed release through Platform's transport, without model calls."""

import asyncio
import importlib
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app.libs import masterbrain
from app.models.chat import Chat, ChatType


@pytest.fixture
def authoring_app(monkeypatch):
    generation = importlib.import_module(
        "masterbrain.endpoints.single_protocol_file_generation.router"
    )
    editing = importlib.import_module("masterbrain.endpoints.code_edit.router")
    app = FastAPI()
    app.include_router(
        generation.single_protocol_file_generation_router, prefix="/api/endpoints"
    )
    app.include_router(editing.code_edit_router, prefix="/api/endpoints")

    @asynccontextmanager
    async def client():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://masterbrain.local"
        ) as transport:
            yield transport

    monkeypatch.setattr(masterbrain, "_masterbrain_client", client)
    monkeypatch.setattr(
        masterbrain, "_masterbrain_request_target", lambda path: f"/api/{path}"
    )
    return generation, editing


def test_platform_generation_opts_in_through_released_request_model(
    authoring_app, monkeypatch
):
    generation, _ = authoring_app
    stream_module = importlib.import_module(
        "masterbrain.endpoints.single_protocol_file_generation.logic.stream_generator"
    )
    captured = []

    async def create(**kwargs):
        captured.append(kwargs["messages"])

        async def chunks():
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="# Synthetic Protocol")
                    )
                ]
            )

        return chunks()

    monkeypatch.setattr(generation, "ensure_model_api_key", lambda _: None)
    monkeypatch.setattr(
        stream_module,
        "select_client",
        lambda _: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ),
    )
    chat = Chat(
        user_id=uuid.uuid4(),
        context={"instruction": "Create a synthetic area calculation"},
        messages=[],
        type=ChatType.PROTOCOL_GENERATE,
        model={"name": "qwen3.5-flash"},
        model_type=1,
    )

    async def generate():
        return "".join(
            [part async for part in masterbrain.protocol_generate_aimd(chat)]
        )

    assert asyncio.run(generate()) == "# Synthetic Protocol"
    assert "prefer_client_assigners=true" in captured[0][-1]["content"]
    assert "prefer client-side assigners" in captured[0][0]["content"]
    assert "trusted server verification" in captured[0][0]["content"]

    async def legacy_generate():
        return "".join(
            [
                part
                async for part in masterbrain.stream_request(
                    "endpoints/single_protocol_file_generation",
                    {"instruction": "Synthetic legacy host"},
                )
            ]
        )

    assert asyncio.run(legacy_generate()) == "# Synthetic Protocol"
    assert "prefer_client_assigners=false" in captured[1][-1]["content"]


def test_platform_code_edit_preference_survives_http_validation(
    authoring_app, monkeypatch
):
    from masterbrain.endpoints.code_edit.logic import build_code_edit_prompt
    from masterbrain.endpoints.code_edit.types import CodeEditOutput

    _, editing = authoring_app
    captured = []

    async def generate(payload):
        captured.append(build_code_edit_prompt(payload))
        return CodeEditOutput(message="Synthetic answer; no files changed")

    monkeypatch.setattr(editing, "generate_code_edit_result", generate)
    payload = {
        "model": {"name": "qwen3.5-flash"},
        "prompt": "Explain the calculation",
        "files": [],
    }
    result = asyncio.run(masterbrain.protocol_code_edit(payload))
    assert result["outcome"] == "answer"
    assert result["changed_files"] == []
    assert "prefer_client_assigners=true" in captured[0]
    assert "prefer_client_assigners" not in payload
