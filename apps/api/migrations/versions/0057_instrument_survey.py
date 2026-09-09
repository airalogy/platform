"""Separate observation interpretation from source and interface action authority."""

from alembic import op

revision = "0057_instrument_survey"
down_revision = "0056_instrument_exploration"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(
        "ck_authoring_purpose", "instrument_authoring_sessions", type_="check"
    )
    op.create_check_constraint(
        "ck_authoring_purpose",
        "instrument_authoring_sessions",
        "purpose IN ('source','interface','survey')",
    )


def downgrade():
    # Older runtimes must not reinterpret observation-only sessions as source/action grants.
    op.execute("DELETE FROM instrument_authoring_sessions WHERE purpose = 'survey'")
    op.drop_constraint(
        "ck_authoring_purpose", "instrument_authoring_sessions", type_="check"
    )
    op.create_check_constraint(
        "ck_authoring_purpose",
        "instrument_authoring_sessions",
        "purpose IN ('source','interface')",
    )
