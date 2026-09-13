"""Seal source-authorized Workflow file aliases without publishing private files."""

import sqlalchemy as sa
from alembic import op

revision = "0068_workflow_file_bindings"
down_revision = "0067_workflow_legacy_conversions"
branch_labels = None
depends_on = None
TABLE_NAMES = ("workflow_file_bindings", "workflow_file_export_references")


def upgrade():
    columns = [
        sa.Column(
            "file_id",
            sa.UUID(),
            sa.ForeignKey("airalogy_files.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("binding_id", sa.String(64), nullable=False),
        sa.Column(
            "source_file_id",
            sa.UUID(),
            sa.ForeignKey("airalogy_files.id", ondelete="RESTRICT"),
        ),
        sa.Column("source_kind", sa.String(16), nullable=False),
        sa.Column("source_ref", sa.JSON(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    ]
    for name, table in (
        ("workflow_revision_id", "workflow_revisions"),
        ("task_id", "research_tasks"),
        ("run_id", "research_runs"),
        ("action_id", "research_actions"),
        ("source_action_id", "research_actions"),
        ("blob_id", "research_file_blobs"),
        ("created_by_user_id", "users"),
    ):
        columns.append(
            sa.Column(
                name,
                sa.UUID(),
                sa.ForeignKey(f"{table}.id", ondelete="RESTRICT"),
                nullable=False,
            )
        )
    op.create_table(
        "workflow_file_bindings",
        *columns,
        sa.UniqueConstraint("action_id", "binding_id", name="uq_workflow_file_binding"),
        sa.CheckConstraint(
            "source_kind IN ('record', 'compute')", name="ck_workflow_file_source"
        ),
        sa.CheckConstraint("digest ~ '^[0-9a-f]{64}$'", name="ck_workflow_file_digest"),
    )
    for name in (
        "task_id",
        "run_id",
        "action_id",
        "source_file_id",
        "created_by_user_id",
    ):
        op.create_index(
            f"ix_workflow_file_bindings_{name}", "workflow_file_bindings", [name]
        )
    op.execute(
        "CREATE TRIGGER immutable_workflow_file_bindings BEFORE UPDATE ON workflow_file_bindings FOR EACH ROW EXECUTE FUNCTION reject_workflow_history_update()"
    )
    op.create_table(
        "workflow_file_export_references",
        sa.Column(
            "export_id",
            sa.UUID(),
            sa.ForeignKey("record_exports.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "file_id",
            sa.UUID(),
            sa.ForeignKey("workflow_file_bindings.file_id", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )
    op.execute(
        "CREATE TRIGGER immutable_workflow_file_exports BEFORE UPDATE ON workflow_file_export_references FOR EACH ROW EXECUTE FUNCTION reject_workflow_history_update()"
    )
    op.execute("""
        CREATE FUNCTION protect_workflow_file_snapshot() RETURNS trigger AS $$
        BEGIN
          IF to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) AND EXISTS (
            SELECT 1 FROM workflow_file_bindings WHERE file_id = OLD.id OR source_file_id = OLD.id
          ) THEN RAISE EXCEPTION 'Workflow-bound file metadata is immutable'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER protect_workflow_file_snapshot BEFORE UPDATE ON airalogy_files
        FOR EACH ROW EXECUTE FUNCTION protect_workflow_file_snapshot();
    """)


def downgrade():
    connection = op.get_bind()
    connection.execute(
        sa.text("LOCK TABLE workflow_file_bindings IN ACCESS EXCLUSIVE MODE")
    )
    if connection.scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM workflow_file_bindings)")
    ):
        raise RuntimeError(
            "Cannot downgrade while Workflow file binding receipts exist"
        )
    connection.execute(
        sa.text("LOCK TABLE workflow_revisions IN ACCESS EXCLUSIVE MODE")
    )
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM workflow_revisions WHERE graph->>'schema_version' = '4')"
        )
    ):
        raise RuntimeError(
            "Cannot downgrade while file-capable Workflow revisions exist"
        )
    op.execute("DROP TRIGGER protect_workflow_file_snapshot ON airalogy_files")
    op.execute("DROP FUNCTION protect_workflow_file_snapshot()")
    op.drop_table("workflow_file_export_references")
    op.drop_table("workflow_file_bindings")
