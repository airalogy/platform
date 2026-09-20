"""Seal exact Workflow DataAsset inputs without inventing source Actions."""

import sqlalchemy as sa
from alembic import op

revision = "0071_workflow_asset_inputs"
down_revision = "0070_project_analysis"
branch_labels = None
depends_on = None
TABLE_NAMES = ("workflow_run_asset_inputs",)
SOURCE_CHECK = (
    "(source_kind IN ('record', 'compute') AND source_action_id IS NOT NULL AND asset_input_id IS NULL) OR "
    "(source_kind = 'data_asset' AND source_action_id IS NULL AND asset_input_id IS NOT NULL AND source_file_id IS NULL)"
)
SOURCE_TABLES = (
    "data_asset_versions",
    "research_files",
    "research_file_blobs",
)


def upgrade():
    columns = [
        sa.Column(
            "id", sa.UUID(), primary_key=True, server_default=sa.func.uuid_generate_v7()
        ),
        sa.Column("input_id", sa.String(64), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
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
        ("data_asset_version_id", "data_asset_versions"),
        ("research_file_id", "research_files"),
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
        "workflow_run_asset_inputs",
        *columns,
        sa.UniqueConstraint("run_id", "input_id", name="uq_workflow_run_asset_input"),
        sa.CheckConstraint(
            "input_id ~ '^[a-z][a-z0-9_-]{0,63}$'", name="ck_workflow_asset_input_id"
        ),
        sa.CheckConstraint(
            "digest ~ '^[0-9a-f]{64}$'", name="ck_workflow_asset_input_digest"
        ),
        sa.CheckConstraint(
            "source_digest ~ '^[0-9a-f]{64}$'", name="ck_workflow_asset_source_digest"
        ),
    )
    for name in (
        "task_id",
        "run_id",
        "data_asset_version_id",
        "research_file_id",
        "blob_id",
        "created_by_user_id",
    ):
        op.create_index(
            f"ix_workflow_run_asset_inputs_{name}", "workflow_run_asset_inputs", [name]
        )
    op.execute(
        "CREATE TRIGGER immutable_workflow_run_asset_inputs BEFORE UPDATE ON workflow_run_asset_inputs FOR EACH ROW EXECUTE FUNCTION reject_workflow_history_update()"
    )
    op.execute("""
        CREATE FUNCTION protect_workflow_asset_source_metadata() RETURNS trigger AS $$
        BEGIN
          IF TG_TABLE_NAME = 'data_asset_versions' THEN
            IF to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) AND EXISTS (
              SELECT 1 FROM workflow_run_asset_inputs WHERE data_asset_version_id = OLD.id
            ) THEN RAISE EXCEPTION 'Workflow DataAsset version metadata is immutable'; END IF;
          ELSIF TG_TABLE_NAME = 'research_files' THEN
            IF (to_jsonb(NEW) - ARRAY['visibility', 'archived_at'])
                IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['visibility', 'archived_at'])
                AND EXISTS (
                  SELECT 1 FROM workflow_run_asset_inputs WHERE research_file_id = OLD.id
                ) THEN RAISE EXCEPTION 'Workflow DataAsset file metadata is immutable'; END IF;
          ELSIF TG_TABLE_NAME = 'research_file_blobs' THEN
            IF (to_jsonb(NEW) - 'extracted_text')
                IS DISTINCT FROM (to_jsonb(OLD) - 'extracted_text')
                AND EXISTS (
                  SELECT 1 FROM workflow_run_asset_inputs WHERE blob_id = OLD.id
                ) THEN RAISE EXCEPTION 'Workflow DataAsset blob metadata is immutable'; END IF;
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
    """)
    for table in SOURCE_TABLES:
        op.execute(
            f"CREATE TRIGGER protect_workflow_asset_source_metadata BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION protect_workflow_asset_source_metadata()"
        )
    op.add_column(
        "workflow_file_bindings", sa.Column("asset_input_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        "fk_workflow_file_asset_input",
        "workflow_file_bindings",
        "workflow_run_asset_inputs",
        ["asset_input_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_workflow_file_bindings_asset_input_id",
        "workflow_file_bindings",
        ["asset_input_id"],
    )
    op.alter_column(
        "workflow_file_bindings",
        "source_action_id",
        existing_type=sa.UUID(),
        nullable=True,
    )
    op.drop_constraint(
        "ck_workflow_file_source", "workflow_file_bindings", type_="check"
    )
    op.create_check_constraint(
        "ck_workflow_file_source", "workflow_file_bindings", SOURCE_CHECK
    )


def downgrade():
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE workflow_run_asset_inputs, workflow_file_bindings, workflow_revisions IN ACCESS EXCLUSIVE MODE"
        )
    )
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM workflow_run_asset_inputs) OR EXISTS (SELECT 1 FROM workflow_file_bindings WHERE source_kind = 'data_asset') OR EXISTS (SELECT 1 FROM workflow_revisions WHERE graph->>'schema_version' = '5')"
        )
    ):
        raise RuntimeError(
            "Cannot downgrade while Workflow DataAsset contracts or receipts exist"
        )
    op.drop_constraint(
        "ck_workflow_file_source", "workflow_file_bindings", type_="check"
    )
    op.create_check_constraint(
        "ck_workflow_file_source",
        "workflow_file_bindings",
        "source_kind IN ('record', 'compute')",
    )
    op.alter_column(
        "workflow_file_bindings",
        "source_action_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
    op.drop_index(
        "ix_workflow_file_bindings_asset_input_id", table_name="workflow_file_bindings"
    )
    op.drop_constraint(
        "fk_workflow_file_asset_input", "workflow_file_bindings", type_="foreignkey"
    )
    op.drop_column("workflow_file_bindings", "asset_input_id")
    for table in SOURCE_TABLES:
        op.execute(f"DROP TRIGGER protect_workflow_asset_source_metadata ON {table}")
    op.execute("DROP FUNCTION protect_workflow_asset_source_metadata()")
    op.drop_table("workflow_run_asset_inputs")
