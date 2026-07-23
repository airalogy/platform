"""Add Lab resources, inventory, equipment, and Protocol version governance.

Revision ID: 0007_resource_governance
Revises: 0006_model_usage_events
Create Date: 2026-07-23 00:00:00.000000
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

from migrations.model_registry import import_models

revision: str = "0007_resource_governance"
down_revision: str | None = "0006_model_usage_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


RESOURCE_TABLE_NAMES = (
    "resource_types",
    "resource_type_revisions",
    "resources",
    "resource_revisions",
    "resource_field_indexes",
    "resource_locations",
    "resource_lots",
    "resource_containers",
    "inventory_balances",
    "inventory_events",
    "inventory_reservations",
    "equipment_bookings",
    "equipment_usages",
    "equipment_service_events",
    "resource_lineage",
    "record_resource_links",
    "resource_notifications",
    "resource_labels",
    "schema_migration_runs",
    "record_projections",
    "persistent_jobs",
)


def _resource_tables(metadata):
    return [metadata.tables[name] for name in RESOURCE_TABLE_NAMES]


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    import_models()
    from app.models.base import Base

    Base.metadata.create_all(bind=bind, tables=_resource_tables(Base.metadata))

    protocol_columns = {
        item["name"] for item in sa.inspect(bind).get_columns("protocols")
    }
    if "kind" not in protocol_columns:
        op.add_column(
            "protocols",
            sa.Column(
                "kind",
                sa.String(length=32),
                server_default="experiment",
                nullable=False,
            ),
        )
    protocol_indexes = {
        item["name"] for item in sa.inspect(bind).get_indexes("protocols")
    }
    if "ix_protocols_kind" not in protocol_indexes:
        op.create_index("ix_protocols_kind", "protocols", ["kind"])
    op.create_check_constraint(
        "ck_protocols_kind",
        "protocols",
        "kind IN ('experiment', 'resource_definition')",
    )

    protocol_version_columns = {
        item["name"]
        for item in sa.inspect(bind).get_columns("protocol_versions")
    }
    if "compatibility_report" not in protocol_version_columns:
        op.add_column(
            "protocol_versions",
            sa.Column("compatibility_report", sa.JSON(), nullable=True),
        )
    if "migration_manifest" not in protocol_version_columns:
        op.add_column(
            "protocol_versions",
            sa.Column("migration_manifest", sa.JSON(), nullable=True),
        )

    record_columns = {
        item["name"] for item in sa.inspect(bind).get_columns("records")
    }
    if "revision_kind" not in record_columns:
        op.add_column(
            "records",
            sa.Column(
                "revision_kind",
                sa.String(length=32),
                server_default="initial",
                nullable=False,
            ),
        )
    if "revision_reason" not in record_columns:
        op.add_column(
            "records",
            sa.Column(
                "revision_reason",
                sa.Text(),
                server_default="",
                nullable=False,
            ),
        )
    if "source_protocol_version" not in record_columns:
        op.add_column(
            "records",
            sa.Column(
                "source_protocol_version",
                sa.String(length=64),
                nullable=True,
            ),
        )
    if "migration_run_id" not in record_columns:
        op.add_column(
            "records",
            sa.Column("migration_run_id", sa.UUID(), nullable=True),
        )
    op.create_foreign_key(
        "fk_records_migration_run",
        "records",
        "schema_migration_runs",
        ["migration_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    record_indexes = {
        item["name"] for item in sa.inspect(bind).get_indexes("records")
    }
    if "ix_records_migration_run_id" not in record_indexes:
        op.create_index(
            "ix_records_migration_run_id", "records", ["migration_run_id"]
        )
    op.execute(
        """
        UPDATE records
        SET revision_kind = CASE
            WHEN version = 1 THEN 'initial'
            ELSE 'legacy_revision'
        END
        """
    )
    op.create_check_constraint(
        "ck_records_revision_kind",
        "records",
        "revision_kind IN "
        "('initial', 'correction', 'schema_migration', 'import', 'legacy_revision')",
    )

    for column_name, target in (
        ("resource_type_id", "resource_types.id"),
        ("resource_id", "resources.id"),
        ("location_id", "resource_locations.id"),
    ):
        op.add_column(
            "access_grants",
            sa.Column(column_name, sa.UUID(), nullable=True),
        )
        op.create_index(
            f"ix_access_grants_{column_name}",
            "access_grants",
            [column_name],
        )
        target_table, target_column = target.split(".")
        op.create_foreign_key(
            f"fk_access_grants_{column_name}",
            "access_grants",
            target_table,
            [column_name],
            [target_column],
            ondelete="CASCADE",
        )

    op.drop_constraint(
        "ck_access_grants_scope", "access_grants", type_="check"
    )
    op.create_check_constraint(
        "ck_access_grants_scope",
        "access_grants",
        """
        (scope_type = 'lab' AND project_id IS NULL AND protocol_id IS NULL
            AND resource_type_id IS NULL AND resource_id IS NULL AND location_id IS NULL)
        OR (scope_type = 'project' AND project_id IS NOT NULL AND protocol_id IS NULL
            AND resource_type_id IS NULL AND resource_id IS NULL AND location_id IS NULL)
        OR (scope_type = 'protocol' AND protocol_id IS NOT NULL
            AND resource_type_id IS NULL AND resource_id IS NULL AND location_id IS NULL)
        OR (scope_type = 'resource_type' AND resource_type_id IS NOT NULL
            AND project_id IS NULL AND protocol_id IS NULL
            AND resource_id IS NULL AND location_id IS NULL)
        OR (scope_type = 'resource' AND resource_id IS NOT NULL
            AND project_id IS NULL AND protocol_id IS NULL
            AND resource_type_id IS NULL AND location_id IS NULL)
        OR (scope_type = 'location' AND location_id IS NOT NULL
            AND project_id IS NULL AND protocol_id IS NULL
            AND resource_type_id IS NULL AND resource_id IS NULL)
        """,
    )

    _install_resource_constraints()
    _install_append_only_guards()


def _install_resource_constraints() -> None:
    op.create_check_constraint(
        "ck_inventory_balances_non_negative",
        "inventory_balances",
        "on_hand >= 0 AND reserved >= 0 AND reserved <= on_hand",
    )
    op.create_check_constraint(
        "ck_inventory_events_positive_quantity",
        "inventory_events",
        "quantity > 0 OR (kind = 'count' AND quantity = 0)",
    )
    op.create_check_constraint(
        "ck_inventory_reservations_positive_quantity",
        "inventory_reservations",
        "quantity > 0",
    )
    op.create_check_constraint(
        "ck_equipment_bookings_time",
        "equipment_bookings",
        "ends_at > starts_at",
    )
    op.create_check_constraint(
        "ck_equipment_service_events_time",
        "equipment_service_events",
        "ends_at IS NULL OR ends_at > starts_at",
    )
    op.create_check_constraint(
        "ck_resource_visibility",
        "resources",
        "visibility IN ('lab', 'restricted')",
    )
    op.create_check_constraint(
        "ck_resource_locations_visibility",
        "resource_locations",
        "visibility IN ('lab', 'restricted')",
    )
    op.execute(
        """
        ALTER TABLE equipment_bookings
        ADD CONSTRAINT ex_equipment_bookings_no_overlap
        EXCLUDE USING gist (
            resource_id WITH =,
            tstzrange(starts_at, ends_at, '[)') WITH &&
        )
        WHERE (status IN ('pending', 'approved'))
        """
    )


def _install_append_only_guards() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.prevent_resource_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
        END;
        $$
        """
    )
    for table_name in (
        "inventory_events",
        "equipment_service_events",
        "resource_lineage",
    ):
        op.execute(
            f"""
            CREATE TRIGGER {table_name}_append_only
            BEFORE UPDATE OR DELETE ON public.{table_name}
            FOR EACH ROW EXECUTE FUNCTION public.prevent_resource_event_mutation()
            """
        )


