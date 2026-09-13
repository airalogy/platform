"""Offline tests of the Platform/Masterbrain model and index boundaries."""

import ast
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from fastapi import BackgroundTasks, FastAPI, HTTPException
from masterbrain.usage import InMemoryUsageSink, UsageContext, bind_usage_sinks
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.libs import masterbrain, text_splitter
from app.libs.embedding_config import EMBEDDING_DIMENSIONS
from app.models.embedding import Embedding, EmbeddingResourceType
from app.models.question import Question
from app.routers import questions
from app.services.model_usage import configure_embedded_masterbrain_app


def vector():
    return [0.1] * EMBEDDING_DIMENSIONS


def enable_embeddings(monkeypatch, enabled=True):
    settings = SimpleNamespace(effective_embeddings_enabled=enabled)
    monkeypatch.setattr(masterbrain, "config", settings)
    monkeypatch.setattr(text_splitter, "config", settings)


def test_all_builtin_model_sdks_are_owned_by_masterbrain():
    app_root = Path(__file__).resolve().parents[1] / "app"
    forbidden = {
        "openai",
        "litellm",
        "dashscope",
        "anthropic",
        "google.generativeai",
        "google.genai",
    }
    violations = []
    for path in app_root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            if any(
                name == provider or name.startswith(provider + ".")
                for name in names
                for provider in forbidden
            ):
                violations.append(f"{path.relative_to(app_root)}:{node.lineno}")
    assert not violations, (
        f"Built-in provider calls must go through Masterbrain: {violations}"
    )


def test_disabled_embeddings_cannot_reach_transport(monkeypatch):
    enable_embeddings(monkeypatch, False)
    send = AsyncMock(side_effect=AssertionError("must not send"))
    monkeypatch.setattr(masterbrain, "json_request", send)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(masterbrain.text_embeddings(["private text"]))
    assert exc.value.status_code == 503
    assert asyncio.run(text_splitter.optional_text_to_vectors(["private text"])) is None
    send.assert_not_awaited()


def test_batching_keeps_model_dimensions_and_identity(monkeypatch):
    enable_embeddings(monkeypatch)
    context = UsageContext(feature="index.protocol", user_id=str(uuid4()))
    calls = []

    async def send(path, data, **kwargs):
        calls.append((path, data, kwargs))
        return {
            "model": data["model"],
            "dimensions": data["dimensions"],
            "vectors": [vector() for _ in data["input"]],
        }

    monkeypatch.setattr(masterbrain, "json_request", send)
    texts = [f"paragraph {i}" for i in range(13)]
    result = asyncio.run(text_splitter.text_to_vectors(texts, usage_context=context))
    assert len(result) == 13
    assert [len(data["input"]) for _, data, _ in calls] == [6, 6, 1]
    assert [t for _, data, _ in calls for t in data["input"]] == texts
    assert all(
        path == "endpoints/embeddings"
        and data["model"] == "text-embedding-v4"
        and data["dimensions"] == 1024
        for path, data, _ in calls
    )
    assert all(kwargs["usage_context"] is context for _, _, kwargs in calls)
    assert asyncio.run(text_splitter.text_to_vectors([])) == []
    assert len(calls) == 3


@pytest.mark.parametrize(
    "result",
    [
        {"model": "wrong-model", "dimensions": 1024, "vectors": [vector()]},
        {"model": "text-embedding-v4", "dimensions": 1, "vectors": [[0.1]]},
        {
            "model": "text-embedding-v4",
            "dimensions": 1024,
            "vectors": [vector(), vector()],
        },
        {
            "model": "text-embedding-v4",
            "dimensions": 1024,
            "vectors": [[float("nan")] * 1024],
        },
        {"model": "text-embedding-v4", "dimensions": 1024, "vectors": [[True] * 1024]},
    ],
)
def test_external_masterbrain_response_must_match_index_contract(monkeypatch, result):
    enable_embeddings(monkeypatch)
    monkeypatch.setattr(masterbrain, "json_request", AsyncMock(return_value=result))
    with pytest.raises((ValueError, ValidationError)):
        asyncio.run(masterbrain.text_embeddings(["text"]))


