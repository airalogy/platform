"""Add versioned Lab Research autonomy policies.

Revision ID: 0040_research_autonomy_policy
Revises: 0039_research_action_dependency_guard
Create Date: 2026-09-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.model_registry import import_models

revision: str = "0040_research_autonomy_policy"
down_revision: str | None = "0039_research_action_dependency_guard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAMES = (
    "research_autonomy_policies",
    "research_autonomy_policy_audits",
)


def _tables(metadata):
    return [metadata.tables[name] for name in TABLE_NAMES]


def upgrade() -> None:
    bind = op.get_bind()
    import_models()
    from app.models.base import Base

    Base.metadata.create_all(bind=bind, tables=_tables(Base.metadata))
    columns = {
        item["name"] for item in sa.inspect(bind).get_columns("research_actions")
    }
    if "policy_reason" not in columns:
        op.add_column(
            "research_actions",
            sa.Column(
                "policy_reason",
                sa.Text(),
                nullable=False,
                server_default="",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    import_models()
    from app.models.base import Base

    columns = {
        item["name"] for item in sa.inspect(bind).get_columns("research_actions")
    }
    if "policy_reason" in columns:
        op.drop_column("research_actions", "policy_reason")
    Base.metadata.drop_all(bind=bind, tables=list(reversed(_tables(Base.metadata))))
