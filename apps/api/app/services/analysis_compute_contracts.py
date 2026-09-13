"""Typed private-analysis compute proposals; validation never executes source."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.record_analyses import AnalysisSelection
from app.services.research_compute_contracts import (
    MAX_SOURCE_BYTES,
    ComputeOutputDraft,
    validate_compute_action_payload,
)

COMPUTE_ENGINE_VERSION = "airalogy.compute.analysis.v1"
ANALYSIS_JOB_SCHEMA = "airalogy.compute-job.analysis.v1"
SOURCE_FILENAME = "records.json"


class AnalysisComputeRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["compute"] = "compute"
    environment_revision_id: UUID
    language: Literal["python", "r"]
    source_code: str
    parameters: dict = Field(default_factory=dict)
    output_files: list[ComputeOutputDraft] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def validate_contract(self):
        validate_compute_action_payload(
            source_code=self.source_code,
            source_byte_limit=MAX_SOURCE_BYTES,
            input_payload=self.parameters,
            input_assets=[],
            output_files=self.output_files,
        )
        # JSON persistence and signatures must agree on finite UTF-8 values.
        json.dumps(
            {
                "parameters": self.parameters,
                "output_files": [
                    output.model_dump(mode="python") for output in self.output_files
                ],
            },
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        return self


class AnalysisComputeDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_id: UUID
    selection: AnalysisSelection = Field(default_factory=AnalysisSelection)
    question: str = Field(default="", max_length=4000)
    recipe: AnalysisComputeRecipe
    approver_user_id: UUID
    max_cost: Decimal | None = Field(
        default=None, ge=0, max_digits=38, decimal_places=18
    )
    budget_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    deadline_at: datetime | None = None
    pipeline_revision_id: UUID | None = None
    rerun_of_id: UUID | None = None
    ai_draft_id: UUID | None = None

    @model_validator(mode="after")
    def validate_governance(self):
        if (self.max_cost is None) != (self.budget_currency is None):
            raise ValueError(
                "Compute cost ceiling and currency must be provided together"
            )
        if self.deadline_at is not None and self.deadline_at.tzinfo is None:
            raise ValueError("Compute deadline must include a timezone")
        self.question = self.question.strip()
        return self


class AnalysisComputeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    expected_revision: int = Field(ge=1, strict=True)
    contract_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def nonblank_reason(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("An approval decision reason is required")
        return self


class AnalysisComputeCancel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1, strict=True)
    contract_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def nonblank_reason(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("A cancellation reason is required")
        return self
