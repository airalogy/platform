"""Persist scoped development authority separately from instrument execution."""

import sqlalchemy as sa
from alembic import op

revision = "0055_instrument_authoring"
down_revision = "0054_instrument_outputs"
branch_labels = None
depends_on = None
TABLE_NAMES = ("instrument_authoring_sessions", "instrument_authoring_turns")


def upgrade():
    op.create_table(
        "instrument_authoring_sessions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "gateway_id",
            sa.UUID(),
            sa.ForeignKey("research_instrument_gateways.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "resource_id",
            sa.UUID(),
            sa.ForeignKey("resources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("scope_pin", sa.JSON(), nullable=False),
        sa.Column("confirmation_digest", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("state IN ('open','cancelled')", name="ck_authoring_state"),
    )
    op.create_index(
        "ix_instrument_authoring_sessions_gateway_id",
        "instrument_authoring_sessions",
        ["gateway_id"],
    )
    op.create_table(
        "instrument_authoring_turns",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "session_id",
            sa.UUID(),
            sa.ForeignKey("instrument_authoring_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("previous_id", sa.UUID()),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("proposal", sa.JSON()),
        sa.Column("candidate_digest", sa.String(64)),
        sa.Column("error", sa.String(64)),
        sa.Column("report", sa.JSON()),
        sa.Column("operation_id", sa.String(128), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("session_id", "ordinal", name="uq_authoring_turn_ordinal"),
        sa.CheckConstraint("ordinal BETWEEN 1 AND 5", name="ck_authoring_turn_ordinal"),
        sa.CheckConstraint(
            "state IN ('generating','generated','failed')",
            name="ck_authoring_turn_state",
        ),
    )
    op.create_index(
        "ix_instrument_authoring_turns_session_id",
        "instrument_authoring_turns",
        ["session_id"],
    )


def downgrade():
    for table in reversed(TABLE_NAMES):
        op.drop_table(table)
