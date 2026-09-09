"""Persist exact, scope-limited instrument acceptance without enabling execution."""

import sqlalchemy as sa
from alembic import op

revision = "0052_instrument_qualifications"
down_revision = "0051_instrument_device_bindings"
branch_labels = None
depends_on = None
TABLE_NAMES = ("instrument_qualifications",)


def upgrade():
    op.create_table(
        "instrument_qualifications",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "binding_id",
            sa.UUID(),
            sa.ForeignKey("instrument_device_bindings.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "lab_id",
            sa.UUID(),
            sa.ForeignKey("labs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("pins", sa.JSON(), nullable=False),
        sa.Column("evidence_files", sa.JSON(), nullable=False),
        sa.Column("confirmation_digest", sa.String(64), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "revoked_by_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "scope IN ('simulation','read_only','controlled')",
            name="ck_instrument_qualification_scope",
        ),
        sa.CheckConstraint(
            "outcome IN ('passed','failed')", name="ck_instrument_qualification_outcome"
        ),
    )
    for field in ("binding_id", "lab_id"):
        op.create_index(
            f"ix_instrument_qualifications_{field}",
            "instrument_qualifications",
            [field],
        )


def downgrade():
    op.drop_table("instrument_qualifications")
