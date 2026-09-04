"""Add governed Sample lineage semantics.

Revision ID: 0044_sample_lineage_semantics
Revises: 0043_research_autonomy_grants
Create Date: 2026-09-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044_sample_lineage_semantics"
down_revision: str | None = "0043_research_autonomy_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_names(bind) -> set[str]:
    return {
        item["name"] for item in sa.inspect(bind).get_columns("resource_lineage")
    }


def _constraint_names(bind) -> set[str]:
    inspector = sa.inspect(bind)
    return {
        item["name"]
        for item in (
            inspector.get_unique_constraints("resource_lineage")
            + inspector.get_check_constraints("resource_lineage")
            + inspector.get_foreign_keys("resource_lineage")
        )
        if item.get("name")
    }


def upgrade() -> None:
    bind = op.get_bind()
    columns = _column_names(bind)
    if "source_action_id" not in columns:
        op.add_column(
            "resource_lineage", sa.Column("source_action_id", sa.UUID(), nullable=True)
        )
    if "reason" not in columns:
        op.add_column(
            "resource_lineage",
            sa.Column("reason", sa.Text(), server_default="", nullable=False),
        )
    if "created_by_user_id" not in columns:
        op.add_column(
            "resource_lineage",
            sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        )
    if "idempotency_key" not in columns:
        op.add_column(
            "resource_lineage",
            sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        )

    columns_by_name = {
        item["name"]: item
        for item in sa.inspect(bind).get_columns("resource_lineage")
    }
    for name in ("record_id", "record_version"):
        if not columns_by_name[name]["nullable"]:
            op.alter_column(
                "resource_lineage",
                name,
                existing_type=columns_by_name[name]["type"],
                nullable=True,
            )

    constraints = _constraint_names(bind)
    if "fk_resource_lineage_created_by_user_id_users" not in constraints:
        op.create_foreign_key(
            "fk_resource_lineage_created_by_user_id_users",
            "resource_lineage",
            "users",
            ["created_by_user_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    if "uq_resource_lineage_idempotency" not in constraints:
        op.create_unique_constraint(
            "uq_resource_lineage_idempotency",
            "resource_lineage",
            ["idempotency_key"],
        )
    if "ck_resource_lineage_record_pair" not in constraints:
        op.create_check_constraint(
            "ck_resource_lineage_record_pair",
            "resource_lineage",
            "(record_id IS NULL) = (record_version IS NULL)",
        )
    if "ck_resource_lineage_distinct_resources" not in constraints:
        op.create_check_constraint(
            "ck_resource_lineage_distinct_resources",
            "resource_lineage",
            "parent_resource_id <> child_resource_id",
        )
    if "ck_resource_lineage_relationship" not in constraints:
        op.create_check_constraint(
            "ck_resource_lineage_relationship",
            "resource_lineage",
            "relationship IN ('derived_from', 'aliquot_of', 'split_from', 'pooled_from')",
        )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS resource_lineage_append_only "
        "ON public.resource_lineage"
    )
    op.drop_constraint(
        "ck_resource_lineage_relationship", "resource_lineage", type_="check"
    )
    op.drop_constraint(
        "ck_resource_lineage_distinct_resources",
        "resource_lineage",
        type_="check",
    )
    op.drop_constraint(
        "ck_resource_lineage_record_pair", "resource_lineage", type_="check"
    )
    op.drop_constraint(
        "uq_resource_lineage_idempotency", "resource_lineage", type_="unique"
    )
    op.drop_constraint(
        "fk_resource_lineage_created_by_user_id_users",
        "resource_lineage",
        type_="foreignkey",
    )
    op.execute("DELETE FROM resource_lineage WHERE record_id IS NULL")
    op.alter_column("resource_lineage", "record_version", nullable=False)
    op.alter_column("resource_lineage", "record_id", nullable=False)
    for column_name in (
        "idempotency_key",
        "created_by_user_id",
        "reason",
        "source_action_id",
    ):
        op.drop_column("resource_lineage", column_name)
    op.execute(
        """
        CREATE TRIGGER resource_lineage_append_only
        BEFORE UPDATE OR DELETE ON public.resource_lineage
        FOR EACH ROW EXECUTE FUNCTION public.prevent_resource_event_mutation()
        """
    )
