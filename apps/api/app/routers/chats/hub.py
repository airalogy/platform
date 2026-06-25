import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import and_, select

from app.database import DBSession
from app.libs.masterbrain import hub_chat
from app.libs.text_splitter import text_to_vectors
from app.models.chat import (
    Chat,
    ChatModel,
    ChatType,
    ChatUserMessage,
)
from app.models.embedding import Embedding, EmbeddingResourceType
from app.models.lab import Lab
from app.models.project import Project, ProjectType
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.routers.chats.utils import check_model_usage, generate_tool_call_messages
from app.routers.depends import CurrentUser, get_current_user

router = APIRouter(
    dependencies=[Depends(get_current_user)],
)


async def inject_recommend_airalogy_protocols(db_session, content: str, limit: int = 3):
    vector = text_to_vectors([content[0:1000]])[0]

    sub_query = (
        select(
            Protocol.id,
        )
        .join(
            Embedding,
            and_(
                Embedding.resource_id == Protocol.id,
                Embedding.resource_type == EmbeddingResourceType.PROTOCOL,
            ),
        )
        .join(
            Project,
            Protocol.project_id == Project.id,
        )
        .where(
            Project.type == ProjectType.PUBLIC,
            Protocol.parent_protocol_id.is_(None),
            Embedding.embedding.cosine_distance(vector) < 0.5,
        )
        .order_by(
            Embedding.embedding.cosine_distance(vector).asc(),
            Protocol.stars_count.desc(),
            Protocol.forks_count.desc(),
        )
        .limit(limit * 2)
        .subquery()
    )
    query = (
        select(
            ProtocolVersion, Lab.uid.label("lab_uid"), Project.uid.label("project_uid")
        )
        .join(
            Protocol,
            and_(
                ProtocolVersion.protocol_id == Protocol.id,
                ProtocolVersion.version == Protocol.latest_version,
            ),
        )
        .outerjoin(
            Project,
            Protocol.project_id == Project.id,
        )
        .outerjoin(
            Lab,
            Project.lab_id == Lab.id,
        )
        .where(
            Protocol.id.in_(select(sub_query.c.id)),
        )
        .order_by(
            Protocol.stars_count.desc(),
            Protocol.forks_count.desc(),
        )
        .limit(limit)
    )
    result = (await db_session.execute(query)).all()

    data = []
    for protocol_version, lab_uid, project_uid in result:
        protocol_version.lab_uid = lab_uid
        protocol_version.project_uid = project_uid
        data.append(
            {
                "id": protocol_version.airalogy_id,
                "markdown": protocol_version.aimd,
                "field_json_schema": protocol_version.json_schema,
            }
        )
    return {"airalogy_protocols": data}


class HubChatMessageParams(BaseModel):
    chat_id: uuid.UUID | None = None
    message: ChatUserMessage
    model: ChatModel


@router.post("/hub/message")
async def send_hub_chat_message(
    db_session: DBSession,
    current_user: CurrentUser,
    params: HubChatMessageParams,
) -> StreamingResponse:
    await check_model_usage(db_session, current_user, params.model)

    if params.chat_id is not None:
        chat = await Chat.find(db_session, id=params.chat_id)
        if chat.user_id != current_user.id:
            raise HTTPException(status_code=400, detail="Permission denied")
    else:
        chat = Chat(
            user_id=current_user.id,
            context={
                "inject_airalogy_protocols": {
                    "enabled": True,
                    "airalogy_protocol_ids": [],
                }
            },
            messages=[],
            type=ChatType.HUB,
            model={"name": params.model.name},
            model_type=params.model.model_type.value,
            user_message_count=0,
        )
        db_session.add(chat)
        await db_session.flush()

    message = params.message
    context = chat.context

    if params.model.name != chat.model["name"]:
        chat.model = {
            "name": params.model.name,
        }

    chat.messages.append(message.model_dump())
    current_message_index = len(chat.messages)
    # inject airalogy protocols
    protocols = await inject_recommend_airalogy_protocols(
        db_session,
        message.content,
    )
    airalogy_protocol_ids = [p["id"] for p in protocols["airalogy_protocols"]]
    inject_protocols_tool_call_messages = generate_tool_call_messages(
        "recommend_airalogy_protocols",
        {"airalogy_protocol_ids": airalogy_protocol_ids},
        protocols,
    )
    chat.messages.extend(inject_protocols_tool_call_messages)

    context["inject_airalogy_protocols"]["airalogy_protocol_ids"] = list(
        set(
            context["inject_airalogy_protocols"]["airalogy_protocol_ids"]
            + airalogy_protocol_ids
        )
    )
    chat.context = context

    # 创建一个新的流式响应，同时捕获内容
    async def capture_and_forward_stream():
        # 先讲 chat id 已 chunk 的方式发送
        meta_data = {"type": "meta", "data": {"chat_id": str(chat.id)}}
        yield f"data: {json.dumps(meta_data, ensure_ascii=False)}\n\n"

        # 发送 tool_call 的消息
        for i in range(current_message_index, len(chat.messages)):
            msg_data = {
                "type": "message",
                "data": {"index": i, "message": chat.messages[i]},
            }
            yield f"data: {json.dumps(msg_data, ensure_ascii=False)}\n\n"

        response_message_index = len(chat.messages)
        response_message = {
            "type": "message",
            "data": {
                "index": response_message_index,
                "message": {"role": "assistant", "content": ""},
            },
        }
        yield f"data: {json.dumps(response_message, ensure_ascii=False)}\n\n"

        # 获取原始的流式响应
        original_stream = hub_chat(chat=chat)

        full_response = ""
        async for chunk in original_stream:
            # 累积响应内容
            full_response += chunk
            # 将块转发给客户端
            chunk_message = {
                "type": "message",
                "data": {
                    "index": response_message_index,
                    "message": {"content": chunk},
                },
            }
            yield f"data: {json.dumps(chunk_message, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

        chat.messages.append(
            {
                "role": "assistant",
                "content": full_response,
            }
        )
        chat.user_message_count += 1
        chat.updated_at = datetime.now()
        await db_session.commit()

    # 返回新的流式响应
    return StreamingResponse(
        capture_and_forward_stream(),
        headers={"X-Accel-Buffering": "no"},
        media_type="text/event-stream",
    )
