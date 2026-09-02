"""Add tamper-evident Aira provenance to Protocol improvement proposals.

Revision ID: 0022_protocol_improvement_ai_provenance
Revises: 0021_protocol_improvement_lineage
Create Date: 2026-09-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_protocol_improvement_ai_provenance"
down_revision: str | None = "0021_protocol_improvement_lineage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ADDED_COLUMNS = (
    "generation_id",
    "generation_model",
    "generation_snapshot",
    "generation_receipt_digest",
)
GENERATION_CONSTRAINT = "ck_protocol_improvement_generation_provenance"
GENERATION_INDEX = "uq_protocol_improvement_proposals_generation_id"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {
        column["name"]
        for column in inspector.get_columns("protocol_improvement_proposals")
    }
    definitions = {
        "generation_id": sa.Column("generation_id", sa.UUID(), nullable=True),
        "generation_model": sa.Column(
            "generation_model", sa.String(length=255), nullable=True
        ),
        "generation_snapshot": sa.Column(
            "generation_snapshot", sa.JSON(), nullable=True
        ),
        "generation_receipt_digest": sa.Column(
            "generation_receipt_digest", sa.String(length=64), nullable=True
        ),
    }
    for name, definition in definitions.items():
        if name not in columns:
            op.add_column("protocol_improvement_proposals", definition)
    inspector = sa.inspect(bind)
    indexes = {
        index["name"]
        for index in inspector.get_indexes("protocol_improvement_proposals")
    }
    if GENERATION_INDEX not in indexes:
        op.create_index(
            GENERATION_INDEX,
            "protocol_improvement_proposals",
            ["generation_id"],
            unique=True,
        )
    checks = {
        check["name"]
        for check in inspector.get_check_constraints("protocol_improvement_proposals")
    }
    if GENERATION_CONSTRAINT not in checks:
        op.create_check_constraint(
            GENERATION_CONSTRAINT,
            "protocol_improvement_proposals",
            "((generated_by = 'human' AND generation_id IS NULL "
            "AND generation_model IS NULL AND generation_snapshot IS NULL "
            "AND generation_receipt_digest IS NULL) OR "
            "(generated_by <> 'human' AND generation_id IS NOT NULL "
            "AND generation_model IS NOT NULL AND generation_snapshot IS NOT NULL "
            "AND generation_receipt_digest IS NOT NULL))",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    checks = {
        check["name"]
        for check in inspector.get_check_constraints("protocol_improvement_proposals")
    }
    indexes = {
        index["name"]
        for index in inspector.get_indexes("protocol_improvement_proposals")
    }
    columns = {
        column["name"]
        for column in inspector.get_columns("protocol_improvement_proposals")
    }
    if GENERATION_CONSTRAINT in checks:
        op.drop_constraint(
            GENERATION_CONSTRAINT,
            "protocol_improvement_proposals",
            type_="check",
        )
    if GENERATION_INDEX in indexes:
        op.drop_index(
            GENERATION_INDEX,
            table_name="protocol_improvement_proposals",
        )
    for name in reversed(ADDED_COLUMNS):
        if name in columns:
            op.drop_column("protocol_improvement_proposals", name)
