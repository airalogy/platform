from app.config import config
from app.models.chat import ChatModelType


DEFAULT_CHAT_MODEL_TYPES = (
    ChatModelType.BASIC,
    ChatModelType.PLUS,
    ChatModelType.PRO,
)


def enabled_chat_model_types() -> tuple[ChatModelType, ...]:
    if config.ENABLE_GPT_MODEL:
        return (*DEFAULT_CHAT_MODEL_TYPES, ChatModelType.GPT)
    return DEFAULT_CHAT_MODEL_TYPES


def is_chat_model_enabled(model_type: ChatModelType) -> bool:
    return model_type in enabled_chat_model_types()
