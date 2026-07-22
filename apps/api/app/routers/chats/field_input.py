import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database import DBSession
from app.libs.masterbrain import field_input_chat
from app.models.chat import (
    Chat,
    ChatModel,
    ChatToolMessage,
    ChatType,
    ChatUserMessage,
)
from app.models.lab import Lab
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.routers.chats.file_processor import process_files
from app.routers.chats.utils import check_model_usage
from app.routers.depends import CurrentUser, get_current_user
from app.routers.permission import check_user_permission
from app.services.model_usage import create_usage_context

router = APIRouter(
    dependencies=[Depends(get_current_user)],
)


class FieldInputChatMessageParams(BaseModel):
    chat_id: uuid.UUID | None = None
    protocol_id: uuid.UUID
    message: ChatUserMessage | ChatToolMessage
    model: ChatModel


@router.post("/field_input/message")
async def send_field_input_chat_message(
    db_session: DBSession,
    current_user: CurrentUser,
    params: FieldInputChatMessageParams,
) -> dict[str, Any]:
    protocol = await Protocol.find(db_session, id=params.protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    lab = await Lab.find(db_session, id=project.lab_id)
    protocol.lab_uid = lab.uid
    protocol.project_uid = project.uid

    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="read_protocol",
    )
    await check_model_usage(db_session, current_user, params.model)

    protocol_version = await ProtocolVersion.find_by(
        db_session,
        [
            ProtocolVersion.protocol_id == protocol.id,
            ProtocolVersion.version == protocol.latest_version,
        ],
    )
    if protocol_version is None:
        raise HTTPException(status_code=400, detail="Protocol schema not found")

    if params.chat_id is not None:
        chat = await Chat.find(db_session, id=params.chat_id)
        if chat.user_id != current_user.id:
            raise HTTPException(status_code=400, detail="Permission denied")
    else:
        chat = Chat(
            protocol_id=params.protocol_id,
            user_id=current_user.id,
            context={
                "inject_airalogy_protocols": {
                    "enabled": True,
                    "airalogy_protocol_ids": [protocol.airalogy_id],
                },
                "protocol_schema": protocol_version.json_schema["vars"],
            },
            type=ChatType.FIELD_INPUT,
            messages=[],
            model={
                "name": params.model.name,
            },
            model_type=params.model.model_type.value,
            user_message_count=0,
        )
        db_session.add(chat)
        await db_session.flush()

    usage_context = create_usage_context(
        feature="chat.field_input",
        user_id=current_user.id,
        lab_id=lab.id,
        project_id=project.id,
        chat_id=chat.id,
    )

    if params.model.name != chat.model["name"]:
        chat.model = {
            "name": params.model.name,
        }

    if params.message.files is not None and len(params.message.files) > 0:
        file_tool_call_messages = await process_files(
            db_session,
            params.message.files,
            current_user.id,
            usage_context=usage_context,
        )
        chat.messages.extend(file_tool_call_messages)

    chat.messages.append(params.message.model_dump())
    response = await field_input_chat(chat, usage_context=usage_context)
    chat.messages = response["history"]
    chat.model = response["model"]
    chat.user_message_count += 1

    await db_session.commit()

    return chat.as_dict()
