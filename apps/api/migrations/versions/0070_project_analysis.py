"""Explicit multi-Protocol scope and independent interpretation history.

Historical Protocol recipes/digests are unchanged. Project analyses use the
existing job lifecycle and retain relational protection for every source slot.
"""

import sqlalchemy as sa
from alembic import op

revision = "0070_project_analysis"
down_revision = "0069_analysis_input_files"
branch_labels = None
depends_on = None
TABLE_NAMES = ("analysis_project_inputs", "analysis_interpretation_revisions")
SCOPES = (
    ("analysis_pipelines", "ck_analysis_pipeline_source_scope"),
    ("analysis_runs", "ck_analysis_run_source_scope"),
    ("analysis_previews", "ck_analysis_preview_source_scope"),
)
SCOPE_CHECK = (
    "(source_scope = 'protocol' AND protocol_id IS NOT NULL) OR "
    "(source_scope = 'project' AND protocol_id IS NULL)"
)


def upgrade():
    for table, constraint in SCOPES:
        op.add_column(
            table,
            sa.Column(
                "source_scope", sa.String(16), nullable=False, server_default="protocol"
            ),
        )
        op.alter_column(table, "protocol_id", existing_type=sa.UUID(), nullable=True)
        op.create_check_constraint(constraint, table, SCOPE_CHECK)
    op.create_table(
        "analysis_project_inputs",
        sa.Column(
            "run_id",
            sa.UUID(),
            sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("slot_id", sa.String(24), primary_key=True),
        sa.Column(
            "protocol_id",
            sa.UUID(),
            sa.ForeignKey("protocols.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "source_digest ~ '^[0-9a-f]{64}$'", name="ck_analysis_project_input_digest"
        ),
        sa.CheckConstraint(
            "slot_id ~ '^[a-z][a-z0-9_]{0,23}$'", name="ck_analysis_project_input_slot"
        ),
        sa.UniqueConstraint(
            "run_id", "protocol_id", name="uq_analysis_project_input_protocol"
        ),
    )
    op.create_index(
        "ix_analysis_project_inputs_protocol_id",
        "analysis_project_inputs",
        ["protocol_id"],
    )
    op.create_table(
        "analysis_interpretation_revisions",
        sa.Column(
            "id", sa.UUID(), primary_key=True, server_default=sa.func.uuid_generate_v7()
        ),
        sa.Column(
            "analysis_run_id",
            sa.UUID(),
            sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("result_digest", sa.String(64), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("resolved_evidence", sa.JSON(), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "analysis_run_id", "revision", name="uq_analysis_interpretation_revision"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_analysis_interpretation_revision"),
        sa.CheckConstraint(
            "result_digest ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_interpretation_result_digest",
        ),
        sa.CheckConstraint(
            "content_digest ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_interpretation_content_digest",
        ),
    )
    op.create_index(
        "ix_analysis_interpretation_revisions_analysis_run_id",
        "analysis_interpretation_revisions",
        ["analysis_run_id"],
    )
    for table in TABLE_NAMES:
        op.execute(
            f"CREATE TRIGGER immutable_{table} BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_workflow_history_update()"
        )
    op.execute("""
        CREATE FUNCTION protect_project_analysis_history() RETURNS trigger AS $$
        BEGIN
          IF TG_TABLE_NAME = 'analysis_pipeline_revisions' THEN
            IF EXISTS (SELECT 1 FROM analysis_pipelines WHERE id = OLD.pipeline_id AND source_scope = 'project')
              OR EXISTS (SELECT 1 FROM analysis_pipelines WHERE id = NEW.pipeline_id AND source_scope = 'project') THEN
              RAISE EXCEPTION 'Project analysis method revisions are immutable';
            END IF;
            RETURN NEW;
          END IF;
          IF NEW.source_scope IS DISTINCT FROM OLD.source_scope THEN
            RAISE EXCEPTION 'Analysis source scope is immutable';
          END IF;
          IF OLD.source_scope <> 'project' THEN RETURN NEW; END IF;
          IF TG_TABLE_NAME = 'analysis_previews' THEN
            IF to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN
              RAISE EXCEPTION 'Project analysis previews are immutable';
            END IF;
          ELSIF TG_TABLE_NAME = 'analysis_pipelines' THEN
            IF (to_jsonb(NEW) - ARRAY['title','current_revision','updated_at'])
              IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['title','current_revision','updated_at']) THEN
              RAISE EXCEPTION 'Project analysis method identity is immutable';
            END IF;
            IF NEW.current_revision < OLD.current_revision THEN
              RAISE EXCEPTION 'Project analysis method history cannot rewind';
            END IF;
          ELSIF TG_TABLE_NAME = 'analysis_runs' THEN
            IF (to_jsonb(NEW) - ARRAY['status','result','result_digest','error','job_id','started_at','finished_at'])
              IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['status','result','result_digest','error','job_id','started_at','finished_at']) THEN
              RAISE EXCEPTION 'Project analysis execution contract is immutable';
            END IF;
            IF OLD.status IN ('succeeded','failed','cancelled') AND
              (to_jsonb(NEW) - 'job_id') IS DISTINCT FROM (to_jsonb(OLD) - 'job_id') THEN
              RAISE EXCEPTION 'Finished Project analysis history is immutable';
            END IF;
            IF NEW.result_digest IS NOT NULL AND NEW.status <> 'succeeded' THEN
              RAISE EXCEPTION 'Project analysis results require successful execution';
            END IF;
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
    """)
    for table in (*[item[0] for item in SCOPES], "analysis_pipeline_revisions"):
        op.execute(
            f"CREATE TRIGGER protect_project_analysis_history BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION protect_project_analysis_history()"
        )


def downgrade():
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE analysis_pipelines, analysis_runs, analysis_previews, "
            "analysis_pipeline_revisions, analysis_project_inputs, "
            "analysis_interpretation_revisions IN ACCESS EXCLUSIVE MODE"
        )
    )
    if connection.scalar(
        sa.text("""
        SELECT EXISTS (SELECT 1 FROM analysis_runs WHERE source_scope = 'project')
          OR EXISTS (SELECT 1 FROM analysis_previews WHERE source_scope = 'project')
          OR EXISTS (SELECT 1 FROM analysis_pipelines WHERE source_scope = 'project')
          OR EXISTS (SELECT 1 FROM analysis_project_inputs)
          OR EXISTS (SELECT 1 FROM analysis_interpretation_revisions)
    """)
    ):
        raise RuntimeError(
            "Cannot downgrade while Project analysis contracts or interpretation history exist"
        )
    for table in (*[item[0] for item in SCOPES], "analysis_pipeline_revisions"):
        op.execute(f"DROP TRIGGER protect_project_analysis_history ON {table}")
    op.execute("DROP FUNCTION protect_project_analysis_history()")
    for table in reversed(TABLE_NAMES):
        op.drop_table(table)
    for table, constraint in reversed(SCOPES):
        op.drop_constraint(constraint, table, type_="check")
        op.alter_column(table, "protocol_id", existing_type=sa.UUID(), nullable=False)
        op.drop_column(table, "source_scope")
