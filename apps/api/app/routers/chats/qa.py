import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.database import DBSession
from app.libs.masterbrain import chat_qa_language
from app.models.chat import (
    Chat,
    ChatContext,
    ChatModel,
    ChatType,
    ChatUserMessage,
)
from app.models.project import Project
from app.models.protocol import Protocol
from app.routers.depends import CurrentUser, get_current_user
from app.routers.permission import check_user_permission
from app.services.model_usage import create_usage_context

from .context_inject import (
    build_current_editor_protocol_context_message,
    build_current_recorder_record_context_message,
    inject_airalogy_discussions,
    inject_airalogy_protocols,
    inject_airalogy_records,
    inject_recommended_airalogy_protocols,
)
from .file_processor import process_files
from .utils import (
    build_chat_stream_error_data,
    check_model_usage,
    generate_tool_call_messages,
)

logger = logging.getLogger("app")

router = APIRouter(
    dependencies=[Depends(get_current_user)],
)


class QAChatMessageParams(BaseModel):
    chat_id: uuid.UUID | None = None
    protocol_id: uuid.UUID | None = None
    context: ChatContext
    message: ChatUserMessage
    model: ChatModel
    hub_search: bool = False


# protocol record qa chat
@router.post(
    "/qa/message",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {
                "text/event-stream": {
                    "description": "Stream of chat messages",
                },
            }
        }
    },
)
async def send_qa_chat_message(
    db_session: DBSession,
    current_user: CurrentUser,
    params: QAChatMessageParams,
) -> StreamingResponse:
    protocol: Protocol | None = None
    project: Project | None = None
    if params.protocol_id is not None:
        protocol = await Protocol.find(db_session, id=params.protocol_id)
        project = await Project.find(db_session, id=protocol.project_id)
        await check_user_permission(
            db_session,
            project=project,
            user=current_user,
            action="read_protocol",
        )

    await check_model_usage(db_session, current_user, params.model)

    if params.chat_id is not None:
        chat = await Chat.find(db_session, id=params.chat_id)
        if chat.user_id != current_user.id:
            raise HTTPException(status_code=400, detail="Permission denied")
    else:
        chat = Chat(
            protocol_id=params.protocol_id,
            user_id=current_user.id,
            context={},
            messages=[],
            type=ChatType.QA,
            model=params.model.model_dump(),
            model_type=params.model.model_type.value,
            user_message_count=0,
        )
        db_session.add(chat)
        await db_session.flush()

    if project is None and chat.protocol_id is not None:
        chat_protocol = await Protocol.find(db_session, id=chat.protocol_id)
        project = await Project.find(db_session, id=chat_protocol.project_id)

    usage_context = create_usage_context(
        feature="chat.qa",
        user_id=current_user.id,
        lab_id=project.lab_id if project is not None else None,
        project_id=project.id if project is not None else None,
        chat_id=chat.id,
    )

    # files
    if params.message.files is not None and len(params.message.files) > 0:
        file_tool_call_messages = await process_files(
            db_session,
            params.message.files,
            current_user.id,
            usage_context=usage_context,
        )
        chat.messages.extend(file_tool_call_messages)

    message = params.message.model_dump()
    context = params.context.model_dump(exclude_none=True)
    ephemeral_context = context.pop("ephemeral_context", {}) or {}
    editor_context_message = build_current_editor_protocol_context_message(
        ephemeral_context.get("current_editor_protocol"),
    )
    recorder_context_message = build_current_recorder_record_context_message(
        ephemeral_context.get("current_recorder_record"),
    )
    current_context_messages = [
        context_message
        for context_message in (editor_context_message, recorder_context_message)
        if context_message is not None
    ]
    current_context_message_index = len(chat.messages)
    current_context_message_count = len(current_context_messages)

    chat.model = params.model.model_dump()
    chat.model_type = params.model.model_type.value
    chat.messages.extend(current_context_messages)
    chat.messages.append(message)
    current_message_index = len(chat.messages)
    local_context = chat.context

    # inject airalogy protocols
    if context.get("inject_airalogy_protocols", {}).get("enabled", False):
        airalogy_protocol_ids = list(
            set(
                context.get("inject_airalogy_protocols", {}).get(
                    "airalogy_protocol_ids", []
                )
            ).difference(
                set(
                    local_context.get("inject_airalogy_protocols", {}).get(
                        "airalogy_protocol_ids", []
                    )
                )
            )
        )
        if len(airalogy_protocol_ids) > 0:
            protocols = await inject_airalogy_protocols(
                db_session,
                airalogy_protocol_ids,
            )
            inject_protocols_tool_call_messages = generate_tool_call_messages(
                "inject_airalogy_protocols",
                {"airalogy_protocol_ids": airalogy_protocol_ids},
                protocols,
            )
            chat.messages.extend(inject_protocols_tool_call_messages)

    # inject airalogy records
    if context.get("inject_airalogy_records", {}).get("enabled", False):
        airalogy_record_ids = list(
            set(
                context.get("inject_airalogy_records", {}).get(
                    "airalogy_record_ids", []
                )
            ).difference(
                set(
                    local_context.get("inject_airalogy_records", {}).get(
                        "airalogy_record_ids", []
                    )
                )
            )
        )
        if len(airalogy_record_ids) > 0:
            records = await inject_airalogy_records(
                db_session,
                airalogy_record_ids,
            )
            inject_records_tool_call_messages = generate_tool_call_messages(
                "inject_airalogy_records",
                {"airalogy_record_ids": airalogy_record_ids},
                records,
            )
            chat.messages.extend(inject_records_tool_call_messages)

    # inject airalogy discussions
    if (
        protocol
        and context.get("inject_airalogy_discussions", {}).get("enabled", False)
        and isinstance(message["content"], str)
    ):
        discussions = await inject_airalogy_discussions(
            db_session, protocol.id, message["content"]
        )
        if len(discussions["airalogy_discussions"]) > 0:
            airalogy_discussion_ids = [
                d["airalogy_discussion_id"] for d in discussions["airalogy_discussions"]
            ]
            inject_discussions_tool_call_messages = generate_tool_call_messages(
                "inject_airalogy_discussions",
                {"airalogy_discussion_ids": airalogy_discussion_ids},
                discussions,
            )
            chat.messages.extend(inject_discussions_tool_call_messages)

            if "airalogy_discussion_ids" not in context["inject_airalogy_discussions"]:
                context["inject_airalogy_discussions"]["airalogy_discussion_ids"] = (
                    airalogy_discussion_ids
                )
            else:
                context["inject_airalogy_discussions"]["airalogy_discussion_ids"] = (
                    list(
                        set(
                            context["inject_airalogy_discussions"][
                                "airalogy_discussion_ids"
                            ]
                            + airalogy_discussion_ids
                        )
                    )
                )

    # inject recommended airalogy protocols
    if params.hub_search and isinstance(message["content"], str):
        recommended_protocols = await inject_recommended_airalogy_protocols(
            db_session,
            message.get("content", ""),
        )
        recommended_protocol_ids = [
            p["id"] for p in recommended_protocols.get("airalogy_protocols", [])
        ]
        inject_protocols_tool_call_messages = generate_tool_call_messages(
            "recommend_airalogy_protocols",
            {"airalogy_protocol_ids": recommended_protocol_ids},
            recommended_protocols,
        )
        chat.messages.extend(inject_protocols_tool_call_messages)

        context["inject_airalogy_protocols"] = context.get(
            "inject_airalogy_protocols", {"enabled": True, "airalogy_protocol_ids": []}
        )
        context["inject_airalogy_protocols"]["airalogy_protocol_ids"] = list(
            set(
                context["inject_airalogy_protocols"]["airalogy_protocol_ids"]
                + recommended_protocol_ids
            )
        )

    chat.context = context

    # 创建一个新的流式响应，同时捕获内容
    async def capture_and_forward_stream():
        # 先讲 chat id 已 chunk 的方式发送
        meta_data = {
            "type": "meta",
            "data": {
                "chat_id": str(chat.id),
                "model": chat.model.get("name"),
            },
        }
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
        original_stream = chat_qa_language(
            chat=chat, usage_context=usage_context
        )

        full_response = ""
        try:
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
        except Exception as exc:
            logger.exception(
                "QA model stream failed for chat %s using model %s",
                chat.id,
                chat.model.get("name"),
            )
            error_event = {
                "type": "error",
                "data": build_chat_stream_error_data(
                    exc,
                    chat_id=chat.id,
                    model=chat.model.get("name"),
                ),
            }
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
            return

        yield "data: [DONE]\n\n"

        if current_context_message_count:
            del chat.messages[
                current_context_message_index : current_context_message_index
                + current_context_message_count
            ]

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
