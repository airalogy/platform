"""Complete research action approval audit fields.

Revision ID: 0010_research_approvals
Revises: 0009_research_tasks
Create Date: 2026-09-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_research_approvals"
down_revision: str | None = "0009_research_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ADDED_COLUMNS = {
    "decided_by_user_id",
    "decision_reason",
    "revision",
}


def upgrade() -> None:
    bind = op.get_bind()
    columns = {
        column["name"] for column in sa.inspect(bind).get_columns("research_approvals")
    }
    decided_by_added = "decided_by_user_id" not in columns
    if decided_by_added:
        op.add_column(
            "research_approvals",
            sa.Column("decided_by_user_id", sa.UUID(), nullable=True),
        )
    if "decision_reason" not in columns:
        op.add_column(
            "research_approvals",
            sa.Column("decision_reason", sa.Text(), nullable=False, server_default=""),
        )
    if "revision" not in columns:
        op.add_column(
            "research_approvals",
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        )
    if decided_by_added:
        op.create_foreign_key(
            "fk_research_approvals_decided_by_user_id_users",
            "research_approvals",
            "users",
            ["decided_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            "ix_research_approvals_decided_by_user_id",
            "research_approvals",
            ["decided_by_user_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("research_approvals")}
    indexes = {index["name"] for index in inspector.get_indexes("research_approvals")}
    if "ix_research_approvals_decided_by_user_id" in indexes:
        op.drop_index(
            "ix_research_approvals_decided_by_user_id",
            table_name="research_approvals",
        )
    foreign_keys = [
        key
        for key in inspector.get_foreign_keys("research_approvals")
        if key.get("constrained_columns") == ["decided_by_user_id"]
    ]
    for foreign_key in foreign_keys:
        if foreign_key.get("name"):
            op.drop_constraint(
                foreign_key["name"],
                "research_approvals",
                type_="foreignkey",
            )
    for column in ("revision", "decision_reason", "decided_by_user_id"):
        if column in columns:
            op.drop_column("research_approvals", column)
