"""Add versioned DataAsset, Evidence, and Claim models.

Revision ID: 0014_research_assets
Revises: 0013_research_log
Create Date: 2026-09-02 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
from migrations.model_registry import import_models

revision: str = "0014_research_assets"
down_revision: str | None = "0013_research_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAMES = (
    "data_assets",
    "data_asset_versions",
    "research_evidence",
    "research_claims",
    "research_claim_revisions",
    "research_claim_evidence",
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
