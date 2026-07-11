"""Add single-use account invitation and recovery tokens.

Revision ID: 0002_single_lab_account_tokens
Revises: 0001_initial_schema
Create Date: 2026-07-11 00:00:00.000000
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_single_lab_account_tokens"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_security",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "account_tokens",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("uuid_generate_v7()"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("token_type", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False, server_default=""),
        sa.Column("lab_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("lab_role", sa.Integer(), nullable=True),
        sa.Column("project_role", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["lab_id"], ["labs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_account_tokens_id", "account_tokens", ["id"])
    op.create_index(
        "ix_account_tokens_token_hash",
        "account_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_account_tokens_token_type",
        "account_tokens",
        ["token_type"],
    )
    op.create_index("ix_account_tokens_email", "account_tokens", ["email"])
    op.create_index("ix_account_tokens_lab_id", "account_tokens", ["lab_id"])
    op.create_index("ix_account_tokens_user_id", "account_tokens", ["user_id"])
    op.create_index(
        "ix_account_tokens_expires_at",
        "account_tokens",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_account_tokens_expires_at", table_name="account_tokens")
    op.drop_index("ix_account_tokens_user_id", table_name="account_tokens")
    op.drop_index("ix_account_tokens_lab_id", table_name="account_tokens")
    op.drop_index("ix_account_tokens_email", table_name="account_tokens")
    op.drop_index("ix_account_tokens_token_type", table_name="account_tokens")
    op.drop_index("ix_account_tokens_token_hash", table_name="account_tokens")
    op.drop_index("ix_account_tokens_id", table_name="account_tokens")
    op.drop_table("account_tokens")
    op.drop_table("account_security")
