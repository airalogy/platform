"""Lab-private immutable adapter releases and source-review history.

Revision ID: 0050_instrument_adapter_packages
Revises: 0049_instrument_pairings
"""

import sqlalchemy as sa
from alembic import op

revision = "0050_instrument_adapter_packages"
down_revision = "0049_instrument_pairings"
branch_labels = None
depends_on = None
TABLE_NAMES = ("instrument_adapter_releases", "instrument_adapter_release_audits")


def upgrade():
    op.create_table(
        "instrument_adapter_releases",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "lab_id",
            sa.UUID(),
            sa.ForeignKey("labs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "research_file_id",
            sa.UUID(),
            sa.ForeignKey("research_files.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("package_key", sa.String(128), nullable=False),
        sa.Column("package_version", sa.String(64), nullable=False),
        sa.Column("archive_digest", sa.String(64), nullable=False),
        sa.Column("manifest_digest", sa.String(64), nullable=False),
        sa.Column("inspection", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
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
        sa.UniqueConstraint(
            "lab_id",
            "package_key",
            "package_version",
            name="uq_instrument_adapter_version",
        ),
        sa.CheckConstraint(
            "state IN ('imported','approved','revoked')",
            name="ck_instrument_adapter_state",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_instrument_adapter_revision"),
    )
    op.create_index(
        "ix_instrument_adapter_releases_lab_id",
        "instrument_adapter_releases",
        ["lab_id"],
    )
    op.create_table(
        "instrument_adapter_release_audits",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            server_default=sa.text("uuid_generate_v7()"),
        ),
        sa.Column(
            "release_id",
            sa.UUID(),
            sa.ForeignKey("instrument_adapter_releases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column(
            "actor_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "release_id", "revision", name="uq_instrument_adapter_audit_revision"
        ),
    )
    op.create_index(
        "ix_instrument_adapter_release_audits_release_id",
        "instrument_adapter_release_audits",
        ["release_id"],
    )


def downgrade():
    op.drop_table("instrument_adapter_release_audits")
    op.drop_table("instrument_adapter_releases")
