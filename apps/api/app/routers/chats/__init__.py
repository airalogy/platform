from fastapi import APIRouter

from .field_input import router as field_input_router
from .index import router as chats_router
from .qa import router as qa_chat_router
from .stt import router as stt_router

router = APIRouter(
    prefix="/chats",
    tags=["chats"],
)

router.include_router(chats_router)
router.include_router(qa_chat_router)
router.include_router(field_input_router)
router.include_router(stt_router)
