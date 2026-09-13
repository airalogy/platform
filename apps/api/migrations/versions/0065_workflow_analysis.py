"""Explicit Project method publication and governed analysis occurrences."""

import sqlalchemy as sa
from alembic import op

revision = "0065_workflow_analysis"
down_revision = "0064_workflow_node_resolutions"
branch_labels = None
depends_on = None
TABLE_NAMES = ("workflow_analysis_methods", "research_analysis_actions")


def upgrade():
    op.create_table(
        "workflow_analysis_methods",
        sa.Column(
            "id", sa.UUID(), primary_key=True, server_default=sa.func.uuid_generate_v7()
        ),
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
        sa.Column(
            "protocol_version_id",
            sa.UUID(),
            sa.ForeignKey("protocol_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_pipeline_revision_id",
            sa.UUID(),
            sa.ForeignKey("analysis_pipeline_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_method_digest", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("engine_version", sa.String(64), nullable=False),
        sa.Column("recipe", sa.JSON(), nullable=False),
        sa.Column("input_fields", sa.JSON(), nullable=False),
        sa.Column("source_schema_digest", sa.String(64), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.UUID(), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "created_by_user_id",
            "idempotency_key",
            name="uq_workflow_analysis_method_request",
        ),
        sa.CheckConstraint(
            "digest ~ '^[0-9a-f]{64}$'", name="ck_workflow_analysis_method_digest"
        ),
        sa.CheckConstraint(
            "source_schema_digest ~ '^[0-9a-f]{64}$'",
            name="ck_workflow_analysis_method_schema",
        ),
    )
    op.create_index(
        "ix_workflow_analysis_methods_project_id",
        "workflow_analysis_methods",
        ["project_id"],
    )
    op.execute(
        "CREATE TRIGGER immutable_workflow_analysis_methods BEFORE UPDATE ON workflow_analysis_methods FOR EACH ROW EXECUTE FUNCTION reject_workflow_history_update()"
    )
    op.create_table(
        "research_analysis_actions",
        sa.Column(
            "action_id",
            sa.UUID(),
            sa.ForeignKey("research_actions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "method_publication_id",
            sa.UUID(),
            sa.ForeignKey("workflow_analysis_methods.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "analysis_run_id",
            sa.UUID(),
            sa.ForeignKey("analysis_runs.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "analysis_preview_id",
            sa.UUID(),
            sa.ForeignKey("analysis_previews.id", ondelete="RESTRICT"),
        ),
        sa.Column("input_snapshot", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("source_digest", sa.String(64)),
        sa.Column("resolution_digest", sa.String(64)),
        sa.Column("preview_digest", sa.String(64)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("analysis_run_id", name="uq_research_analysis_action_run"),
        sa.UniqueConstraint(
            "analysis_preview_id", name="uq_research_analysis_action_preview"
        ),
        sa.CheckConstraint(
            "source_digest IS NULL OR source_digest ~ '^[0-9a-f]{64}$'",
            name="ck_research_analysis_source_digest",
        ),
        sa.CheckConstraint(
            "resolution_digest IS NULL OR resolution_digest ~ '^[0-9a-f]{64}$'",
            name="ck_research_analysis_resolution_digest",
        ),
        sa.CheckConstraint(
            "preview_digest IS NULL OR preview_digest ~ '^[0-9a-f]{64}$'",
            name="ck_research_analysis_preview_digest",
        ),
    )
    op.execute("""
        CREATE FUNCTION protect_workflow_analysis_inputs() RETURNS trigger AS $$
        BEGIN
            IF OLD.action_id IS DISTINCT FROM NEW.action_id
                OR OLD.method_publication_id IS DISTINCT FROM NEW.method_publication_id
                OR OLD.created_at IS DISTINCT FROM NEW.created_at
                OR (OLD.source_digest IS NOT NULL AND (
                    OLD.input_snapshot::jsonb IS DISTINCT FROM NEW.input_snapshot::jsonb
                    OR OLD.source_digest IS DISTINCT FROM NEW.source_digest
                    OR OLD.resolution_digest IS DISTINCT FROM NEW.resolution_digest
                    OR OLD.preview_digest IS DISTINCT FROM NEW.preview_digest))
                OR (OLD.analysis_run_id IS NOT NULL AND OLD.analysis_run_id IS DISTINCT FROM NEW.analysis_run_id)
                OR (OLD.analysis_preview_id IS NOT NULL AND OLD.analysis_preview_id IS DISTINCT FROM NEW.analysis_preview_id)
            THEN RAISE EXCEPTION 'Workflow analysis inputs and execution bindings are immutable'; END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql
    """)
    op.execute(
        "CREATE TRIGGER immutable_research_analysis_inputs BEFORE UPDATE ON research_analysis_actions FOR EACH ROW EXECUTE FUNCTION protect_workflow_analysis_inputs()"
    )


def downgrade():
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE workflow_analysis_methods, research_analysis_actions, workflow_revisions IN ACCESS EXCLUSIVE MODE"
        )
    )
    # The graph predicate must be protected by the same transaction's lock:
    # publishing a v2 Protocol-only graph does not insert into either new table.
    has_new_graphs = connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM workflow_revisions WHERE graph ->> 'schema_version' = '2')"
        )
    )
    if has_new_graphs or any(
        connection.scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {name})"))
        for name in TABLE_NAMES
    ):
        raise RuntimeError(
            "Cannot downgrade while published methods, analysis occurrences, or version 2 Workflow graphs exist"
        )
    op.drop_table("research_analysis_actions")
    op.execute("DROP FUNCTION protect_workflow_analysis_inputs()")
    op.drop_table("workflow_analysis_methods")
