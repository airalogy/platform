"""Add structured reproduction drafts to independent review recommendations.

Revision ID: 0046_research_reproduction_assessments
Revises: 0045_instrument_safety_interlocks
Create Date: 2026-09-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0046_research_reproduction_assessments"
down_revision: str | None = "0045_instrument_safety_interlocks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "research_review_recommendations"
COLUMN_NAME = "reproduction_assessment"


def upgrade() -> None:
    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns(TABLE_NAME)
    }
    if COLUMN_NAME not in columns:
        op.add_column(
            TABLE_NAME,
            sa.Column(
                COLUMN_NAME,
                sa.JSON(),
            ),
        )


def downgrade() -> None:
    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns(TABLE_NAME)
    }
    if COLUMN_NAME in columns:
        op.drop_column(TABLE_NAME, COLUMN_NAME)
