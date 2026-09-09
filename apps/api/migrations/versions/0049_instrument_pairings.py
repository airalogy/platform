"""Add single-use, administrator-confirmed Gateway enrollment.

Revision ID: 0049_instrument_pairings
Revises: 0048_instrument_integration_drafts
"""

import sqlalchemy as sa
from alembic import op

revision = "0049_instrument_pairings"
down_revision = "0048_instrument_integration_drafts"
branch_labels = None
depends_on = None
TABLE_NAMES = ("instrument_pairings",)


def upgrade():
    op.create_table(
        "instrument_pairings",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            server_default=sa.text("uuid_generate_v7()"),
        ),
        sa.Column(
            "gateway_id",
            sa.UUID(),
            sa.ForeignKey("research_instrument_gateways.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("gateway_revision", sa.Integer(), nullable=False),
        sa.Column("code_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("client_name", sa.String(128)),
        sa.Column("credential_digest", sa.String(64)),
        sa.Column("credential_hint", sa.String(8)),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('pending','claimed','confirmed','cancelled')",
            name="ck_instrument_pairing_state",
        ),
    )
    op.create_index(
        "ix_instrument_pairings_gateway_id", "instrument_pairings", ["gateway_id"]
    )


def downgrade():
    op.drop_table("instrument_pairings")