def downgrade() -> None:
    bind = op.get_bind()

    for table_name in (
        "inventory_events",
        "equipment_service_events",
        "resource_lineage",
    ):
        op.execute(
            f"DROP TRIGGER IF EXISTS {table_name}_append_only ON public.{table_name}"
        )
    op.execute(
        "DROP FUNCTION IF EXISTS public.prevent_resource_event_mutation()"
    )

    op.drop_constraint(
        "ck_access_grants_scope", "access_grants", type_="check"
    )
    for column_name in ("location_id", "resource_id", "resource_type_id"):
        op.drop_index(
            f"ix_access_grants_{column_name}", table_name="access_grants"
        )
        op.drop_constraint(
            f"fk_access_grants_{column_name}",
            "access_grants",
            type_="foreignkey",
        )
        op.drop_column("access_grants", column_name)
    op.create_check_constraint(
        "ck_access_grants_scope",
        "access_grants",
        "(scope_type = 'lab' AND project_id IS NULL AND protocol_id IS NULL) "
        "OR (scope_type = 'project' AND project_id IS NOT NULL AND protocol_id IS NULL) "
        "OR (scope_type = 'protocol' AND protocol_id IS NOT NULL)",
    )

    op.drop_constraint("ck_records_revision_kind", "records", type_="check")
    op.drop_index("ix_records_migration_run_id", table_name="records")
    op.drop_constraint(
        "fk_records_migration_run", "records", type_="foreignkey"
    )
    for column_name in (
        "migration_run_id",
        "source_protocol_version",
        "revision_reason",
        "revision_kind",
    ):
        op.drop_column("records", column_name)

    op.drop_column("protocol_versions", "migration_manifest")
    op.drop_column("protocol_versions", "compatibility_report")
    op.drop_constraint("ck_protocols_kind", "protocols", type_="check")
    op.drop_index("ix_protocols_kind", table_name="protocols")
    op.drop_column("protocols", "kind")

    import_models()
    from app.models.base import Base

    Base.metadata.drop_all(bind=bind, tables=_resource_tables(Base.metadata))
