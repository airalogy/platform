from importlib import import_module
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import union_all
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.main import app
from app.models.research_log import (
    ResearchLogEntry,
    ResearchLogRevision,
    ResearchLogScope,
)
from app.routers.research_log import (
    LogScopeContext,
    ResearchLogEntryDraft,
    ResearchLogEntryUpdate,
    _event_selects,
)


def compile_table(model) -> str:
    return str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))


def test_research_log_entries_are_scoped_and_revisioned():
    entry_ddl = compile_table(ResearchLogEntry)
    revision_ddl = compile_table(ResearchLogRevision)

    assert "ck_research_log_entries_scope" in entry_ddl
    assert "completed_items" in entry_ddl
    assert "evidence" in entry_ddl
    assert "risks" in entry_ddl
    assert "next_steps" in entry_ddl
    assert "asset_links" in entry_ddl
    assert "UNIQUE (log_entry_id, revision)" in revision_ddl


def test_research_log_migration_follows_research_environment():
    migration = import_module("migrations.versions.0013_research_log")

    assert migration.down_revision == "0012_research_environment_knowledge"
    assert migration.TABLE_NAMES == (
        "research_log_entries",
        "research_log_revisions",
    )


def test_log_draft_normalizes_structured_sections():
    draft = ResearchLogEntryDraft(
        scope_type="project",
        lab_id=uuid4(),
        project_id=uuid4(),
        kind="progress",
        title="  Weekly progress  ",
        body="  Main observation  ",
        completed_items=[" first ", "", " second"],
        next_steps=[" repeat assay "],
    )

    assert draft.title == "Weekly progress"
    assert draft.body == "Main observation"
    assert draft.completed_items == ["first", "second"]
    assert draft.next_steps == ["repeat assay"]


def test_log_revision_requires_a_stale_guard_and_change_summary():
    with pytest.raises(ValidationError):
        ResearchLogEntryUpdate(expected_revision=1, body="changed", change_summary="")


def test_project_timeline_union_compiles_all_authoritative_sources():
    scope = LogScopeContext(
        ResearchLogScope.PROJECT,
        None,
        SimpleNamespace(id=uuid4()),
        SimpleNamespace(id=uuid4()),
    )
    selects = _event_selects(scope)

    statement = union_all(*selects)
    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert len(selects) == 6
    assert "research_log_entries" in sql
    assert "records" in sql
    assert "protocol_versions" in sql
    assert "knowledge_items" in sql
    assert "research_events" in sql


def test_personal_timeline_only_projects_own_logs_and_records():
    user_id = uuid4()
    scope = LogScopeContext(ResearchLogScope.PERSONAL, user_id, None, None)
    selects = _event_selects(scope)

    sql = str(union_all(*selects).compile(dialect=postgresql.dialect()))

    assert len(selects) == 2
    assert "research_log_entries" in sql
    assert "records" in sql
    assert "protocol_versions" not in sql


def test_openapi_exposes_manual_log_and_aggregate_timeline_contracts():
    paths = app.openapi()["paths"]

    assert "/research-log/timeline" in paths
    assert "/research-log/entries" in paths
    assert "/research-log/entries/{entry_id}" in paths
    assert "/research-log/entries/{entry_id}/revisions" in paths
    assert "post" in paths["/research-log/entries"]
    assert "patch" in paths["/research-log/entries/{entry_id}"]
