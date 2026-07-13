"""Generalize teams into typed organizational units.

Revision ID: 0004_organizational_units
Revises: 0003_structured_access_control
Create Date: 2026-07-13 00:00:00.000000
"""

from typing import Sequence

from alembic import op

revision: str = "0004_organizational_units"
down_revision: str | None = "0003_structured_access_control"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Revision 0001 creates its tables from current model metadata on fresh
    # installs, so this column can already exist before revision 0004 runs.
    op.execute(
        "ALTER TABLE groups ADD COLUMN IF NOT EXISTS "
        "unit_type VARCHAR DEFAULT 'other' NOT NULL"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'groups'::regclass
                  AND conname = 'ck_groups_unit_type'
            ) THEN
                ALTER TABLE groups
                ADD CONSTRAINT ck_groups_unit_type
                CHECK (unit_type IN (
                    'department', 'research_group', 'core_facility',
                    'project_team', 'committee', 'other'
                ));
            END IF;
        END
        $$
        """
    )
    op.execute(
        "ALTER TABLE access_grants DROP CONSTRAINT IF EXISTS "
        "ck_access_grants_subject"
    )
    op.execute(
        "UPDATE access_grants SET subject_type = 'org_unit' "
        "WHERE subject_type = 'team'"
    )
    op.create_check_constraint(
        "ck_access_grants_subject",
        "access_grants",
        "(subject_type = 'user' AND user_id IS NOT NULL AND group_id IS NULL) "
        "OR (subject_type = 'org_unit' AND group_id IS NOT NULL AND user_id IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_access_grants_subject", "access_grants", type_="check"
    )
    op.execute(
        "UPDATE access_grants SET subject_type = 'team' "
        "WHERE subject_type = 'org_unit'"
    )
    op.create_check_constraint(
        "ck_access_grants_subject",
        "access_grants",
        "(subject_type = 'user' AND user_id IS NOT NULL AND group_id IS NULL) "
        "OR (subject_type = 'team' AND group_id IS NOT NULL AND user_id IS NULL)",
    )
    op.execute(
        "ALTER TABLE groups DROP CONSTRAINT IF EXISTS ck_groups_unit_type"
    )
    op.execute("ALTER TABLE groups DROP COLUMN IF EXISTS unit_type")
