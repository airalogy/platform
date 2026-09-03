"""Shared, transport-independent validation for governed Compute Actions."""

from __future__ import annotations

import re
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

MOUNT_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
MEDIA_TYPE_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*$"
)
MAX_SOURCE_BYTES = 200_000
MAX_AIRA_SOURCE_BYTES = 30_000
MAX_INPUT_ASSETS = 32
MAX_OUTPUT_FILES = 16
MAX_OUTPUT_FILE_BYTES = 2_147_483_647


class ComputeInputDraft(BaseModel):
    """One immutable DataAsset version mounted read-only into a Compute Job."""

    model_config = ConfigDict(extra="forbid")

    data_asset_version_id: UUID
    mount_name: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def normalize(self):
        self.mount_name = self.mount_name.strip()
        if not MOUNT_NAME_RE.fullmatch(self.mount_name):
            raise ValueError("Invalid Compute input mount name")
        return self


class ComputeOutputDraft(BaseModel):
    """One bounded file that may become a draft DataAsset after verification."""

    model_config = ConfigDict(extra="forbid")

    mount_name: str = Field(min_length=1, max_length=128)
    asset_name: str = Field(min_length=1, max_length=512)
    description: str = Field(default="", max_length=20_000)
    kind: Literal["file", "table", "image", "model", "archive"] = "file"
    media_type: str = Field(min_length=3, max_length=255)
    max_bytes: int = Field(ge=1, le=MAX_OUTPUT_FILE_BYTES)
    required: bool = True
    data_schema: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize(self):
        self.mount_name = self.mount_name.strip()
        self.asset_name = self.asset_name.strip()
        self.description = self.description.strip()
        self.media_type = self.media_type.strip().lower()
        if not MOUNT_NAME_RE.fullmatch(self.mount_name):
            raise ValueError("Invalid Compute output mount name")
        if not self.asset_name:
            raise ValueError("Compute output asset name is required")
        if not MEDIA_TYPE_RE.fullmatch(self.media_type):
            raise ValueError("Invalid Compute output media type")
        if len(str(self.data_schema)) > 100_000:
            raise ValueError("Compute output data Schema is too large")
        if len(str(self.metadata)) > 100_000:
            raise ValueError("Compute output metadata is too large")
        return self


def validate_compute_action_payload(
    *,
    source_code: str,
    source_byte_limit: int,
    input_payload: dict[str, Any],
    input_assets: list[ComputeInputDraft],
    output_files: list[ComputeOutputDraft],
) -> None:
    """Apply the same deterministic size and uniqueness limits to every caller."""

    if not source_code.strip():
        raise ValueError("Compute source code cannot be blank")
    if len(source_code.encode("utf-8")) > source_byte_limit:
        raise ValueError("Compute source code is too large")
    if len(str(input_payload)) > 100_000:
        raise ValueError("Compute input payload is too large")
    if len(input_assets) > MAX_INPUT_ASSETS:
        raise ValueError(f"Compute input assets cannot exceed {MAX_INPUT_ASSETS}")
    input_versions = [item.data_asset_version_id for item in input_assets]
    input_mounts = [item.mount_name for item in input_assets]
    if len(input_versions) != len(set(input_versions)) or len(input_mounts) != len(
        set(input_mounts)
    ):
        raise ValueError("Compute input assets and mount names must be unique")
    if len(output_files) > MAX_OUTPUT_FILES:
        raise ValueError(f"Compute output files cannot exceed {MAX_OUTPUT_FILES}")
    output_mounts = [item.mount_name for item in output_files]
    if len(output_mounts) != len(set(output_mounts)):
        raise ValueError("Compute output mount names must be unique")
    if len(str([item.model_dump(mode="json") for item in output_files])) > 200_000:
        raise ValueError("Compute output declarations are too large")


def validate_compute_output_budget(
    output_files: list[ComputeOutputDraft], resource_limits: dict[str, Any]
) -> int:
    """Reserve room for the structured result inside the environment output cap."""

    total = sum(item.max_bytes for item in output_files)
    output_limit = int(resource_limits.get("max_output_bytes") or 0)
    if total > max(0, output_limit - 1024):
        raise ValueError(
            "Declared Compute output files must leave at least 1024 bytes "
            "for the structured result"
        )
    return total
