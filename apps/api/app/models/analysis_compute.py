"""Explicit approval and append-only lifecycle history for private computation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AnalysisComputeApprovalState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class AnalysisCompute(Base):
    """Approval of one immutable analysis contract, not another execution engine."""

    __tablename__ = "analysis_computations"
    __table_args__ = (
        CheckConstraint(
            "approval_state IN ('pending','approved','rejected','cancelled')",
            name="ck_analysis_compute_approval_state",
        ),
        CheckConstraint(
            "approval_revision >= 1", name="ck_analysis_compute_approval_revision"
        ),
        CheckConstraint(
            "contract_digest ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_compute_contract_digest",
        ),
        CheckConstraint(
            "(max_cost IS NULL AND budget_currency IS NULL) OR "
            "(max_cost IS NOT NULL AND max_cost >= 0 AND "
            "max_cost <> 'NaN'::numeric AND budget_currency IS NOT NULL AND "
            "budget_currency ~ '^[A-Z]{3}$')",
            name="ck_analysis_compute_budget_pair",
        ),
        Index(
            "ix_analysis_computations_approver_state",
            "approver_user_id",
            "approval_state",
        ),
        Index(
            "ix_analysis_computations_state_deadline", "approval_state", "deadline_at"
        ),
    )

    analysis_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), primary_key=True
    )
    approval_state: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=AnalysisComputeApprovalState.PENDING.value,
        server_default="pending",
    )
    approval_revision: Mapped[int] = mapped_column(
        nullable=False, default=1, server_default="1"
    )
    approver_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    contract_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    max_cost: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    budget_currency: Mapped[str | None] = mapped_column(String(3))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    decision_reason: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )


class AnalysisComputeEvent(Base):
    """Append-only decision and execution events; no mutable user-facing asset."""

    __tablename__ = "analysis_compute_events"
    __table_args__ = (
        UniqueConstraint(
            "analysis_run_id", "idempotency_key", name="uq_analysis_compute_event_key"
        ),
        Index(
            "ix_analysis_compute_events_analysis_created",
            "analysis_run_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    analysis_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
