import inspect
from importlib import import_module

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.knowledge import (
    KnowledgeItem,
    Paper,
    PaperLibraryEntry,
    ResearchFile,
    ResearchFileAccessAudit,
)
from app.services.knowledge import (
    is_pdf,
    normalize_doi,
    paper_fingerprint,
    parse_paper_source,
    safe_download_filename,
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
    source = inspect.getsource(migration)
    assert "research_file_access_audits_append_only" in source


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("10.1000/ABC.Def", "10.1000/abc.def"),
        ("doi: 10.1000/ABC.Def", "10.1000/abc.def"),
        ("https://doi.org/10.1000/ABC.Def", "10.1000/abc.def"),
        ("doi:https://dx.doi.org/10.1000/ABC.Def", "10.1000/abc.def"),
    ],
)
def test_doi_normalization_accepts_common_forms(value, expected):
    assert normalize_doi(value) == expected


def test_doi_normalization_rejects_malformed_identifiers():
    with pytest.raises(ValueError, match="Invalid DOI"):
        normalize_doi("not-a-doi")


def test_no_doi_fingerprint_normalizes_case_punctuation_and_whitespace():
    first = paper_fingerprint("A Study: of Cells", 2026, "Alice Smith")
    second = paper_fingerprint("  a study of cells ", 2026, "ALICE  SMITH")

    assert first == second
    assert len(first) == 64


def test_bibtex_and_ris_imports_produce_the_same_canonical_shape():
    bibtex = parse_paper_source(
        "bibtex",
        """@article{smith2026,
          title={A reproducible result},
          author={Alice Smith and Bob Li},
          year={2026},
          doi={https://doi.org/10.1234/ABC},
          journal={Airalogy Research}
        }""",
    )
    ris = parse_paper_source(
        "ris",
        """TY  - JOUR
TI  - A reproducible result
AU  - Alice Smith
AU  - Bob Li
PY  - 2026
DO  - 10.1234/abc
JO  - Airalogy Research
ER  -""",
    )

    for key in ("title", "authors", "publication_year", "doi", "venue"):
        assert bibtex[key] == ris[key]
    assert bibtex["candidate_fingerprint"] == ris["candidate_fingerprint"]
    assert bibtex["metadata_json"] == {}
    assert ris["metadata_json"] == {}


def test_pdf_detection_uses_file_signature_and_filename_is_header_safe():
    assert is_pdf(b"%PDF-1.7\n")
    assert not is_pdf(b"<html>not a pdf</html>")
    assert safe_download_filename("../../paper\r\nInjected.pdf") == "paperInjected.pdf"


def test_openapi_exposes_preview_confirm_and_short_lived_file_access():
    from app.main import app

    paths = app.openapi()["paths"]
    assert "/knowledge/papers/import/preview" in paths
    assert "/knowledge/papers/import/{draft_id}/confirm" in paths
    assert "/knowledge/papers/import/pdf/preview" in paths
    assert "/knowledge/files/{file_id}/token" in paths
    assert "/knowledge/files/{file_id}/content" in paths
    assert "/knowledge/collections/{collection_id}/entries/{entry_id}" in paths
    assert "/knowledge/items/{item_id}/publish/preview" in paths
    assert "/knowledge/items/{item_id}/publish/confirm" in paths
