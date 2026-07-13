"""Add structured team and scoped access control.

Revision ID: 0003_structured_access_control
Revises: 0002_single_lab_account_tokens
Create Date: 2026-07-13 00:00:00.000000
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_structured_access_control"
down_revision: str | None = "0002_single_lab_account_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Revision 0001 creates its tables from current model metadata. These guards
    # keep both old-database upgrades and fresh installs valid when later model
    # columns are already present during 0001.
    op.execute("ALTER TABLE groups ADD COLUMN IF NOT EXISTS parent_group_id INTEGER")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'groups'::regclass
                  AND contype = 'f'
                  AND pg_get_constraintdef(oid)
                      LIKE 'FOREIGN KEY (parent_group_id)%'
            ) THEN
                ALTER TABLE groups
                ADD CONSTRAINT fk_groups_parent_group_id_groups
                FOREIGN KEY (parent_group_id) REFERENCES groups (id) ON DELETE RESTRICT;
            END IF;
        END
        $$
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_groups_parent_group_id "
        "ON groups (parent_group_id)"
    )
    op.execute(
        "ALTER TABLE group_users ADD COLUMN IF NOT EXISTS "
        "membership_role VARCHAR DEFAULT 'member' NOT NULL"
    )
    op.execute(
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS "
        "inherit_permissions BOOLEAN DEFAULT true NOT NULL"
    )
    op.execute(
        "ALTER TABLE protocols ADD COLUMN IF NOT EXISTS "
        "inherit_permissions BOOLEAN DEFAULT true NOT NULL"
    )

    op.create_table(
        "access_grants",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("uuid_generate_v7()"), nullable=False
        ),
        sa.Column("lab_id", sa.UUID(), nullable=False),
        sa.Column("subject_type", sa.String(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("protocol_id", sa.UUID(), nullable=True),
        sa.Column("role_key", sa.String(), nullable=False),
        sa.Column("inherit_to_children", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "(subject_type = 'user' AND user_id IS NOT NULL AND group_id IS NULL) "
            "OR (subject_type = 'team' AND group_id IS NOT NULL AND user_id IS NULL)",
            name="ck_access_grants_subject",
        ),
        sa.CheckConstraint(
            "(scope_type = 'lab' AND project_id IS NULL AND protocol_id IS NULL) "
            "OR (scope_type = 'project' AND project_id IS NOT NULL AND protocol_id IS NULL) "
            "OR (scope_type = 'protocol' AND protocol_id IS NOT NULL)",
            name="ck_access_grants_scope",
        ),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lab_id"], ["labs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["protocol_id"], ["protocols.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("id", "lab_id", "user_id", "group_id", "project_id", "protocol_id", "expires_at", "revoked_at"):
        op.create_index(f"ix_access_grants_{column}", "access_grants", [column])
    op.create_index(
        "ix_access_grants_lab_active",
        "access_grants",
        ["lab_id", "revoked_at", "expires_at"],
    )
    op.create_index(
        "ix_access_grants_user_active", "access_grants", ["user_id", "revoked_at"]
    )
    op.create_index(
        "ix_access_grants_group_active", "access_grants", ["group_id", "revoked_at"]
    )

    op.create_table(
        "access_grant_audits",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("uuid_generate_v7()"), nullable=False
        ),
        sa.Column("grant_id", sa.UUID(), nullable=False),
        sa.Column("lab_id", sa.UUID(), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("before_state", sa.JSON(), nullable=True),
        sa.Column("after_state", sa.JSON(), nullable=True),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["lab_id"], ["labs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("id", "grant_id", "lab_id", "actor_user_id"):
        op.create_index(
            f"ix_access_grant_audits_{column}", "access_grant_audits", [column]
        )
    op.create_index(
        "ix_access_grant_audits_lab_created",
        "access_grant_audits",
        ["lab_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("access_grant_audits")
    op.drop_table("access_grants")
    op.execute(
        "ALTER TABLE groups DROP CONSTRAINT IF EXISTS "
        "fk_groups_parent_group_id_groups"
    )
    op.execute(
        "ALTER TABLE groups DROP CONSTRAINT IF EXISTS groups_parent_group_id_fkey"
    )
    op.execute("DROP INDEX IF EXISTS ix_groups_parent_group_id")
    op.execute("ALTER TABLE protocols DROP COLUMN IF EXISTS inherit_permissions")
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS inherit_permissions")
    op.execute("ALTER TABLE group_users DROP COLUMN IF EXISTS membership_role")
    op.execute("ALTER TABLE groups DROP COLUMN IF EXISTS parent_group_id")
