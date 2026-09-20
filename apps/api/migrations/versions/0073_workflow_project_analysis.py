"""Explicit multi-source Workflow methods, preserving older publication seals."""

import sqlalchemy as sa
from alembic import op

revision = "0073_workflow_project_analysis"
down_revision = "0072_analysis_publications"
branch_labels = None
depends_on = None
TABLE_NAMES = ("workflow_analysis_method_project_versions",)
SCOPE_CHECK = (
    "(engine_version = 'airalogy.project-analysis.v1' "
    "AND protocol_id IS NULL AND protocol_version_id IS NULL "
    "AND project_contract::jsonb <> '{}'::jsonb "
    "AND input_fields::jsonb = '[]'::jsonb "
    "AND compute_contract::jsonb = '{}'::jsonb) OR "
    "(engine_version <> 'airalogy.project-analysis.v1' "
    "AND protocol_id IS NOT NULL AND protocol_version_id IS NOT NULL "
    "AND project_contract::jsonb = '{}'::jsonb)"
)


def upgrade():
    op.add_column(
        "workflow_analysis_methods",
        sa.Column("project_contract", sa.JSON(), nullable=False, server_default="{}"),
    )
    for name in ("protocol_id", "protocol_version_id"):
        op.alter_column(
            "workflow_analysis_methods", name, existing_type=sa.UUID(), nullable=True
        )
    op.create_check_constraint(
        "ck_workflow_analysis_method_project_scope",
        "workflow_analysis_methods",
        SCOPE_CHECK,
    )
    op.create_table(
        TABLE_NAMES[0],
        sa.Column(
            "method_id",
            sa.UUID(),
            sa.ForeignKey("workflow_analysis_methods.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("slot_id", sa.String(24), primary_key=True),
        sa.Column(
            "protocol_version_id",
            sa.UUID(),
            sa.ForeignKey("protocol_versions.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "protocol_id",
            sa.UUID(),
            sa.ForeignKey("protocols.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("schema_digest", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "slot_id ~ '^[a-z][a-z0-9_]{0,23}$'", name="ck_workflow_project_method_slot"
        ),
        sa.CheckConstraint(
            "schema_digest ~ '^[0-9a-f]{64}$'", name="ck_workflow_project_method_schema"
        ),
    )
    op.create_index(
        "ix_workflow_analysis_method_project_versions_protocol_id",
        TABLE_NAMES[0],
        ["protocol_id"],
    )
    op.execute(
        "CREATE TRIGGER immutable_workflow_project_method_versions "
        "BEFORE UPDATE ON workflow_analysis_method_project_versions "
        "FOR EACH ROW EXECUTE FUNCTION reject_workflow_history_update()"
    )
    op.execute("""
        CREATE FUNCTION check_workflow_project_method_version() RETURNS trigger AS $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM workflow_analysis_methods m
            JOIN protocols p ON p.id = NEW.protocol_id AND p.project_id = m.project_id
            JOIN protocol_versions v ON v.id = NEW.protocol_version_id AND v.protocol_id = p.id,
            jsonb_array_elements(m.project_contract::jsonb -> 'slots') AS slot_entry(slot_json),
            jsonb_array_elements(slot_entry.slot_json -> 'versions') AS version_entry(version_json)
            WHERE m.id = NEW.method_id AND m.engine_version = 'airalogy.project-analysis.v1'
              AND slot_entry.slot_json ->> 'slot_id' = NEW.slot_id
              AND slot_entry.slot_json ->> 'protocol_id' = NEW.protocol_id::text
              AND version_entry.version_json ->> 'id' = NEW.protocol_version_id::text
              AND version_entry.version_json ->> 'schema_digest' = NEW.schema_digest
          ) THEN RAISE EXCEPTION 'Project method version must match its exact scoped contract'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql
    """)
    op.execute(
        "CREATE TRIGGER check_workflow_project_method_version "
        "BEFORE INSERT ON workflow_analysis_method_project_versions "
        "FOR EACH ROW EXECUTE FUNCTION check_workflow_project_method_version()"
    )


def downgrade():
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "LOCK TABLE workflow_analysis_methods, workflow_analysis_method_project_versions, "
            "workflow_revisions IN ACCESS EXCLUSIVE MODE"
        )
    )
    if connection.scalar(
        sa.text("""
        SELECT EXISTS (SELECT 1 FROM workflow_analysis_methods
          WHERE engine_version = 'airalogy.project-analysis.v1'
            OR project_contract::jsonb <> '{}'::jsonb)
          OR EXISTS (SELECT 1 FROM workflow_analysis_method_project_versions)
          OR EXISTS (SELECT 1 FROM workflow_revisions WHERE graph ->> 'schema_version' = '6')
    """)
    ):
        raise RuntimeError(
            "Cannot downgrade while Project methods or version 6 Workflows exist"
        )
    op.drop_table(TABLE_NAMES[0])
    op.execute("DROP FUNCTION check_workflow_project_method_version()")
    op.drop_constraint(
        "ck_workflow_analysis_method_project_scope", "workflow_analysis_methods"
    )
    for name in ("protocol_id", "protocol_version_id"):
        op.alter_column(
            "workflow_analysis_methods", name, existing_type=sa.UUID(), nullable=False
        )
    op.drop_column("workflow_analysis_methods", "project_contract")
