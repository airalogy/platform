"""Project-scoped external Agent grants, approvals and audit."""

import sqlalchemy as sa
from alembic import op

revision = "0078_external_agent_access"
down_revision = "0077_record_resource_reservation"
branch_labels = None
depends_on = None
TABLE_NAMES = (
    "external_access_policies",
    "external_grants",
    "external_operations",
    "external_access_audit",
)


def upgrade():
    op.create_table(
        "external_access_policies",
        sa.Column(
            "lab_id",
            sa.UUID(),
            sa.ForeignKey("labs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("blocked_fields", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.create_table(
        "external_grants",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("token_prefix", sa.String(20), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "external_operations",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "grant_id",
            sa.UUID(),
            sa.ForeignKey("external_grants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("request_key", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column(
            "protocol_id",
            sa.UUID(),
            sa.ForeignKey("protocols.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("protocol_version_id", sa.UUID(), nullable=False),
        sa.Column("policy_revision", sa.Integer(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "grant_id", "request_key", name="uq_external_operation_request"
        ),
    )
    op.create_table(
        "external_access_audit",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "grant_id",
            sa.UUID(),
            sa.ForeignKey("external_grants.id", ondelete="SET NULL"),
        ),
        sa.Column("event", sa.String(80), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    for table in (
        "external_access_audit",
        "external_operations",
        "external_grants",
        "external_access_policies",
    ):
        op.drop_table(table)
