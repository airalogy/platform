"""Allow separately identified, non-executing advanced analysis AI drafts."""

import sqlalchemy as sa
from alembic import op

revision = "0062_analysis_compute_ai"
down_revision = "0061_analysis_compute"
branch_labels = None
depends_on = None


def _replace(kind, run_kind):
    op.drop_constraint("ck_analysis_ai_run_kind", "analysis_ai_requests", type_="check")
    op.drop_constraint("ck_analysis_ai_kind", "analysis_ai_requests", type_="check")
    op.create_check_constraint("ck_analysis_ai_kind", "analysis_ai_requests", kind)
    op.create_check_constraint(
        "ck_analysis_ai_run_kind", "analysis_ai_requests", run_kind
    )


def upgrade():
    _replace(
        "kind IN ('draft','compute_draft','interpretation')",
        "(kind IN ('draft','compute_draft') AND analysis_run_id IS NULL) OR "
        "(kind = 'interpretation' AND analysis_run_id IS NOT NULL)",
    )


def downgrade():
    # Never discard paid-attempt history or provenance to make an old schema fit.
    connection = op.get_bind()
    connection.execute(
        sa.text("LOCK TABLE analysis_ai_requests IN ACCESS EXCLUSIVE MODE")
    )
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM analysis_ai_requests AS request "
            "LEFT JOIN analysis_runs AS run ON run.id = request.analysis_run_id "
            "WHERE request.kind = 'compute_draft' "
            "OR request.input_context->>'result_kind' = 'compute' "
            "OR run.engine_version = 'airalogy.compute.analysis.v1')"
        )
    ):
        raise RuntimeError(
            "Cannot downgrade while advanced analysis AI drafts or interpretations exist"
        )
    _replace(
        "kind IN ('draft','interpretation')",
        "(kind = 'draft' AND analysis_run_id IS NULL) OR "
        "(kind = 'interpretation' AND analysis_run_id IS NOT NULL)",
    )
