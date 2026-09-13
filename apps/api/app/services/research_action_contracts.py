"""AI-independent inputs to the governed Research Action materializer."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProtocolActionDraft(BaseModel):
    """A user-authored Protocol occurrence, not an Aira proposal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: Literal["protocol"] = "protocol"
    protocol_id: UUID
    protocol_version_id: UUID
    title: str = Field(default="", max_length=255)
    thought: str = Field(default="", max_length=4000)
    protocol_initial_values: dict[str, Any] = Field(default_factory=dict)
