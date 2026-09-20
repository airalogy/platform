"""Frozen schema and SQL guards for reviewed analysis-derived Protocol packages."""

from importlib import import_module
from io import StringIO
from pathlib import Path
from unittest.mock import Mock

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.analysis_protocol import (
    AnalysisProtocolDraft,
    AnalysisProtocolDraftReview,
    AnalysisProtocolDraftRevision,
    AnalysisProtocolMethodLink,
)
from migrations.model_registry import MODEL_MODULES, import_models
from tests.test_analysis_models import _column_signature, _constraint_signature

MODELS = (
    AnalysisProtocolDraft,
    AnalysisProtocolDraftRevision,
    AnalysisProtocolDraftReview,
    AnalysisProtocolMethodLink,
)
MIGRATION = "migrations.versions.0074_analysis_protocol_drafts"


@pytest.fixture(scope="module", autouse=True)
def registered_models():
    import_models()


def ddl(model):
    return str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))


def test_analysis_protocol_models_have_one_frozen_revision_and_registry_entry():
    assert "app.models.analysis_protocol" in MODEL_MODULES
    migration = import_module(MIGRATION)
    assert migration.revision == "0074_analysis_protocol_drafts"
    assert migration.down_revision == "0073_workflow_project_analysis"
    assert migration.TABLE_NAMES == tuple(model.__tablename__ for model in MODELS)
    assert migration.branch_labels is migration.depends_on is None
    initial = import_module("migrations.versions.0001_initial_schema")
    assert set(migration.TABLE_NAMES).isdisjoint(initial.INITIAL_TABLE_NAMES)


@pytest.mark.parametrize("model", MODELS)
def test_history_foreign_keys_are_required_restrict_not_cascading(model):
    assert model.__table__.foreign_keys
    for constraint in model.__table__.foreign_key_constraints:
        assert constraint.ondelete == "RESTRICT"
    for column in model.__table__.c:
        assert column.nullable == (
            column.name in {"target_protocol_id", "base_protocol_version_id"}
        )
        if isinstance(column.type, sa.DateTime):
            assert column.type.timezone
            assert str(column.server_default.arg) == "now()"
    assert "CASCADE" not in ddl(model)


@pytest.mark.parametrize("model", MODELS)
def test_every_digest_has_db_format_validation(model):
    sql = ddl(model)
    for column in model.__table__.c:
        if column.name.endswith("_digest"):
            assert column.type.length == 64
            assert f"{column.name} ~ '^[0-9a-f]{{64}}$'" in sql


def test_parent_has_creator_bound_idempotency_and_paired_existing_target():
    model = AnalysisProtocolDraft
    sql = ddl(model)
    assert "UNIQUE (created_by_user_id, idempotency_key)" in sql
    assert "CHECK (revision >= 1)" in sql
    assert "CHECK (state IN ('draft','reviewed','rejected','applied'))" in sql
    assert (
        "CHECK ((target_protocol_id IS NULL) = (base_protocol_version_id IS NULL))"
        in sql
    )
    assert model.__table__.c.state.default.arg == "draft"
    assert model.__table__.c.revision.default.arg == 1
    assert str(model.__table__.c.id.server_default.arg) == "uuid_generate_v7()"
    assert set(model.__table__.primary_key.columns.keys()) == {"id"}


def test_revision_keeps_files_and_exact_request_not_mutable_parent_contents():
    table = AnalysisProtocolDraftRevision.__table__
    assert tuple(table.primary_key.columns.keys()) == ("draft_id", "revision")
    assert "UNIQUE (draft_id, idempotency_key)" in ddl(AnalysisProtocolDraftRevision)
    assert "jsonb_typeof(files::jsonb) = 'object'" in ddl(AnalysisProtocolDraftRevision)
    assert isinstance(table.c.files.type, sa.JSON)
    assert isinstance(table.c.reason.type, sa.Text)
    assert "files" not in AnalysisProtocolDraft.__table__.c


