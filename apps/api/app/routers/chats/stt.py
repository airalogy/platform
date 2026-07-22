import base64
from typing import Any

from fastapi import APIRouter, Depends, UploadFile

from app.database import DBSession
from app.libs.masterbrain import stt
from app.routers.depends import CurrentUser, get_current_user
from app.services.model_usage import create_usage_context

router = APIRouter(
    dependencies=[Depends(get_current_user)],
)


@router.post("/stt/message")
async def send_stt_chat_message(
    db_session: DBSession,
    current_user: CurrentUser,
    audio: UploadFile,
) -> dict[str, Any]:
    # Read audio file content
    audio_content = await audio.read()

    audio_base64 = base64.b64encode(audio_content).decode("utf-8")

    usage_context = create_usage_context(
        feature="chat.stt",
        user_id=current_user.id,
    )
    response = await stt(audio_base64, usage_context=usage_context)

    if response and "history" in response and response["history"]:
        last_message = response["history"][-1]
        if "content" in last_message and last_message["content"]:
            return {"text": last_message["content"]}
    return {"text": ""}
