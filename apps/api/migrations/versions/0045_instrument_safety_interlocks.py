"""Add pinned Instrument safety contracts and Gateway attestations.

Revision ID: 0045_instrument_safety_interlocks
Revises: 0044_sample_lineage_semantics
Create Date: 2026-09-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045_instrument_safety_interlocks"
down_revision: str | None = "0044_sample_lineage_semantics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COMMAND_TABLE = "research_instrument_commands"
JOB_TABLE = "research_instrument_jobs"


def _add_json_column(table: str, name: str) -> None:
    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)
    }
    if name not in columns:
        op.add_column(
            table,
            sa.Column(
                name,
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'::json"),
            ),
        )


def upgrade() -> None:
    _add_json_column(COMMAND_TABLE, "safety_contract")
    _add_json_column(JOB_TABLE, "safety_contract")
    _add_json_column(JOB_TABLE, "safety_attestation")
    op.execute(
        sa.text(
            f"""
            UPDATE {COMMAND_TABLE}
            SET safety_contract = CAST(:contract AS JSON)
            WHERE risk = 'high'
              AND CAST(safety_contract AS TEXT) = '{{}}'
            """
        ).bindparams(
            contract=(
                '{"required_interlocks":[],"operator_presence_required":true,'
                '"emergency_stop_required":true}'
            )
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE {JOB_TABLE}
            SET safety_contract = CAST(:contract AS JSON)
            WHERE risk = 'high'
              AND status IN ('queued', 'leased')
              AND CAST(safety_contract AS TEXT) = '{{}}'
            """
        ).bindparams(
            contract=(
                '{"required_interlocks":[],"operator_presence_required":true,'
                '"emergency_stop_required":true}'
            )
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table, names in (
        (JOB_TABLE, ("safety_attestation", "safety_contract")),
        (COMMAND_TABLE, ("safety_contract",)),
    ):
        columns = {column["name"] for column in sa.inspect(bind).get_columns(table)}
        for name in names:
            if name in columns:
                op.drop_column(table, name)
