from fastapi import HTTPException

from app.config import config
from app.models.chat import ChatModelType


DEFAULT_CHAT_MODEL_TYPES = (
    ChatModelType.BASIC,
    ChatModelType.PLUS,
    ChatModelType.PRO,
)


def enabled_chat_model_types() -> tuple[ChatModelType, ...]:
    if not config.effective_ai_enabled:
        return ()

    enabled_models: tuple[ChatModelType, ...] = ()
    if config.qwen_chat_configured:
        enabled_models = DEFAULT_CHAT_MODEL_TYPES
    if config.gpt_chat_configured:
        enabled_models = (*enabled_models, ChatModelType.GPT)
    return enabled_models


def is_chat_model_enabled(model_type: ChatModelType) -> bool:
    return model_type in enabled_chat_model_types()


def require_ai_enabled() -> None:
    if not config.effective_ai_enabled:
        raise HTTPException(status_code=503, detail="AI features are disabled")
