import json
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select

from app.database import DBSession
from app.models.chat import Chat, ChatModel, ChatModelType
from app.models.user import User

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
