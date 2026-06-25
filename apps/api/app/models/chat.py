from datetime import datetime
from enum import IntEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from Crypto import Protocol
from pydantic import BaseModel, Field, computed_field
from sqlalchemy import JSON, ForeignKey, func
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ChatType(IntEnum):
    QA = 1
    FIELD_INPUT = 2
    HUB = 3
    PROTOCOL_GENERATE = 4
    PROTOCOL_CHECK = 5
    PROTOCOL_DEBUG = 6
    VISION = 7
    STT = 8


FastModels = Literal["qwen3.5-flash"]
AccurateModels = Literal["qwen3.5-plus"]
DeepModels = Literal["qwen3-max"]
GPTModels = Literal["gpt-4.1"]
SupportedModels = FastModels | AccurateModels | DeepModels | GPTModels


class ChatModelType(IntEnum):
    BASIC = 1
    PLUS = 2
    PRO = 3
    GPT = 4


class ChatContextProtocol(BaseModel):
    enabled: bool = False
    airalogy_protocol_ids: list[str]


class ChatContextRecord(BaseModel):
    enabled: bool = False
    airalogy_record_ids: list[str]


class ChatContextDiscussion(BaseModel):
    enabled: bool = False
    scope: str = "protocol"
    airalogy_discussion_ids: list[str] | None = None


class ChatContextCurrentEditorProtocol(BaseModel):
    enabled: bool = False
    title: str | None = None
    protocol_aimd: str | None = None
    model_py: str | None = None
    assigner_py: str | None = None
    protocol_toml: str | None = None


class ChatContextCurrentRecorderRecord(BaseModel):
    enabled: bool = False
    title: str | None = None
    protocol_id: str | None = None
    protocol_uid: str | None = None
    protocol_name: str | None = None
    readonly: bool = False
    filled_count: int | None = None
    empty_count: int | None = None
    field_summary: list[dict[str, Any]] | None = None
    record_data: dict[str, Any] | None = None
    truncated: bool = False


class ChatContextEphemeralContext(BaseModel):
    current_editor_protocol: ChatContextCurrentEditorProtocol | None = None
    current_recorder_record: ChatContextCurrentRecorderRecord | None = None


class ChatContext(BaseModel):
    inject_airalogy_protocols: ChatContextProtocol | None = None
    inject_airalogy_records: ChatContextRecord | None = None
    inject_airalogy_discussions: ChatContextDiscussion | None = None
    ephemeral_context: ChatContextEphemeralContext | None = None


class ChatModel(BaseModel):
    model_type: Annotated[ChatModelType, Field(exclude=True)] = ChatModelType.BASIC
    enable_thinking: bool = False
    enable_search: bool = False

    @computed_field
    @property
    def name(self) -> SupportedModels:
        if self.model_type == ChatModelType.BASIC:
            return "qwen3.5-flash"
        elif self.model_type == ChatModelType.PLUS:
            return "qwen3.5-plus"
        elif self.model_type == ChatModelType.PRO:
            return "qwen3-max"
        elif self.model_type == ChatModelType.GPT:
            return "gpt-4.1"
        else:
            raise ValueError(f"Unknown ChatModelType: {self}")


class ChatFile(BaseModel):
    id: str
    type: Literal["image", "audio", "docx", "pdf", "text"]
    file_name: str


class ChatUserMessage(BaseModel):
    role: Literal["user"] = "user"
    content: str
    files: list[ChatFile] | None = None


class ChatToolMessage(BaseModel):
    role: Literal["tool"] = "tool"
    content: str
    tool_call_id: str


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[UUID] = mapped_column(
        nullable=False,
        primary_key=True,
        index=True,
        server_default=func.uuid_generate_v7(),
    )
    protocol_id: Mapped[UUID] = mapped_column(ForeignKey("protocols.id"), nullable=True)
    user_id: Mapped[UUID] = mapped_column(nullable=False)
    context: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default={})
    messages: Mapped[list[dict]] = mapped_column(
        MutableList.as_mutable(JSON), default=[]
    )
    type: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )
    model: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), nullable=False)
    model_type: Mapped[int] = mapped_column(nullable=False)
    user_message_count: Mapped[int] = mapped_column(nullable=False, default=1)
    protocol: Mapped["Protocol"] = relationship("Protocol", overlaps="chats")

    @property
    def airalogy_id(self):
        return f"airalogy.id.chat.{self.id}"
