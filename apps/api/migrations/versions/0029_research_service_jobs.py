"""Add governed external research-service job lifecycle.

Revision ID: 0029_research_service_jobs
Revises: 0028_research_service_catalog
Create Date: 2026-09-03 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

from migrations.model_registry import import_models

revision: str = "0029_research_service_jobs"
down_revision: str | None = "0028_research_service_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAMES = (
    "research_service_jobs",
    "research_service_quotes",
    "research_service_custody_events",
    "research_service_result_assets",
)


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
