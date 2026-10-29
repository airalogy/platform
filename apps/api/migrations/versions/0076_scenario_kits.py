"""Scope-bound built-in scenario kits and append-only application receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0076_scenario_kits"
down_revision = "0075_legacy_file_metadata"
branch_labels = None
depends_on = None
TABLE_NAMES = (
    "lab_scenario_kits",
    "scenario_kit_applications",
    "scenario_shared_components",
    "scenario_kit_events",
)


def _id():
    return sa.Column(
        "id", sa.UUID(), primary_key=True, server_default=sa.func.uuid_generate_v7()
    )


def _fk(name, table, nullable=False):
    return sa.Column(
        name,
        sa.UUID(),
        sa.ForeignKey(
            f"{table}.id",
            ondelete="CASCADE"
            if table in {"labs", "projects", "lab_scenario_kits"}
            else "RESTRICT",
        ),
        nullable=nullable,
    )


def _time(name):
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def upgrade():
    op.create_table(
        "lab_scenario_kits",
        _id(),
        _fk("lab_id", "labs"),
        sa.Column("kit_id", sa.String(128), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        _time("updated_at"),
        sa.UniqueConstraint("lab_id", "kit_id", name="uq_lab_scenario_kit"),
        sa.CheckConstraint("revision > 0", name="ck_lab_scenario_kit_revision"),
    )
    op.create_index("ix_lab_scenario_kits_lab_id", "lab_scenario_kits", ["lab_id"])
    op.create_table(
        "scenario_kit_applications",
        _id(),
        _fk("project_id", "projects"),
        _fk("installation_id", "lab_scenario_kits"),
        sa.Column("kit_id", sa.String(128), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("assets", sa.JSON(), nullable=False),
        _fk("created_by_user_id", "users"),
        _time("updated_at"),
        sa.UniqueConstraint("project_id", "kit_id", name="uq_project_scenario_kit"),
        sa.CheckConstraint("revision > 0", name="ck_project_scenario_kit_revision"),
    )
    op.create_index(
        "ix_scenario_kit_applications_project_id",
        "scenario_kit_applications",
        ["project_id"],
    )
    op.create_table(
        "scenario_shared_components",
        _id(),
        _fk("lab_id", "labs"),
        sa.Column("component_id", sa.String(128), nullable=False),
        _fk("resource_type_id", "resource_types"),
        sa.Column("schema_digest", sa.String(64), nullable=False),
        sa.UniqueConstraint(
            "lab_id", "component_id", name="uq_scenario_shared_component"
        ),
    )
    op.create_index(
        "ix_scenario_shared_components_lab_id", "scenario_shared_components", ["lab_id"]
    )
    op.create_table(
        "scenario_kit_events",
        _id(),
        _fk("lab_id", "labs"),
        _fk("project_id", "projects", True),
        _fk("actor_user_id", "users"),
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        _time("created_at"),
        sa.UniqueConstraint(
            "actor_user_id", "request_id", name="uq_scenario_kit_request"
        ),
    )
    op.create_index("ix_scenario_kit_events_lab_id", "scenario_kit_events", ["lab_id"])
    op.execute("""CREATE FUNCTION reject_scenario_event_mutation() RETURNS trigger AS $$
        BEGIN
          -- Only parent-scope deletion may cascade through history. Ordinary
          -- updates/deletes, including kit deactivation, cannot erase receipts.
          IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN RETURN OLD; END IF;
          RAISE EXCEPTION 'Scenario receipts are append-only';
        END;
        $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER scenario_event_immutable BEFORE UPDATE OR DELETE ON scenario_kit_events
        FOR EACH ROW EXECUTE FUNCTION reject_scenario_event_mutation()""")


def downgrade():
    if (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM scenario_kit_events)"))
        .scalar()
    ):
        raise RuntimeError(
            "Scenario provenance exists; restore a verified backup instead of deleting history"
        )
    for table in (
        "scenario_kit_events",
        "scenario_shared_components",
        "scenario_kit_applications",
        "lab_scenario_kits",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION reject_scenario_event_mutation()")