@pytest.mark.parametrize(
    "model", (AnalysisProtocolDraftReview, AnalysisProtocolMethodLink)
)
def test_review_and_link_have_exact_composite_revision_foreign_key(model):
    foreign_keys = _constraint_signature(model.__table__)
    assert (
        "foreign_key",
        ("draft_id", "revision"),
        (
            "analysis_protocol_draft_revisions.draft_id",
            "analysis_protocol_draft_revisions.revision",
        ),
        "RESTRICT",
    ) in foreign_keys
    assert "CHECK (revision >= 1)" in ddl(model)


def test_review_is_once_per_revision_and_link_once_per_draft_and_version():
    review = ddl(AnalysisProtocolDraftReview)
    link = ddl(AnalysisProtocolMethodLink)
    assert "UNIQUE (draft_id, revision)" in review
    assert "CHECK (decision IN ('reviewed','rejected'))" in review
    assert "PRIMARY KEY (protocol_version_id)" in link
    assert "UNIQUE (draft_id)" in link


def test_frozen_migration_matches_model_columns_indexes_and_constraints(monkeypatch):
    migration = import_module(MIGRATION)
    metadata = sa.MetaData()
    for name in (
        "projects",
        "protocols",
        "protocol_versions",
        "users",
        "workflow_analysis_methods",
    ):
        sa.Table(name, metadata, sa.Column("id", sa.UUID(), primary_key=True))
    tables, indexes = {}, {}

    def create_table(name, *columns):
        tables[name] = sa.Table(name, metadata, *columns)

    def create_index(name, table, columns):
        indexes[name] = (table, tuple(columns))

    monkeypatch.setattr(migration.op, "create_table", create_table)
    monkeypatch.setattr(migration.op, "create_index", create_index)
    monkeypatch.setattr(migration.op, "execute", Mock())
    migration.upgrade()
    assert tuple(tables) == migration.TABLE_NAMES
    for model in MODELS:
        frozen, declared = tables[model.__tablename__], model.__table__
        assert {column.name: _column_signature(column) for column in frozen.c} == {
            column.name: _column_signature(column) for column in declared.c
        }
        assert _constraint_signature(frozen) == _constraint_signature(declared)
        assert str(CreateTable(frozen).compile(dialect=postgresql.dialect()))
        assert {
            name: spec for name, spec in indexes.items() if spec[0] == declared.name
        } == {
            index.name: (declared.name, tuple(index.columns.keys()))
            for index in declared.indexes
        }
    source = Path(migration.__file__).read_text()
    assert "Base.metadata" not in source and "import_models" not in source


@pytest.fixture
def guard_sql(monkeypatch):
    migration = import_module(MIGRATION)
    execute = Mock()
    monkeypatch.setattr(migration.op, "execute", execute)
    migration._create_guards()
    return "\n".join(str(call.args[0]) for call in execute.call_args_list)


def test_insert_and_reverse_scope_guards_preserve_method_target_and_base(guard_sql):
    for expression in (
        "m.id = NEW.method_id AND m.project_id = NEW.project_id",
        "p.id = NEW.target_protocol_id AND p.project_id = NEW.project_id",
        "v.id = NEW.base_protocol_version_id",
        "NEW.project_id IS DISTINCT FROM OLD.project_id",
        "NEW.protocol_id IS DISTINCT FROM OLD.protocol_id",
        "WHERE target_protocol_id = OLD.id",
        "WHERE base_protocol_version_id = OLD.id",
    ):
        assert expression in guard_sql


def test_parent_identity_revision_and_applied_terminal_are_protected(guard_sql):
    for expression in (
        "NEW.revision <> 1 OR NEW.state <> 'draft'",
        "to_jsonb(NEW) - ARRAY['revision','state','updated_at']",
        "OLD.state = 'applied' AND to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD)",
        "NEW.revision <> OLD.revision + 1 OR NEW.state <> 'draft'",
        "NEW.state IN ('reviewed','rejected') AND OLD.state = 'draft'",
        "NEW.state = 'applied' AND OLD.state = 'reviewed'",
        "r.decision = NEW.state",
        "l.revision = NEW.revision AND l.method_id = NEW.method_id",
    ):
        assert expression in guard_sql


