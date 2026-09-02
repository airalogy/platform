"""Add governed Instrument Gateway configuration.

Revision ID: 0026_research_instrument_gateways
Revises: 0025_research_notifications
Create Date: 2026-09-03 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
from migrations.model_registry import import_models

revision: str = "0026_research_instrument_gateways"
down_revision: str | None = "0025_research_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAMES = (
    "research_instrument_gateways",
    "research_instrument_commands",
    "research_instrument_gateway_audits",
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