@pytest.mark.parametrize(
    "enabled,error",
    [(False, None), (True, httpx.ReadTimeout("private provider content"))],
)
def test_keyword_index_survives_disabled_or_unavailable_ai(
    monkeypatch, caplog, enabled, error
):
    enable_embeddings(monkeypatch, enabled)
    send = AsyncMock(side_effect=error or AssertionError("must not send"))
    monkeypatch.setattr(masterbrain, "json_request", send)
    monkeypatch.setattr(
        text_splitter, "text_to_chunks", lambda _text: ["alpha", "beta"]
    )
    monkeypatch.setattr(text_splitter, "text_to_words", lambda text: [text])
    result = asyncio.run(text_splitter.text_to_embeddings("source"))
    assert result == [("alpha", ["alpha"], None), ("beta", ["beta"], None)]
    assert "private provider content" not in caplog.text
    assert send.await_count == int(enabled)


def test_cancelled_indexing_is_not_disguised_as_provider_outage(monkeypatch):
    enable_embeddings(monkeypatch)
    monkeypatch.setattr(
        masterbrain, "json_request", AsyncMock(side_effect=asyncio.CancelledError())
    )
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(text_splitter.optional_text_to_vectors(["text"]))


def test_keyword_only_rows_remain_searchable_when_ai_returns(monkeypatch):
    monkeypatch.setattr(
        "app.models.embedding.text_to_words", lambda _text: ["antibody"]
    )
    predicate, ordering = Embedding.search_conditions("antibody", vector())
    query = str(
        select(Embedding.id)
        .where(predicate)
        .order_by(*ordering)
        .compile(dialect=postgresql.dialect())
    )
    assert " OR " in query and "@@" in query and "<=>" in query
    predicate, ordering = Embedding.search_conditions("antibody", None)
    query = str(
        select(Embedding.id)
        .where(predicate)
        .order_by(*ordering)
        .compile(dialect=postgresql.dialect())
    )
    assert "@@" in query and "<=>" not in query


def test_keyword_only_discussion_context_matches_published_chat_contract():
    from masterbrain.endpoints.chat.qa.language.types import ChatInput

    from app.routers.chats.utils import generate_tool_call_messages

    result = {"airalogy_discussions": [{"content": "antibody", "similarity": None}]}
    messages = generate_tool_call_messages("inject_airalogy_discussions", {}, result)
    request = ChatInput.model_validate({"messages": messages})
    assert json.loads(request.messages[-1]["content"]) == result


def test_index_replacement_is_atomic_and_rebuild_uses_correct_signature(monkeypatch):
    from app.models import embedding as module

    session = SimpleNamespace(execute=AsyncMock(), add_all=Mock(), commit=AsyncMock())

    @asynccontextmanager
    async def database():
        yield session

    monkeypatch.setattr(module.sessionmanager, "session", database)
    chunks = AsyncMock(return_value=[("antibody", ["antibody"], None)])
    monkeypatch.setattr(module, "text_to_embeddings", chunks)
    protocol_id, resource_id = uuid4(), uuid4()
    context = UsageContext(feature="index.question")
    asyncio.run(
        Embedding.rebuild_resource(
            protocol_id,
            resource_id,
            EmbeddingResourceType.QUESTION,
            "antibody",
            usage_context=context,
        )
    )
    statements = [
        str(call.args[0].compile(dialect=postgresql.dialect()))
        for call in session.execute.await_args_list
    ]
    assert "FOR UPDATE" in statements[0]
    assert statements[1].startswith("DELETE FROM embeddings")
    rows = session.add_all.call_args.args[0]
    assert len(rows) == 1 and rows[0].embedding is None and rows[0].text == "antibody"
    session.commit.assert_awaited_once()
    assert chunks.await_args.kwargs["usage_context"] is context
    assert Embedding.__table__.c.embedding.nullable