def test_child_writes_lock_parent_and_bind_current_revision_and_digests(guard_sql):
    assert guard_sql.count("WHERE id = NEW.draft_id FOR UPDATE") == 3
    for expression in (
        "d.created_by_user_id <> NEW.created_by_user_id",
        "NEW.idempotency_key <> d.idempotency_key OR NEW.request_digest <> d.request_digest",
        "digest = NEW.method_digest",
        "jsonb_typeof(entry.value) <> 'string'",
        "r.revision = NEW.revision AND r.package_digest = NEW.package_digest",
        "d.state <> 'reviewed' OR d.revision <> NEW.revision OR d.method_id <> NEW.method_id",
        "d.target_protocol_id <> NEW.protocol_id",
        "NEW.protocol_version_id = d.base_protocol_version_id",
        "m.digest = r.method_digest AND m.project_id = d.project_id",
        "v.id = NEW.protocol_version_id AND v.protocol_id = p.id",
        "review.package_digest = NEW.package_digest",
        "review.decision = 'reviewed'",
    ):
        assert expression in guard_sql


def test_all_history_is_append_only_and_deferred_state_is_atomic(guard_sql):
    for index, model in enumerate(MODELS):
        events = "DELETE" if index == 0 else "UPDATE OR DELETE"
        assert f"BEFORE {events} ON {model.__tablename__}" in guard_sql
        assert (
            f"AFTER INSERT OR UPDATE ON {model.__tablename__} DEFERRABLE INITIALLY DEFERRED"
            in guard_sql
        )
    for expression in (
        "Current Analysis Protocol draft revision must exist at commit",
        "d.state = 'draft' AND decision IS NOT NULL",
        "d.state IN ('reviewed','rejected') AND decision IS DISTINCT FROM d.state",
        "d.state = 'applied' AND decision IS DISTINCT FROM 'reviewed'",
        "Analysis Protocol application and version link must commit together",
    ):
        assert expression in guard_sql


def test_alembic_upgrade_renders_standalone_postgresql_ddl_without_database():
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    with Operations.context(context):
        import_module(MIGRATION).upgrade()
    sql = output.getvalue()
    for model in MODELS:
        assert f"CREATE TABLE {model.__tablename__}" in sql
    assert sql.count("CREATE FUNCTION") == 7
    assert sql.count("CREATE CONSTRAINT TRIGGER") == 4
    assert "ON DELETE CASCADE" not in sql


@pytest.mark.parametrize("has_drafts", [True, False])
def test_downgrade_locks_all_tables_and_refuses_any_existing_draft(
    monkeypatch, has_drafts
):
    migration = import_module(MIGRATION)
    connection, drop, execute = Mock(), Mock(), Mock()
    connection.scalar.return_value = has_drafts
    monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
    monkeypatch.setattr(migration.op, "drop_table", drop)
    monkeypatch.setattr(migration.op, "execute", execute)
    if has_drafts:
        with pytest.raises(RuntimeError, match="Cannot downgrade"):
            migration.downgrade()
        drop.assert_not_called()
        execute.assert_not_called()
    else:
        migration.downgrade()
        assert [call.args[0] for call in drop.call_args_list] == list(
            reversed(migration.TABLE_NAMES)
        )
        assert len(execute.call_args_list) == 9
    lock = str(connection.execute.call_args.args[0])
    assert "ACCESS EXCLUSIVE MODE" in lock
    assert all(table in lock for table in migration.TABLE_NAMES)
    assert (
        str(connection.scalar.call_args.args[0])
        == "SELECT EXISTS (SELECT 1 FROM analysis_protocol_drafts)"
    )
