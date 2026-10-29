"""Persist the reservation identity already emitted when linking Record resources."""

import sqlalchemy as sa
from alembic import op

revision = "0077_record_resource_reservation"
down_revision = "0076_scenario_kits"
branch_labels = None
depends_on = None


def upgrade():
    # 0007 bootstraps current resource metadata on an empty installation.
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("record_resource_links")
    }
    if "reservation_id" not in columns:
        op.add_column(
            "record_resource_links",
            sa.Column("reservation_id", sa.UUID(), nullable=True),
        )
        op.create_foreign_key(
            "fk_record_resource_reservation",
            "record_resource_links",
            "inventory_reservations",
            ["reservation_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade():
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM record_resource_links WHERE reservation_id IS NOT NULL)"
            )
        )
        .scalar()
    ):
        raise RuntimeError("Record reservation lineage exists; refusing to discard it")
    op.drop_column("record_resource_links", "reservation_id")
