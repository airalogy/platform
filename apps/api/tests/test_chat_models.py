import asyncio

import pytest
from fastapi import HTTPException

from app.config import config
from app.models.chat import ChatModel, ChatModelType
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
