"""Seal private exact Record attachments without publishing DataAssets."""

import sqlalchemy as sa
from alembic import op

revision = "0069_analysis_input_files"
down_revision = "0068_workflow_file_bindings"
branch_labels = None
depends_on = None
TABLE_NAMES = ("analysis_compute_input_files",)


def upgrade():
    op.add_column(
        "analysis_computations",
        sa.Column(
            "input_file_manifest", sa.JSON(), nullable=False, server_default="{}"
        ),
    )
    op.create_table(
        "analysis_compute_input_files",
        sa.Column(
            "input_row_id",
            sa.UUID(),
            sa.ForeignKey("research_compute_job_inputs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "analysis_run_id",
            sa.UUID(),
            sa.ForeignKey("analysis_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_file_id",
            sa.UUID(),
            sa.ForeignKey("airalogy_files.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "blob_id",
            sa.UUID(),
            sa.ForeignKey("research_file_blobs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("input_id", sa.String(24), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["record_id", "record_version"],
            ["records.id", "records.version"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "analysis_run_id",
            "record_id",
            "record_version",
            "input_id",
            name="uq_analysis_compute_input_file_source",
        ),
        sa.CheckConstraint(
            "digest ~ '^[0-9a-f]{64}$'", name="ck_analysis_input_file_digest"
        ),
        sa.CheckConstraint(
            "record_version >= 1", name="ck_analysis_input_file_record_version"
        ),
    )
    for column in ("analysis_run_id", "source_file_id", "blob_id"):
        op.create_index(
            f"ix_analysis_compute_input_files_{column}",
            "analysis_compute_input_files",
            [column],
        )
    op.execute(
        "CREATE TRIGGER immutable_analysis_compute_input_files BEFORE UPDATE ON analysis_compute_input_files FOR EACH ROW EXECUTE FUNCTION reject_workflow_history_update()"
    )
    op.execute("""
        CREATE FUNCTION protect_analysis_attachment_metadata() RETURNS trigger AS $$
        BEGIN
          IF to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN
            IF TG_TABLE_NAME = 'airalogy_files' AND EXISTS (
              SELECT 1 FROM analysis_compute_input_files WHERE source_file_id = OLD.id
            ) THEN RAISE EXCEPTION 'Analysis attachment file metadata is immutable'; END IF;
            IF TG_TABLE_NAME = 'research_file_blobs' AND EXISTS (
              SELECT 1 FROM analysis_compute_input_files WHERE blob_id = OLD.id
            ) THEN RAISE EXCEPTION 'Analysis attachment blob metadata is immutable'; END IF;
            IF TG_TABLE_NAME = 'research_compute_job_inputs' THEN
              IF EXISTS (
                SELECT 1 FROM analysis_computations WHERE analysis_run_id = OLD.analysis_run_id
                  AND input_file_manifest::jsonb <> '{}'::jsonb
              ) THEN RAISE EXCEPTION 'Analysis attachment input metadata is immutable'; END IF;
            END IF;
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
    """)
    for table in (
        "airalogy_files",
        "research_file_blobs",
        "research_compute_job_inputs",
    ):
        op.execute(
            f"CREATE TRIGGER protect_analysis_attachment_metadata BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION protect_analysis_attachment_metadata()"
        )
    op.execute("""
        CREATE FUNCTION protect_analysis_attachment_manifest() RETURNS trigger AS $$
        BEGIN
          IF NEW.input_file_manifest::jsonb IS DISTINCT FROM OLD.input_file_manifest::jsonb
          THEN RAISE EXCEPTION 'Analysis attachment manifest is immutable'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
    """)
    op.execute(
        "CREATE TRIGGER protect_analysis_attachment_manifest BEFORE UPDATE ON analysis_computations FOR EACH ROW EXECUTE FUNCTION protect_analysis_attachment_manifest()"
    )


def downgrade():
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE analysis_compute_input_files, analysis_computations, analysis_runs, analysis_previews, analysis_pipeline_revisions, workflow_analysis_methods IN ACCESS EXCLUSIVE MODE"
        )
    )
    if connection.scalar(
        sa.text("""
        SELECT EXISTS (SELECT 1 FROM analysis_compute_input_files)
          OR EXISTS (SELECT 1 FROM analysis_computations WHERE input_file_manifest::jsonb <> '{}'::jsonb)
          OR EXISTS (SELECT 1 FROM analysis_runs WHERE COALESCE(recipe->'input_files', '[]'::json)::jsonb <> '[]'::jsonb)
          OR EXISTS (SELECT 1 FROM analysis_previews WHERE COALESCE(recipe->'input_files', '[]'::json)::jsonb <> '[]'::jsonb)
          OR EXISTS (SELECT 1 FROM analysis_pipeline_revisions WHERE COALESCE(recipe->'input_files', '[]'::json)::jsonb <> '[]'::jsonb)
          OR EXISTS (SELECT 1 FROM workflow_analysis_methods WHERE COALESCE(recipe->'input_files', '[]'::json)::jsonb <> '[]'::jsonb)
    """)
    ):
        raise RuntimeError(
            "Cannot downgrade while attachment-enabled analysis contracts or receipts exist"
        )
    op.execute(
        "DROP TRIGGER protect_analysis_attachment_manifest ON analysis_computations"
    )
    op.execute("DROP FUNCTION protect_analysis_attachment_manifest()")
    for table in (
        "airalogy_files",
        "research_file_blobs",
        "research_compute_job_inputs",
    ):
        op.execute(f"DROP TRIGGER protect_analysis_attachment_metadata ON {table}")
    op.execute("DROP FUNCTION protect_analysis_attachment_metadata()")
    op.drop_table("analysis_compute_input_files")
    op.drop_column("analysis_computations", "input_file_manifest")
