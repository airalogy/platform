import json
import uuid
from datetime import datetime
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select

from app.config import config
from app.database import DBSession
from app.models.chat import Chat, ChatModel, ChatModelType
from app.models.user import User
from app.services.chat_models import is_chat_model_enabled

UsageLimit = {
    1: {
        ChatModelType.BASIC: 50,
        ChatModelType.PLUS: 30,
        ChatModelType.PRO: 10,
        ChatModelType.GPT: 10,
    },
    2: {
        ChatModelType.BASIC: 200,
        ChatModelType.PLUS: 100,
        ChatModelType.PRO: 50,
        ChatModelType.GPT: 50,
    },
    3: {
        ChatModelType.BASIC: 500,
        ChatModelType.PLUS: 200,
        ChatModelType.PRO: 100,
        ChatModelType.GPT: 100,
    },
    9: {
        ChatModelType.BASIC: 10000,
        ChatModelType.PLUS: 10000,
        ChatModelType.PRO: 10000,
        ChatModelType.GPT: 10000,
    },
}


def build_chat_stream_error_data(
    exc: Exception,
    *,
    chat_id: uuid.UUID,
    model: str | None,
) -> dict[str, Any]:
    http_status: int | None = None

    if isinstance(exc, httpx.TimeoutException):
        code = "MODEL_TIMEOUT"
        message = "The model service did not respond in time."
        retryable = True
    elif isinstance(exc, httpx.ConnectError):
        code = "MODEL_UNAVAILABLE"
        message = "The platform could not connect to the model service."
        retryable = True
    elif isinstance(exc, httpx.RemoteProtocolError):
        code = "MODEL_STREAM_ERROR"
        message = "The model service interrupted the streaming response."
        retryable = True
    elif isinstance(exc, HTTPException):
        http_status = exc.status_code
        if http_status in (401, 403):
            code = "MODEL_AUTHENTICATION_FAILED"
            message = "The model service rejected its configured credentials."
            retryable = False
        elif http_status == 429:
            code = "MODEL_RATE_LIMITED"
            message = "The model service is rate limited."
            retryable = True
        elif http_status in (408, 504):
            code = "MODEL_TIMEOUT"
            message = "The model service did not respond in time."
            retryable = True
        elif http_status >= 500:
            code = "MODEL_UPSTREAM_ERROR"
            message = "The model service returned an internal error."
            retryable = True
        else:
            code = "MODEL_REQUEST_REJECTED"
            message = "The model service rejected this request."
            retryable = False
    elif isinstance(exc, httpx.RequestError):
        code = "MODEL_UNAVAILABLE"
        message = "The model service connection failed."
        retryable = True
    else:
        code = "MODEL_STREAM_ERROR"
        message = "The platform could not complete the model response."
        retryable = True

    data: dict[str, Any] = {
        "code": code,
        "stage": "model",
        "message": message,
        "chat_id": str(chat_id),
        "model": model,
        "retryable": retryable,
    }
    if http_status is not None:
        data["http_status"] = http_status

    if config.APP_ENV != "production":
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        data["debug"] = {
            "exception": type(exc).__name__,
            "detail": str(detail),
        }

    return data


def generate_tool_call_messages(
    function_name: str, function_args: dict[str, Any], function_result: dict[str, Any]
) -> list[dict[str, Any]]:
    tool_call_id = str(uuid.uuid4())
    return [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": function_name,
                        "arguments": json.dumps(function_args, ensure_ascii=False),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "content": json.dumps(function_result, ensure_ascii=False),
            "tool_call_id": tool_call_id,
        },
    ]


async def check_model_usage(
    db_session: DBSession, current_user: User, model: ChatModel
):
    if not is_chat_model_enabled(model.model_type):
        raise HTTPException(status_code=400, detail="Chat model is not enabled.")

    user_limit = UsageLimit.get(current_user.level, UsageLimit[1])

    query = (
        select(func.sum(Chat.user_message_count).label("total_count"))
        .select_from(Chat)
        .where(
            Chat.model_type == model.model_type.value,
            Chat.user_id == current_user.id,
            Chat.created_at >= datetime.combine(datetime.now(), datetime.min.time()),
        )
    )
    count = (await db_session.execute(query)).scalar() or 0
    count_limit = user_limit.get(model.model_type, 0)
    if count >= count_limit:
        raise HTTPException(status_code=400, detail="User model usage limit reached.")
