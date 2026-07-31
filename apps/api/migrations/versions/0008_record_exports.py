"""Add scoped, auditable Record export jobs.

Revision ID: 0008_record_exports
Revises: 0007_resource_governance
Create Date: 2026-07-31 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

from migrations.model_registry import import_models

revision: str = "0008_record_exports"
down_revision: str | None = "0007_resource_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE_NAMES = ("record_exports", "record_export_audits")


def _tables(metadata):
    return [metadata.tables[name] for name in TABLE_NAMES]


def upgrade() -> None:
    bind = op.get_bind()
    import_models()
    from app.models.base import Base

    Base.metadata.create_all(bind=bind, tables=_tables(Base.metadata))
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.prevent_record_export_audit_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'record_export_audits is append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER record_export_audits_append_only
        BEFORE UPDATE OR DELETE ON public.record_export_audits
        FOR EACH ROW EXECUTE FUNCTION public.prevent_record_export_audit_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS record_export_audits_append_only "
        "ON public.record_export_audits"
    )
    op.execute("DROP FUNCTION IF EXISTS public.prevent_record_export_audit_mutation()")
    bind = op.get_bind()
    import_models()
    from app.models.base import Base

    Base.metadata.drop_all(bind=bind, tables=_tables(Base.metadata))
