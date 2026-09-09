"""Separate physical completion, file delivery and reviewed Record association."""

import sqlalchemy as sa
from alembic import op

revision = "0054_instrument_outputs"
down_revision = "0053_instrument_activations"
branch_labels = None
depends_on = None
TABLE_NAMES = (
    "instrument_output_batches",
    "instrument_outputs",
    "instrument_output_associations",
)


def upgrade():
    op.create_table(
        "instrument_output_batches",
        sa.Column(
            "job_id",
            sa.UUID(),
            sa.ForeignKey("research_instrument_jobs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "created_by_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("lineage", sa.JSON(), nullable=False),
        sa.Column("capture", sa.JSON()),
        sa.Column("finalized_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "instrument_outputs",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "job_id",
            sa.UUID(),
            sa.ForeignKey("instrument_output_batches.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column(
            "research_file_id",
            sa.UUID(),
            sa.ForeignKey("research_files.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "data_asset_version_id",
            sa.UUID(),
            sa.ForeignKey("data_asset_versions.id", ondelete="RESTRICT"),
        ),
        sa.Column("received_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("job_id", "name", name="uq_instrument_output_name"),
    )
    op.create_index("ix_instrument_outputs_job_id", "instrument_outputs", ["job_id"])
    op.create_index(
        "ix_instrument_outputs_research_file_id",
        "instrument_outputs",
        ["research_file_id"],
    )
    op.create_table(
        "instrument_output_associations",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "output_id",
            sa.UUID(),
            sa.ForeignKey("instrument_outputs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("record_hash", sa.String(128), nullable=False),
        sa.Column("sample_reference", sa.String(1024), nullable=False),
        sa.Column("confirmation_digest", sa.String(64), nullable=False),
        sa.Column(
            "created_by_user_id",
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
        sa.ForeignKeyConstraint(
            ["record_id", "record_version"],
            ["records.id", "records.version"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "output_id", "revision", name="uq_instrument_output_association_revision"
        ),
        sa.CheckConstraint(
            "revision > 0", name="ck_instrument_output_association_revision"
        ),
    )
    op.create_index(
        "ix_instrument_output_associations_output_id",
        "instrument_output_associations",
        ["output_id"],
    )


def downgrade():
    for table in reversed(TABLE_NAMES):
        op.drop_table(table)
