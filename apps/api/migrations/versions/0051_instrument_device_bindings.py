"""Pin equipment/package/configuration and independently authorize installation.

Revision ID: 0051_instrument_device_bindings
Revises: 0050_instrument_adapter_packages
"""

import sqlalchemy as sa
from alembic import op

revision = "0051_instrument_device_bindings"
down_revision = "0050_instrument_adapter_packages"
branch_labels = None
depends_on = None
TABLE_NAMES = ("instrument_device_bindings", "instrument_device_binding_audits")


def upgrade():
    op.create_table(
        "instrument_device_bindings",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "lab_id",
            sa.UUID(),
            sa.ForeignKey("labs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "gateway_id",
            sa.UUID(),
            sa.ForeignKey("research_instrument_gateways.id", ondelete="RESTRICT"),
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
        sa.Column("resource_revision", sa.Integer(), nullable=False),
        sa.Column(
            "release_id",
            sa.UUID(),
            sa.ForeignKey("instrument_adapter_releases.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("release_revision", sa.Integer(), nullable=False),
        sa.Column("gateway_credential_pin", sa.String(64), nullable=False),
        sa.Column("installer_token_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("installer_fingerprint", sa.String(64), nullable=False),
        sa.Column("descriptor", sa.JSON(), nullable=False),
        sa.Column("authorization_digest", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("receipt", sa.JSON(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("creator_auth_version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('authorized','installing','installed','expired','revoked')",
            name="ck_instrument_binding_state",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_instrument_binding_revision"),
    )
    for field in ("lab_id", "gateway_id", "resource_id", "release_id"):
        op.create_index(
            f"ix_instrument_device_bindings_{field}",
            "instrument_device_bindings",
            [field],
        )
    op.create_index(
        "uq_instrument_binding_pending_gateway",
        "instrument_device_bindings",
        ["gateway_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('authorized','installing')"),
    )
    op.create_table(
        "instrument_device_binding_audits",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            server_default=sa.text("uuid_generate_v7()"),
        ),
        sa.Column(
            "binding_id",
            sa.UUID(),
            sa.ForeignKey("instrument_device_bindings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "actor_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "binding_id", "revision", name="uq_instrument_binding_audit_revision"
        ),
    )
    op.create_index(
        "ix_instrument_device_binding_audits_binding_id",
        "instrument_device_binding_audits",
        ["binding_id"],
    )


def downgrade():
    op.drop_table("instrument_device_binding_audits")
    op.drop_table("instrument_device_bindings")
