from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from app.database import DBSession
from app.models.chat import (
    Chat,
    ChatType,
)
from app.routers.chats.utils import UsageLimit
from app.routers.depends import CurrentUser, get_current_user
from app.services.chat_models import enabled_chat_model_types

router = APIRouter(
    dependencies=[Depends(get_current_user)],
)


@router.get("/usage")
async def get_usage(db_session: DBSession, current_user: CurrentUser):
    user_limit = UsageLimit.get(current_user.level, UsageLimit[1])

    query = (
        select(Chat.model_type, func.sum(Chat.user_message_count).label("total_count"))
        .where(
            Chat.user_id == current_user.id,
            Chat.created_at >= datetime.combine(datetime.now(), datetime.min.time()),
        )
        .group_by(Chat.model_type)
    )
    result = await db_session.execute(query)
    rows = result.all()

    # Create a dict of used counts keyed by model_type (int value)
    used_counts = {row.model_type: row.total_count for row in rows}

    usage = {}
    for model_type in enabled_chat_model_types():
        count = used_counts.get(model_type.value, 0)
        limit = user_limit.get(model_type, 0)
        usage[model_type.name.capitalize()] = {"used": count, "limit": limit}

    return usage


@router.get("/{chat_id}")
async def get_chat(chat_id: UUID, db_session: DBSession, current_user: CurrentUser):
    chat = await Chat.find(db_session, id=chat_id)
    if chat.user_id != current_user.id:
        raise HTTPException(status_code=400, detail="Permission denied")
    return chat


@router.get("/")
async def get_chat_history(
    db_session: DBSession,
    current_user: CurrentUser,
    type: ChatType,
    protocol_id: UUID | None = None,
    page: int = 1,
    page_size: int = 10,
):
    chats = await Chat.all(
        db_session,
        [
            Chat.user_id == current_user.id,
            Chat.protocol_id == protocol_id,
            Chat.type == type,
        ],
        page=page,
        page_size=page_size,
        order_by=[Chat.id.desc()],
    )
    return {"chats": [c.as_dict() for c in chats]}
