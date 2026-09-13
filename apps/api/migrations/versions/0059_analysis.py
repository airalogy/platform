"""Persist private, reproducible Record analysis previews, runs, and recipes."""

import sqlalchemy as sa
from alembic import op

revision = "0059_analysis"
down_revision = "0058_optional_embeddings"
branch_labels = None
depends_on = None

TABLE_NAMES = (
    "analysis_pipelines",
    "analysis_pipeline_revisions",
    "analysis_runs",
    "analysis_previews",
)


def _identity():
    return sa.Column(
        "id", sa.UUID(), primary_key=True, server_default=sa.func.uuid_generate_v7()
    )


def _created_at():
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


def _owner():
    return sa.Column(
        "created_by_user_id",
        sa.UUID(),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )


def _scope():
    return (
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "protocol_id",
            sa.UUID(),
            sa.ForeignKey("protocols.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        _owner(),
    )


def _recipe_and_sources():
    return (
        sa.Column(
            "pipeline_revision_id",
            sa.UUID(),
            sa.ForeignKey("analysis_pipeline_revisions.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "rerun_of_id",
            sa.UUID(),
            sa.ForeignKey("analysis_runs.id", ondelete="RESTRICT"),
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("recipe", sa.JSON(), nullable=False),
        sa.Column("source_selection", sa.JSON(), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("recipe_digest", sa.String(64), nullable=False),
        sa.Column("preview_digest", sa.String(64), nullable=False),
    )


def _source_indexes(table):
    for column in ("project_id", "protocol_id"):
        op.create_index(f"ix_{table}_{column}", table, [column])


def _recipe_indexes(table):
    for column in ("pipeline_revision_id", "rerun_of_id"):
        op.create_index(f"ix_{table}_{column}", table, [column])


def upgrade():
    # Frozen DDL deliberately does not import mutable application model metadata.
    op.create_table(
        "analysis_pipelines",
        _identity(),
        *_scope(),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("current_revision", sa.Integer(), nullable=False),
        _created_at(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "current_revision >= 1", name="ck_analysis_pipeline_revision"
        ),
    )
    _source_indexes("analysis_pipelines")
    op.create_index(
        "ix_analysis_pipelines_owner_protocol_created",
        "analysis_pipelines",
        ["created_by_user_id", "protocol_id", "created_at"],
    )
    op.create_table(
        "analysis_pipeline_revisions",
        _identity(),
        sa.Column(
            "pipeline_id",
            sa.UUID(),
            sa.ForeignKey("analysis_pipelines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("recipe", sa.JSON(), nullable=False),
        sa.Column("recipe_digest", sa.String(64), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("source_selection", sa.JSON(), nullable=False),
        _owner(),
        _created_at(),
        sa.UniqueConstraint(
            "pipeline_id", "revision", name="uq_analysis_pipeline_revision"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_analysis_recipe_revision"),
        sa.CheckConstraint(
            "recipe_digest ~ '^[0-9a-f]{64}$'", name="ck_analysis_recipe_digest"
        ),
    )
    op.create_index(
        "ix_analysis_pipeline_revisions_pipeline_id",
        "analysis_pipeline_revisions",
        ["pipeline_id"],
    )
    op.create_table(
        "analysis_runs",
        _identity(),
        *_scope(),
        *_recipe_and_sources(),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("client_idempotency_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("engine_version", sa.String(64), nullable=False),
        sa.Column("result", sa.JSON(none_as_null=True)),
        sa.Column("result_digest", sa.String(64)),
        sa.Column("error", sa.Text()),
        sa.Column(
            "job_id",
            sa.UUID(),
            sa.ForeignKey("persistent_jobs.id", ondelete="SET NULL"),
        ),
        _created_at(),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "created_by_user_id",
            "client_idempotency_key",
            name="uq_analysis_run_owner_idempotency",
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','succeeded','failed','cancelled')",
            name="ck_analysis_run_status",
        ),
        sa.CheckConstraint(
            "rerun_of_id IS NULL OR rerun_of_id <> id", name="ck_analysis_run_not_self"
        ),
        sa.CheckConstraint(
            "source_digest ~ '^[0-9a-f]{64}$'", name="ck_analysis_run_source_digest"
        ),
        sa.CheckConstraint(
            "recipe_digest ~ '^[0-9a-f]{64}$'", name="ck_analysis_run_recipe_digest"
        ),
        sa.CheckConstraint(
            "preview_digest ~ '^[0-9a-f]{64}$'", name="ck_analysis_run_preview_digest"
        ),
        sa.CheckConstraint(
            "result_digest IS NULL OR result_digest ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_run_result_digest",
        ),
        sa.CheckConstraint(
            "(result IS NULL) = (result_digest IS NULL)",
            name="ck_analysis_run_result_pair",
        ),
    )
    _source_indexes("analysis_runs")
    _recipe_indexes("analysis_runs")
    op.create_index("ix_analysis_runs_job_id", "analysis_runs", ["job_id"])
    op.create_index(
        "ix_analysis_runs_owner_protocol_created",
        "analysis_runs",
        ["created_by_user_id", "protocol_id", "created_at"],
    )
    op.create_index(
        "ix_analysis_runs_status_created", "analysis_runs", ["status", "created_at"]
    )
    op.create_table(
        "analysis_previews",
        _identity(),
        *_scope(),
        *_recipe_and_sources(),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "source_digest ~ '^[0-9a-f]{64}$'", name="ck_analysis_preview_source_digest"
        ),
        sa.CheckConstraint(
            "recipe_digest ~ '^[0-9a-f]{64}$'", name="ck_analysis_preview_recipe_digest"
        ),
        sa.CheckConstraint(
            "preview_digest ~ '^[0-9a-f]{64}$'", name="ck_analysis_preview_digest"
        ),
    )
    _source_indexes("analysis_previews")
    _recipe_indexes("analysis_previews")
    op.create_index(
        "ix_analysis_previews_owner_expires",
        "analysis_previews",
        ["created_by_user_id", "expires_at"],
    )


def downgrade():
    for table in reversed(TABLE_NAMES):
        op.drop_table(table)
