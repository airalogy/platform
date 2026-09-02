"""Add typed digital Tool Job and Wait Event Actions.

Revision ID: 0015_research_digital_actions
Revises: 0014_research_assets
Create Date: 2026-09-02 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
from migrations.model_registry import import_models

revision: str = "0015_research_digital_actions"
down_revision: str | None = "0014_research_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAMES = ("research_tool_jobs", "research_wait_events")


def _tables(metadata):
    return [metadata.tables[name] for name in TABLE_NAMES]


def upgrade() -> None:
    bind = op.get_bind()
    import_models()
    from app.models.base import Base

    Base.metadata.create_all(bind=bind, tables=_tables(Base.metadata))


def downgrade() -> None:
    bind = op.get_bind()
    import_models()
    from app.models.base import Base

    Base.metadata.drop_all(bind=bind, tables=list(reversed(_tables(Base.metadata))))
