from importlib import import_module

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.knowledge import (
    KnowledgeItem,
    Paper,
    PaperLibraryEntry,
    ResearchFile,
    ResearchFileAccessAudit,
)


def compile_table(model) -> str:
    return str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))


def test_paper_visibility_is_mediated_by_scoped_library_entries():
    paper_ddl = compile_table(Paper)
    entry_ddl = compile_table(PaperLibraryEntry)

    assert "visibility" not in paper_ddl
    assert "scope_type" in entry_ddl
    assert "ck_paper_library_entries_scope" in entry_ddl
    assert "UNIQUE (doi)" in paper_ddl


def test_research_files_are_logical_scoped_assets_and_access_is_audited():
    file_ddl = compile_table(ResearchFile)
    audit_ddl = compile_table(ResearchFileAccessAudit)

    assert "blob_id" in file_ddl
    assert "scope_type" in file_ddl
    assert "visibility" in file_ddl
    assert "actor_user_id" in audit_ddl
    assert "outcome" in audit_ddl


def test_knowledge_items_keep_review_and_lineage_fields():
    ddl = compile_table(KnowledgeItem)

    assert "derived_from_id" in ddl
    assert "reviewed_by_user_id" in ddl
    assert "superseded_by_id" in ddl
    assert "revision" in ddl


def test_knowledge_migration_is_chained_and_complete():
    migration = import_module("migrations.versions.0011_knowledge_core")

    assert migration.down_revision == "0010_research_approvals"
    assert {
        "papers",
        "paper_library_entries",
        "research_files",
        "knowledge_items",
        "paper_import_drafts",
        "research_file_access_audits",
    }.issubset(set(migration.TABLE_NAMES))
