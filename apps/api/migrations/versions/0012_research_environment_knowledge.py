"""Pin reviewed Knowledge in Research Environments.

Revision ID: 0012_research_environment_knowledge
Revises: 0011_knowledge_core
Create Date: 2026-09-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from migrations.model_registry import import_models

revision: str = "0012_research_environment_knowledge"
down_revision: str | None = "0011_knowledge_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAMES = ("research_task_knowledge",)
ALEMBIC_VERSION_LENGTH = 128


def _tables(metadata):
    return [metadata.tables[name] for name in TABLE_NAMES]


def upgrade() -> None:
    bind = op.get_bind()
    # Alembic creates this internal column as VARCHAR(32). This and later
    # descriptive revision IDs are intentionally longer, so widen the column
    # before Alembic records this revision after upgrade() returns.
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=ALEMBIC_VERSION_LENGTH),
        existing_nullable=False,
    )
    import_models()
    from app.models.base import Base

    Base.metadata.create_all(bind=bind, tables=_tables(Base.metadata))


def downgrade() -> None:
    bind = op.get_bind()
    import_models()
    from app.models.base import Base

    Base.metadata.drop_all(bind=bind, tables=list(reversed(_tables(Base.metadata))))
    # Keep alembic_version widened. Alembic still stores this long revision ID
    # until downgrade() returns, so narrowing here would make the downgrade fail.
