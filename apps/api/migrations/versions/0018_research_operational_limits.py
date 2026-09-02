"""Add Research Task time and budget controls.

Revision ID: 0018_research_operational_limits
Revises: 0017_research_resource_reservations
Create Date: 2026-09-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from migrations.model_registry import import_models

revision: str = "0018_research_operational_limits"
down_revision: str | None = "0017_research_resource_reservations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAMES = ("research_budget_entries",)
ADDED_COLUMNS = {"deadline_at", "budget_limit", "budget_currency"}
BUDGET_CONSTRAINT = "ck_research_tasks_budget_pair"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {
        column["name"] for column in inspector.get_columns("research_tasks")
    }
    if "deadline_at" not in columns:
        op.add_column(
            "research_tasks",
            sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "budget_limit" not in columns:
        op.add_column(
            "research_tasks",
            sa.Column("budget_limit", sa.Numeric(38, 18), nullable=True),
        )
    if "budget_currency" not in columns:
        op.add_column(
            "research_tasks",
            sa.Column("budget_currency", sa.String(length=3), nullable=True),
        )
    check_constraints = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("research_tasks")
    }
    if BUDGET_CONSTRAINT not in check_constraints:
        op.create_check_constraint(
            BUDGET_CONSTRAINT,
            "research_tasks",
            "((budget_limit IS NULL AND budget_currency IS NULL) OR "
            "(budget_limit > 0 AND budget_currency IS NOT NULL AND "
            "length(budget_currency) = 3 AND "
            "budget_currency = upper(budget_currency)))",
        )
    import_models()
    from app.models.base import Base

    Base.metadata.tables[TABLE_NAMES[0]].create(bind=bind, checkfirst=True)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.prevent_research_budget_entry_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'research_budget_entries is append-only';
        END;
        $$
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS research_budget_entries_append_only "
        "ON public.research_budget_entries"
    )
    op.execute(
        """
        CREATE TRIGGER research_budget_entries_append_only
        BEFORE UPDATE OR DELETE ON public.research_budget_entries
        FOR EACH ROW EXECUTE FUNCTION public.prevent_research_budget_entry_mutation()
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {
        column["name"] for column in inspector.get_columns("research_tasks")
    }
    check_constraints = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("research_tasks")
    }
    import_models()
    from app.models.base import Base

    op.execute(
        "DROP TRIGGER IF EXISTS research_budget_entries_append_only "
        "ON public.research_budget_entries"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS public.prevent_research_budget_entry_mutation()"
    )
    Base.metadata.tables[TABLE_NAMES[0]].drop(bind=bind, checkfirst=True)
    if BUDGET_CONSTRAINT in check_constraints:
        op.drop_constraint(BUDGET_CONSTRAINT, "research_tasks", type_="check")
    for column in ("budget_currency", "budget_limit", "deadline_at"):
        if column in columns:
            op.drop_column("research_tasks", column)
