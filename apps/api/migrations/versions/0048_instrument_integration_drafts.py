"""Persist private, versioned GUI integration rehearsals (not device authority).

Revision ID: 0048_instrument_integration_drafts
Revises: 0047_instrument_control_sessions
"""

import sqlalchemy as sa
from alembic import op

revision = "0048_instrument_integration_drafts"
down_revision = "0047_instrument_control_sessions"
branch_labels = None
depends_on = None
TABLE_NAME = "instrument_integration_drafts"
TABLE_NAMES = (TABLE_NAME,)


def upgrade() -> None:
    if TABLE_NAME in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE_NAME,
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
            "resource_revision_id",
            sa.UUID(),
            sa.ForeignKey("resource_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("bundle", sa.JSON(), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "updated_by_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("revision >= 1", name="ck_integration_revision"),
        sa.CheckConstraint("length(content_digest) = 64", name="ck_integration_digest"),
    )
    op.create_index(
        "ix_instrument_integration_drafts_gateway_id", TABLE_NAME, ["gateway_id"]
    )


def downgrade() -> None:
    if TABLE_NAME in sa.inspect(op.get_bind()).get_table_names():
        op.drop_index(
            "ix_instrument_integration_drafts_gateway_id", table_name=TABLE_NAME
        )
        op.drop_table(TABLE_NAME)
