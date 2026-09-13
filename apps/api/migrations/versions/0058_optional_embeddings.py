"""Keep keyword indexes usable without model access; preserve existing vectors."""

from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0058_optional_embeddings"
down_revision = "0057_instrument_survey"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "embeddings", "embedding", existing_type=Vector(1024), nullable=True
    )


def downgrade():
    # Fail closed if keyword-only rows exist. Do not silently delete their text
    # or invent zero vectors; reindex first or restore the pre-upgrade backup.
    op.alter_column(
        "embeddings", "embedding", existing_type=Vector(1024), nullable=False
    )
