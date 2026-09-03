"""Add declared Compute Job output assets.

Revision ID: 0033_research_compute_outputs
Revises: 0032_research_compute_jobs
Create Date: 2026-09-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from migrations.model_registry import import_models

revision: str = "0033_research_compute_outputs"
down_revision: str | None = "0032_research_compute_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAMES = ("research_compute_job_outputs",)


def upgrade() -> None:
    bind = op.get_bind()
    import_models()
    from app.models.base import Base

    op.add_column(
        "research_compute_jobs",
        sa.Column(
            "output_manifest",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    Base.metadata.create_all(
        bind=bind,
        tables=[Base.metadata.tables[name] for name in TABLE_NAMES],
    )


def downgrade() -> None:
    bind = op.get_bind()
    import_models()
    from app.models.base import Base

    Base.metadata.drop_all(
        bind=bind,
        tables=[Base.metadata.tables[name] for name in reversed(TABLE_NAMES)],
    )
    op.drop_column("research_compute_jobs", "output_manifest")
