"""Add tamper-evident Aira provenance to scientific Claims.

Revision ID: 0034_research_claim_ai_provenance
Revises: 0033_research_compute_outputs
Create Date: 2026-09-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_research_claim_ai_provenance"
down_revision: str | None = "0033_research_compute_outputs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ADDED_COLUMNS = (
    "generation_id",
    "generation_model",
    "generation_snapshot",
    "generation_receipt_digest",
)
GENERATION_CONSTRAINT = "ck_research_claim_generation_provenance"
GENERATION_INDEX = "uq_research_claims_generation_id"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("research_claims")}
    definitions = {
        "generation_id": sa.Column("generation_id", sa.UUID(), nullable=True),
        "generation_model": sa.Column(
            "generation_model", sa.String(length=255), nullable=True
        ),
        "generation_snapshot": sa.Column("generation_snapshot", sa.JSON(), nullable=True),
        "generation_receipt_digest": sa.Column(
            "generation_receipt_digest", sa.String(length=64), nullable=True
        ),
    }
    for name, definition in definitions.items():
        if name not in columns:
            op.add_column("research_claims", definition)
    inspector = sa.inspect(bind)
    indexes = {
        index["name"] for index in inspector.get_indexes("research_claims")
    }
    if GENERATION_INDEX not in indexes:
        op.create_index(
            GENERATION_INDEX,
            "research_claims",
            ["generation_id"],
            unique=True,
        )
    checks = {
        check["name"]
        for check in inspector.get_check_constraints("research_claims")
    }
    if GENERATION_CONSTRAINT not in checks:
        op.create_check_constraint(
            GENERATION_CONSTRAINT,
            "research_claims",
            "((generated_by = 'human' AND generation_id IS NULL "
            "AND generation_model IS NULL AND generation_snapshot IS NULL "
            "AND generation_receipt_digest IS NULL) OR "
            "(generated_by = 'aira_assisted' AND generation_id IS NOT NULL "
            "AND generation_model IS NOT NULL AND generation_snapshot IS NOT NULL "
            "AND generation_receipt_digest IS NOT NULL))",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    checks = {
        check["name"]
        for check in inspector.get_check_constraints("research_claims")
    }
    indexes = {
        index["name"] for index in inspector.get_indexes("research_claims")
    }
    columns = {column["name"] for column in inspector.get_columns("research_claims")}
    if GENERATION_CONSTRAINT in checks:
        op.drop_constraint(
            GENERATION_CONSTRAINT,
            "research_claims",
            type_="check",
        )
    if GENERATION_INDEX in indexes:
        op.drop_index(GENERATION_INDEX, table_name="research_claims")
    for name in reversed(ADDED_COLUMNS):
        if name in columns:
            op.drop_column("research_claims", name)
