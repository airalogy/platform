import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.config import config
from app.models.chat import ChatContext, ChatModel, ChatModelType, ChatUserMessage
from app.routers.chats.qa import QAChatMessageParams, send_qa_chat_message
from app.routers.chats.utils import check_model_usage
from app.services.chat_models import enabled_chat_model_types, is_chat_model_enabled


def test_gpt_is_excluded_when_not_enabled(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_GPT_MODEL", False)

    assert enabled_chat_model_types() == (
        ChatModelType.BASIC,
        ChatModelType.PLUS,
        ChatModelType.PRO,
    )
    assert is_chat_model_enabled(ChatModelType.GPT) is False


def test_gpt_is_available_when_explicitly_enabled(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_GPT_MODEL", True)

    assert enabled_chat_model_types()[-1] == ChatModelType.GPT
    assert is_chat_model_enabled(ChatModelType.GPT) is True


def test_disabled_gpt_request_is_rejected_before_usage_lookup(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_GPT_MODEL", False)

    with pytest.raises(HTTPException, match="Chat model is not enabled") as error:
        asyncio.run(
            check_model_usage(
                None,  # type: ignore[arg-type]
                None,  # type: ignore[arg-type]
                ChatModel(model_type=ChatModelType.GPT),
            )
        )

    assert error.value.status_code == 400


def test_new_qa_chat_has_model_before_first_flush(monkeypatch):
    model = ChatModel(model_type=ChatModelType.PLUS, enable_thinking=True)
    created_chats = []

    def add(chat):
        created_chats.append(chat)

    async def flush():
        assert created_chats[0].model == model.model_dump()

    db_session = SimpleNamespace(
        add=Mock(side_effect=add),
        flush=AsyncMock(side_effect=flush),
    )
    current_user = SimpleNamespace(id=uuid.uuid4())
    monkeypatch.setattr("app.routers.chats.qa.check_model_usage", AsyncMock())

    response = asyncio.run(
        send_qa_chat_message(
            db_session=db_session,
            current_user=current_user,
            params=QAChatMessageParams(
                context=ChatContext(),
                message=ChatUserMessage(content="Hello"),
                model=model,
            ),
        )
    )

    assert response.status_code == 200
    db_session.flush.assert_awaited_once()
