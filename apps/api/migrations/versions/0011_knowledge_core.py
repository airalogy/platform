"""Add Knowledge Core and scoped private paper library.

Revision ID: 0011_knowledge_core
Revises: 0010_research_approvals
Create Date: 2026-09-02 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

from migrations.model_registry import import_models

revision: str = "0011_knowledge_core"
down_revision: str | None = "0010_research_approvals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAMES = (
    "papers",
    "paper_library_entries",
    "paper_collections",
    "paper_collection_entries",
    "paper_project_links",
    "research_file_blobs",
    "research_files",
    "paper_file_links",
    "knowledge_items",
    "knowledge_revisions",
    "knowledge_paper_links",
    "knowledge_file_links",
    "knowledge_access_grants",
    "paper_import_drafts",
    "research_file_access_tokens",
    "research_file_access_audits",
)


def _tables(metadata):
    return [metadata.tables[name] for name in TABLE_NAMES]


def upgrade() -> None:
    bind = op.get_bind()
    import_models()
    from app.models.base import Base

    Base.metadata.create_all(bind=bind, tables=_tables(Base.metadata))


def downgrade() -> None:
    bind = op.get_bind()
    import_models()
    from app.models.base import Base

    Base.metadata.drop_all(bind=bind, tables=list(reversed(_tables(Base.metadata))))
