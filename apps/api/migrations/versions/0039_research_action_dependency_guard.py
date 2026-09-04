"""Guard Research Action dependency self edges.

Revision ID: 0039_research_action_dependency_guard
Revises: 0038_research_resource_consumptions
Create Date: 2026-09-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039_research_action_dependency_guard"
down_revision: str | None = "0038_research_resource_consumptions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT_NAME = "ck_research_action_dependency_not_self"


def _constraint_exists() -> bool:
    inspector = sa.inspect(op.get_bind())
    constraints = {
        constraint["name"]
        for constraint in inspector.get_check_constraints(
            "research_action_dependencies"
        )
    }
    return CONSTRAINT_NAME in constraints


def upgrade() -> None:
    if not _constraint_exists():
        op.create_check_constraint(
            CONSTRAINT_NAME,
            "research_action_dependencies",
            "action_id <> depends_on_action_id",
        )


def downgrade() -> None:
    if _constraint_exists():
        op.drop_constraint(
            CONSTRAINT_NAME,
            "research_action_dependencies",
            type_="check",
        )
