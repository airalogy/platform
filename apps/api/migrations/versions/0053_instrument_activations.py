"""Version-pinned managed execution, separate from qualification and installation."""

import sqlalchemy as sa
from alembic import op

revision = "0053_instrument_activations"
down_revision = "0052_instrument_qualifications"
branch_labels = None
depends_on = None
TABLE_NAMES = ("instrument_activations", "instrument_job_activations")


def upgrade():
    references = {
        "binding": "instrument_device_bindings",
        "qualification": "instrument_qualifications",
        "lab": "labs",
        "gateway": "research_instrument_gateways",
        "resource": "resources",
    }
    op.create_table(
        "instrument_activations",
        sa.Column("id", sa.UUID(), primary_key=True),
        *[
            sa.Column(
                f"{name}_id",
                sa.UUID(),
                sa.ForeignKey(
                    f"{table}.id", ondelete="CASCADE" if name == "lab" else "RESTRICT"
                ),
                nullable=False,
            )
            for name, table in references.items()
        ],
        sa.Column("authorization_digest", sa.String(64), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("commands", sa.JSON(), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "revoked_by_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("revoke_reason", sa.Text()),
    )
    op.create_index(
        "ix_instrument_activations_binding_id", "instrument_activations", ["binding_id"]
    )
    for scope in ("gateway", "resource"):
        op.create_index(
            f"uq_instrument_activation_current_{scope}",
            "instrument_activations",
            [f"{scope}_id"],
            unique=True,
            postgresql_where=sa.text("revoked_at IS NULL"),
        )
    op.create_table(
        "instrument_job_activations",
        sa.Column(
            "job_id",
            sa.UUID(),
            sa.ForeignKey("research_instrument_jobs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "activation_id",
            sa.UUID(),
            sa.ForeignKey("instrument_activations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("pin", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_instrument_job_activations_activation_id",
        "instrument_job_activations",
        ["activation_id"],
    )


def downgrade():
    op.drop_table("instrument_job_activations")
    op.drop_table("instrument_activations")
