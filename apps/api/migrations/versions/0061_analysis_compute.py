"""Reuse governed Compute Jobs for private, explicitly approved analyses."""

import sqlalchemy as sa
from alembic import op

revision = "0061_analysis_compute"
down_revision = "0060_analysis_ai"
branch_labels = None
depends_on = None
TABLE_NAMES = ("analysis_computations", "analysis_compute_events")


def upgrade():
    # Frozen DDL: never derive historical migrations from application models.
    op.create_table(
        "analysis_computations",
        sa.Column(
            "analysis_run_id",
            sa.UUID(),
            sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "approval_state", sa.String(16), nullable=False, server_default="pending"
        ),
        sa.Column(
            "approval_revision", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column(
            "approver_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("contract_digest", sa.String(64), nullable=False),
        sa.Column("max_cost", sa.Numeric(38, 18)),
        sa.Column("budget_currency", sa.String(3)),
        sa.Column("deadline_at", sa.DateTime(timezone=True)),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column(
            "decided_by_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("decision_reason", sa.Text(), nullable=False, server_default=""),
        sa.CheckConstraint(
            "approval_state IN ('pending','approved','rejected','cancelled')",
            name="ck_analysis_compute_approval_state",
        ),
        sa.CheckConstraint(
            "approval_revision >= 1", name="ck_analysis_compute_approval_revision"
        ),
        sa.CheckConstraint(
            "contract_digest ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_compute_contract_digest",
        ),
        sa.CheckConstraint(
            "(max_cost IS NULL AND budget_currency IS NULL) OR "
            "(max_cost IS NOT NULL AND max_cost >= 0 AND "
            "max_cost <> 'NaN'::numeric AND budget_currency IS NOT NULL AND "
            "budget_currency ~ '^[A-Z]{3}$')",
            name="ck_analysis_compute_budget_pair",
        ),
    )
    op.create_index(
        "ix_analysis_computations_approver_state",
        "analysis_computations",
        ["approver_user_id", "approval_state"],
    )
    op.create_index(
        "ix_analysis_computations_state_deadline",
        "analysis_computations",
        ["approval_state", "deadline_at"],
    )
    op.create_table(
        "analysis_compute_events",
        sa.Column(
            "id", sa.UUID(), primary_key=True, server_default=sa.func.uuid_generate_v7()
        ),
        sa.Column(
            "analysis_run_id",
            sa.UUID(),
            sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "actor_user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "analysis_run_id", "idempotency_key", name="uq_analysis_compute_event_key"
        ),
    )
    op.create_index(
        "ix_analysis_compute_events_analysis_run_id",
        "analysis_compute_events",
        ["analysis_run_id"],
    )
    op.create_index(
        "ix_analysis_compute_events_analysis_created",
        "analysis_compute_events",
        ["analysis_run_id", "created_at"],
    )
    op.add_column(
        "research_compute_jobs",
        sa.Column(
            "analysis_run_id",
            sa.UUID(),
            sa.ForeignKey("analysis_runs.id", ondelete="RESTRICT"),
        ),
    )
    op.alter_column(
        "research_compute_jobs", "action_id", existing_type=sa.UUID(), nullable=True
    )
    op.create_index(
        "ix_research_compute_jobs_analysis_run_id",
        "research_compute_jobs",
        ["analysis_run_id"],
        unique=True,
    )
    op.create_check_constraint(
        "ck_research_compute_job_context",
        "research_compute_jobs",
        "(action_id IS NOT NULL AND analysis_run_id IS NULL) OR "
        "(action_id IS NULL AND analysis_run_id IS NOT NULL)",
    )
    op.add_column(
        "research_compute_job_inputs",
        sa.Column(
            "analysis_run_id",
            sa.UUID(),
            sa.ForeignKey("analysis_runs.id", ondelete="RESTRICT"),
        ),
    )
    for column in ("data_asset_id", "data_asset_version_id"):
        op.alter_column(
            "research_compute_job_inputs",
            column,
            existing_type=sa.UUID(),
            nullable=True,
        )
    op.create_index(
        "ix_research_compute_job_inputs_analysis_run_id",
        "research_compute_job_inputs",
        ["analysis_run_id"],
    )
    op.create_check_constraint(
        "ck_research_compute_job_input_source",
        "research_compute_job_inputs",
        "(data_asset_id IS NOT NULL AND data_asset_version_id IS NOT NULL "
        "AND analysis_run_id IS NULL) OR "
        "(data_asset_id IS NULL AND data_asset_version_id IS NULL "
        "AND analysis_run_id IS NOT NULL)",
    )


def downgrade():
    # Check before any DDL. Back up and explicitly handle analysis assets first;
    # never delete user computations or silently drop their audit history.
    op.execute(
        sa.text("""
        DO $$
        BEGIN
            LOCK TABLE research_compute_jobs, research_compute_job_inputs,
                analysis_computations, analysis_compute_events IN ACCESS EXCLUSIVE MODE;
            IF EXISTS (SELECT 1 FROM research_compute_jobs WHERE analysis_run_id IS NOT NULL)
                OR EXISTS (SELECT 1 FROM research_compute_job_inputs WHERE analysis_run_id IS NOT NULL)
                OR EXISTS (SELECT 1 FROM analysis_computations)
                OR EXISTS (SELECT 1 FROM analysis_compute_events)
            THEN
                RAISE EXCEPTION 'Cannot downgrade 0061_analysis_compute while analysis computation assets exist; back up and handle them explicitly before retrying';
            END IF;
        END
        $$;
        """)
    )
    op.drop_constraint(
        "ck_research_compute_job_input_source",
        "research_compute_job_inputs",
        type_="check",
    )
    op.drop_index(
        "ix_research_compute_job_inputs_analysis_run_id",
        table_name="research_compute_job_inputs",
    )
    op.drop_column("research_compute_job_inputs", "analysis_run_id")
    for column in ("data_asset_id", "data_asset_version_id"):
        op.alter_column(
            "research_compute_job_inputs",
            column,
            existing_type=sa.UUID(),
            nullable=False,
        )
    op.drop_constraint(
        "ck_research_compute_job_context", "research_compute_jobs", type_="check"
    )
    op.drop_index(
        "ix_research_compute_jobs_analysis_run_id", table_name="research_compute_jobs"
    )
    op.drop_column("research_compute_jobs", "analysis_run_id")
    op.alter_column(
        "research_compute_jobs", "action_id", existing_type=sa.UUID(), nullable=False
    )
    for table in reversed(TABLE_NAMES):
        op.drop_table(table)
