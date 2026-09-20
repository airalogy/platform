"""Publish immutable selected analysis Evidence without opening private reports."""

import sqlalchemy as sa
from alembic import op

revision = "0072_analysis_publications"
down_revision = "0071_workflow_asset_inputs"
branch_labels = None
depends_on = None
TABLE_NAME = "analysis_evidence_publications"
TABLE_NAMES = (TABLE_NAME,)


def upgrade():
    columns = [
        sa.Column(
            "id", sa.UUID(), primary_key=True, server_default=sa.func.uuid_generate_v7()
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("selection", sa.JSON(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    ]
    for name, table, nullable in (
        ("project_id", "projects", False),
        ("task_id", "research_tasks", False),
        ("analysis_run_id", "analysis_runs", False),
        ("interpretation_revision_id", "analysis_interpretation_revisions", True),
        ("evidence_id", "research_evidence", False),
        ("created_by_user_id", "users", False),
    ):
        columns.append(
            sa.Column(
                name,
                sa.UUID(),
                sa.ForeignKey(f"{table}.id", ondelete="RESTRICT"),
                nullable=nullable,
            )
        )
    for name in (
        "source_digest",
        "recipe_digest",
        "result_digest",
        "interpretation_digest",
        "digest",
        "request_digest",
    ):
        columns.append(
            sa.Column(name, sa.String(64), nullable=name == "interpretation_digest")
        )
    op.create_table(
        TABLE_NAME,
        *columns,
        sa.UniqueConstraint(
            "created_by_user_id",
            "idempotency_key",
            name="uq_analysis_evidence_publication_request",
        ),
        sa.UniqueConstraint(
            "evidence_id", name="uq_analysis_evidence_publication_evidence"
        ),
        *[
            sa.CheckConstraint(
                f"{column} ~ '^[0-9a-f]{{64}}$'",
                name=f"ck_analysis_publication_{column}",
            )
            for column in (
                "digest",
                "source_digest",
                "recipe_digest",
                "result_digest",
                "request_digest",
            )
        ],
        sa.CheckConstraint(
            "(interpretation_revision_id IS NULL) = (interpretation_digest IS NULL)",
            name="ck_analysis_publication_interpretation_pair",
        ),
        sa.CheckConstraint(
            "interpretation_digest IS NULL OR interpretation_digest ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_publication_interpretation_digest",
        ),
    )
    for column in ("project_id", "task_id", "analysis_run_id"):
        op.create_index(f"ix_{TABLE_NAME}_{column}", TABLE_NAME, [column])
    op.execute(
        f"CREATE TRIGGER immutable_{TABLE_NAME} BEFORE UPDATE ON {TABLE_NAME} FOR EACH ROW EXECUTE FUNCTION reject_workflow_history_update()"
    )
    op.execute("""
        CREATE FUNCTION protect_analysis_publication_sources() RETURNS trigger AS $$
        BEGIN
          IF TG_TABLE_NAME = 'analysis_runs' THEN
            IF (to_jsonb(NEW) - 'job_id') IS DISTINCT FROM (to_jsonb(OLD) - 'job_id') AND EXISTS (
              SELECT 1 FROM analysis_evidence_publications WHERE analysis_run_id = OLD.id
            ) THEN RAISE EXCEPTION 'Published analysis execution and result are immutable'; END IF;
          ELSIF TG_TABLE_NAME = 'research_evidence' THEN
            IF (to_jsonb(NEW) - ARRAY['quality_state','validation_report','reviewed_by_user_id','reviewed_at'])
              IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['quality_state','validation_report','reviewed_by_user_id','reviewed_at']) AND EXISTS (
              SELECT 1 FROM analysis_evidence_publications WHERE evidence_id = OLD.id
            ) THEN RAISE EXCEPTION 'Published analysis Evidence source identity is immutable'; END IF;
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
    """)
    for table in ("analysis_runs", "research_evidence"):
        op.execute(
            f"CREATE TRIGGER protect_analysis_publication_sources BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION protect_analysis_publication_sources()"
        )


def downgrade():
    if (
        op.get_bind()
        .execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {TABLE_NAME})"))
        .scalar()
    ):
        raise RuntimeError(
            "Cannot downgrade while immutable analysis Evidence publications exist"
        )
    for table in ("analysis_runs", "research_evidence"):
        op.execute(f"DROP TRIGGER protect_analysis_publication_sources ON {table}")
    op.execute("DROP FUNCTION protect_analysis_publication_sources()")
    op.drop_table(TABLE_NAME)
