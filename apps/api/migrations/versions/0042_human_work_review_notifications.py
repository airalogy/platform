"""Add Human Work review attention notifications.

Revision ID: 0042_human_work_review_notifications
Revises: 0041_research_service_graph_state
Create Date: 2026-09-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0042_human_work_review_notifications"
down_revision: str | None = "0041_research_service_graph_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT_NAME = "ck_research_notification_kind"
OLD_KINDS = ("work_item_assigned", "approval_requested")
NEW_KINDS = (*OLD_KINDS, "work_item_review_requested")


def _kind_expression(kinds: tuple[str, ...]) -> str:
    return "kind IN (" + ", ".join(repr(item) for item in kinds) + ")"


def _replace_constraint(kinds: tuple[str, ...]) -> None:
    bind = op.get_bind()
    constraints = {
        item["name"]
        for item in sa.inspect(bind).get_check_constraints("research_notifications")
    }
    if CONSTRAINT_NAME in constraints:
        op.drop_constraint(CONSTRAINT_NAME, "research_notifications", type_="check")
    op.create_check_constraint(
        CONSTRAINT_NAME,
        "research_notifications",
        _kind_expression(kinds),
    )


def upgrade() -> None:
    _replace_constraint(NEW_KINDS)


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE research_notifications SET read_at = CURRENT_TIMESTAMP "
            "WHERE kind = 'work_item_review_requested' AND read_at IS NULL"
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM research_notification_deliveries WHERE notification_id IN "
            "(SELECT id FROM research_notifications "
            "WHERE kind = 'work_item_review_requested')"
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM research_notifications "
            "WHERE kind = 'work_item_review_requested'"
        )
    )
    _replace_constraint(OLD_KINDS)
