"""Separate source and interface development authority; preserve existing grants."""

import sqlalchemy as sa
from alembic import op

revision = "0056_instrument_exploration"
down_revision = "0055_instrument_authoring"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "instrument_authoring_sessions",
        sa.Column("purpose", sa.String(16), nullable=False, server_default="source"),
    )
    op.create_check_constraint(
        "ck_authoring_purpose",
        "instrument_authoring_sessions",
        "purpose IN ('source','interface')",
    )
    op.add_column("instrument_authoring_turns", sa.Column("input", sa.JSON()))


def downgrade():
    # An older source-only server must never interpret an interface grant as source authority.
    op.execute("DELETE FROM instrument_authoring_sessions WHERE purpose = 'interface'")
    op.drop_column("instrument_authoring_turns", "input")
    op.drop_constraint(
        "ck_authoring_purpose", "instrument_authoring_sessions", type_="check"
    )
    op.drop_column("instrument_authoring_sessions", "purpose")
