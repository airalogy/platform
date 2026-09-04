"""Add the dependency-blocked Research Service Job state.

Revision ID: 0041_research_service_graph_state
Revises: 0040_research_autonomy_policy
Create Date: 2026-09-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041_research_service_graph_state"
down_revision: str | None = "0040_research_autonomy_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT_NAME = "ck_research_service_job_status"
OLD_STATUSES = (
    "awaiting_quote",
    "awaiting_approval",
    "ordered",
    "in_fulfillment",
    "completed",
    "failed",
    "cancelled",
)
NEW_STATUSES = ("blocked", *OLD_STATUSES)


def _status_expression(statuses: tuple[str, ...]) -> str:
    return "status IN (" + ", ".join(repr(item) for item in statuses) + ")"


def _replace_constraint(statuses: tuple[str, ...]) -> None:
    bind = op.get_bind()
    constraints = {
        item["name"]
        for item in sa.inspect(bind).get_check_constraints("research_service_jobs")
    }
    if CONSTRAINT_NAME in constraints:
        op.drop_constraint(
            CONSTRAINT_NAME,
            "research_service_jobs",
            type_="check",
        )
    op.create_check_constraint(
        CONSTRAINT_NAME,
        "research_service_jobs",
        _status_expression(statuses),
    )


def upgrade() -> None:
    _replace_constraint(NEW_STATUSES)


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE research_service_jobs SET status = 'cancelled' "
            "WHERE status = 'blocked'"
        )
    )
    _replace_constraint(OLD_STATUSES)