@pytest.mark.parametrize(
    "params,expected",
    [
        ({"title": "Updated title"}, "Updated title\n\nOriginal body"),
        ({"content": "Updated body"}, "Original title\n\nUpdated body"),
        ({"tags": ["tag"]}, None),
    ],
)
def test_partial_question_edit_uses_complete_saved_text(monkeypatch, params, expected):
    user_id, protocol_id, project_id, lab_id = [uuid4() for _ in range(4)]
    question = Question(
        id=uuid4(),
        protocol_id=protocol_id,
        user_id=user_id,
        title="Original title",
        content="Original body",
    )
    monkeypatch.setattr(questions.Question, "find", AsyncMock(return_value=question))
    monkeypatch.setattr(
        questions.Protocol,
        "find",
        AsyncMock(return_value=SimpleNamespace(project_id=project_id)),
    )
    monkeypatch.setattr(
        questions.Project,
        "find",
        AsyncMock(return_value=SimpleNamespace(id=project_id, lab_id=lab_id)),
    )
    tasks = BackgroundTasks()
    asyncio.run(
        questions.update_question(
            question.id,
            questions.QuestionUpateParams(**params),
            SimpleNamespace(id=user_id),
            SimpleNamespace(commit=AsyncMock()),
            tasks,
        )
    )
    assert len(tasks.tasks) == int(expected is not None)
    if expected is not None:
        assert tasks.tasks[0].args[-1] == expected
        context = tasks.tasks[0].kwargs["usage_context"]
        assert context.user_id == str(user_id) and context.tenant_id == str(lab_id)


def test_published_masterbrain_endpoint_uses_platform_metering_without_network(
    monkeypatch,
):
    from masterbrain import configs
    from masterbrain.fastapi.embeddings import router
    from masterbrain.fastapi.usage import install_usage_context_middleware
    from masterbrain.providers.litellm import build_litellm_openai_compatible_client
    from masterbrain.utils import llm
    from openai.resources.embeddings import AsyncEmbeddings

    enable_embeddings(monkeypatch)
    monkeypatch.setattr(llm, "DASHSCOPE_API_KEY", "synthetic-key")
    monkeypatch.setattr(
        configs,
        "DASHSCOPE_CLIENT",
        build_litellm_openai_compatible_client(
            provider="qwen", api_key="synthetic-key"
        ),
    )

    async def provider(_self, **kwargs):
        return SimpleNamespace(
            model=kwargs["model"],
            usage={"prompt_tokens": 9, "total_tokens": 9},
            data=[{"index": 0, "embedding": vector()}],
        )

    monkeypatch.setattr(AsyncEmbeddings, "create", provider)
    app = FastAPI()
    install_usage_context_middleware(app)
    configure_embedded_masterbrain_app(app)
    app.include_router(router, prefix="/api/endpoints")

    @asynccontextmanager
    async def client():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://masterbrain.local"
        ) as client:
            yield client

    monkeypatch.setattr(masterbrain, "_masterbrain_client", client)
    monkeypatch.setattr(
        masterbrain, "_masterbrain_request_target", lambda path: f"/api/{path}"
    )
    context = UsageContext(
        feature="index.protocol", tenant_id=str(uuid4()), user_id=str(uuid4())
    )
    sink = InMemoryUsageSink()
    with bind_usage_sinks(sink):
        result = asyncio.run(
            masterbrain.text_embeddings(["authorized text"], usage_context=context)
        )
    assert result == [vector()]
    assert len(sink.events) == 1 and sink.events[0].context is context
    assert (
        sink.events[0].call_type == "embedding"
        and sink.events[0].usage.input_tokens == 9
    )
