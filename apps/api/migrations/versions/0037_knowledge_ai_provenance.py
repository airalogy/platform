"""Add tamper-evident Aira provenance to Knowledge items.

Revision ID: 0037_knowledge_ai_provenance
Revises: 0036_research_action_output_snapshots
Create Date: 2026-09-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037_knowledge_ai_provenance"
down_revision: str | None = "0036_research_action_output_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ADDED_COLUMNS = (
    "generation_id",
    "generation_model",
    "generation_snapshot",
    "generation_receipt_digest",
)
GENERATION_CONSTRAINT = "ck_knowledge_item_generation_provenance"
GENERATION_INDEX = "uq_knowledge_items_generation_id"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("knowledge_items")}
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
            op.add_column("knowledge_items", definition)
    inspector = sa.inspect(bind)
    indexes = {
        index["name"] for index in inspector.get_indexes("knowledge_items")
    }
    if GENERATION_INDEX not in indexes:
        op.create_index(
            GENERATION_INDEX,
            "knowledge_items",
            ["generation_id"],
            unique=True,
        )
    checks = {
        check["name"]
        for check in inspector.get_check_constraints("knowledge_items")
    }
    if GENERATION_CONSTRAINT not in checks:
        op.create_check_constraint(
            GENERATION_CONSTRAINT,
            "knowledge_items",
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
        for check in inspector.get_check_constraints("knowledge_items")
    }
    indexes = {
        index["name"] for index in inspector.get_indexes("knowledge_items")
    }
    columns = {column["name"] for column in inspector.get_columns("knowledge_items")}
    if GENERATION_CONSTRAINT in checks:
        op.drop_constraint(
            GENERATION_CONSTRAINT,
            "knowledge_items",
            type_="check",
        )
    if GENERATION_INDEX in indexes:
        op.drop_index(GENERATION_INDEX, table_name="knowledge_items")
    for name in reversed(ADDED_COLUMNS):
        if name in columns:
            op.drop_column("knowledge_items", name)
