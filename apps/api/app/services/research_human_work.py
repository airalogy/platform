"""Bounded contracts for non-Protocol human Research work."""

from __future__ import annotations

import json
import math
import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.research_asset import EvidenceKind

HUMAN_WORK_CAPABILITY_KEY = "human:structured-work"
HUMAN_WORK_CAPABILITY_VERSION = "1"
HUMAN_WORK_SUBMISSION_SCHEMA = "airalogy.human-work-submission.v1"
FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class HumanWorkField(BaseModel):
    """One safe, renderer-friendly field in a human submission contract."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2_000)
    value_type: Literal["text", "long_text", "number", "boolean", "date", "choice"]
    required: bool = True
    options: list[str] = Field(default_factory=list, max_length=50)
    unit: str = Field(default="", max_length=64)

    @model_validator(mode="after")
    def normalize_and_validate(self):
        self.key = self.key.strip().lower()
        self.label = self.label.strip()
        self.description = self.description.strip()
        self.unit = self.unit.strip()
        self.options = [item.strip() for item in self.options]
        if not FIELD_KEY_RE.fullmatch(self.key):
            raise ValueError("Human Work field key is invalid")
        if not self.label:
            raise ValueError("Human Work field label is required")
        if self.value_type == "choice":
            if len(self.options) < 2 or any(
                not item or len(item) > 255 for item in self.options
            ):
                raise ValueError(
                    "Choice fields require at least two non-empty options of at most "
                    "255 characters"
                )
            if len(self.options) != len(set(self.options)):
                raise ValueError("Choice field options must be unique")
        elif self.options:
            raise ValueError("Only choice fields may declare options")
        if self.value_type != "number" and self.unit:
            raise ValueError("Only number fields may declare a unit")
        return self


class HumanWorkRequest(BaseModel):
    """An exact, bounded work request that Platform can render and validate."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    instructions: str = Field(min_length=1, max_length=20_000)
    completion_criteria: str = Field(default="", max_length=4_000)
    evidence_kind: EvidenceKind = EvidenceKind.OBSERVATION
    fields: list[HumanWorkField] = Field(min_length=1, max_length=20)
    data_asset_min_count: int = Field(default=0, ge=0, le=20)
    data_asset_max_count: int = Field(default=0, ge=0, le=20)

    @model_validator(mode="after")
    def normalize_and_validate(self):
        self.title = self.title.strip()
        self.instructions = self.instructions.strip()
        self.completion_criteria = self.completion_criteria.strip()
        if not self.title or not self.instructions:
            raise ValueError("Human Work title and instructions are required")
        keys = [item.key for item in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError("Human Work field keys must be unique")
        if self.data_asset_min_count > self.data_asset_max_count:
            raise ValueError("Human Work DataAsset minimum exceeds its maximum")
        if len(json.dumps(self.model_dump(mode="json"), ensure_ascii=False)) > 50_000:
            raise ValueError("Human Work request is too large")
        return self

    def submission_contract(self) -> dict[str, Any]:
        return {
            "schema": HUMAN_WORK_SUBMISSION_SCHEMA,
            "type": "structured_values",
            "fields": [item.model_dump(mode="json") for item in self.fields],
            "data_asset_min_count": self.data_asset_min_count,
            "data_asset_max_count": self.data_asset_max_count,
            "evidence_kind": self.evidence_kind.value,
            "completion_criteria": self.completion_criteria,
        }


def human_work_request_from_contract(
    *,
    title: str,
    instructions: str,
    contract: dict[str, Any],
) -> HumanWorkRequest:
    if contract.get("schema") != HUMAN_WORK_SUBMISSION_SCHEMA:
        raise ValueError("Human Work submission contract version is unsupported")
    if contract.get("type") != "structured_values":
        raise ValueError("Human Work submission contract type is unsupported")
    return HumanWorkRequest.model_validate(
        {
            "title": title,
            "instructions": instructions,
            "completion_criteria": contract.get("completion_criteria") or "",
            "evidence_kind": contract.get("evidence_kind") or "observation",
            "fields": contract.get("fields") or [],
            "data_asset_min_count": contract.get("data_asset_min_count") or 0,
            "data_asset_max_count": contract.get("data_asset_max_count") or 0,
        }
    )


def validate_human_work_submission(
    request: HumanWorkRequest,
    *,
    values: dict[str, Any],
    data_asset_count: int,
) -> dict[str, Any]:
    """Validate untrusted user values against the fixed renderer-safe contract."""

    if len(json.dumps(values, ensure_ascii=False)) > 100_000:
        raise ValueError("Human Work submission is too large")
    fields = {item.key: item for item in request.fields}
    unknown = set(values) - set(fields)
    if unknown:
        raise ValueError(f"Human Work submission contains unknown field: {min(unknown)}")
    normalized: dict[str, Any] = {}
    for key, field in fields.items():
        value = values.get(key)
        missing = value is None or (isinstance(value, str) and not value.strip())
        if missing:
            if field.required:
                raise ValueError(f"Human Work field {key} is required")
            normalized[key] = None
            continue
        if field.value_type in {"text", "long_text", "choice", "date"}:
            if not isinstance(value, str):
                raise ValueError(f"Human Work field {key} must be text")
            value = value.strip()
            maximum = 20_000 if field.value_type == "long_text" else 2_000
            if len(value) > maximum:
                raise ValueError(f"Human Work field {key} is too long")
            if field.value_type == "choice" and value not in field.options:
                raise ValueError(f"Human Work field {key} has an invalid option")
            if field.value_type == "date":
                try:
                    date.fromisoformat(value)
                except ValueError as error:
                    raise ValueError(
                        f"Human Work field {key} must use YYYY-MM-DD"
                    ) from error
            normalized[key] = value
        elif field.value_type == "number":
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not math.isfinite(value)
            ):
                raise ValueError(f"Human Work field {key} must be a number")
            normalized[key] = value
        elif field.value_type == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"Human Work field {key} must be true or false")
            normalized[key] = value
    if not request.data_asset_min_count <= data_asset_count <= request.data_asset_max_count:
        raise ValueError(
            "Human Work submission does not satisfy the DataAsset count contract"
        )
    return normalized
