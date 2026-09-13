"""Storage and frozen migration contracts for non-executing AI requests."""

from importlib import import_module
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.analysis import AnalysisPreview, AnalysisRun
from app.models.analysis_ai import (
    AnalysisAIRequest,
    AnalysisAIRequestKind,
    AnalysisAIRequestState,
)
from migrations.model_registry import MODEL_MODULES, import_models


@pytest.fixture(scope="module", autouse=True)
def registered_models():
    import_models()


def ddl():
    return str(
        CreateTable(AnalysisAIRequest.__table__).compile(dialect=postgresql.dialect())
    )


def test_request_registration_and_migration_keep_a_linear_history():
    assert "app.models.analysis_ai" in MODEL_MODULES
    migration = import_module("migrations.versions.0060_analysis_ai")
    assert migration.revision == "0060_analysis_ai"
    assert migration.down_revision == "0059_analysis"
    assert migration.TABLE_NAMES == ("analysis_ai_requests",)
    assert migration.branch_labels is None
    assert migration.depends_on is None


def test_explicit_request_id_can_guard_a_paid_request_without_creating_execution():
    identity = uuid4()
    request = AnalysisAIRequest(id=identity)
    assert request.id == identity
    columns = AnalysisAIRequest.__table__.c
    assert columns.id.primary_key
    assert str(columns.id.server_default.arg) == "uuid_generate_v7()"
    assert "job_id" not in columns
    assert "visibility" not in columns
    assert "public" not in columns
    assert columns.operation_id.type.length == 128
    assert columns.model.type.length == 255
    assert columns.error.type.length == 64
    assert not columns.created_by_user_id.nullable
    assert not columns.project_id.nullable
    assert not columns.protocol_id.nullable


def test_draft_and_interpretation_are_distinct_typed_states():
    assert {kind.value for kind in AnalysisAIRequestKind} == {
        "draft",
        "compute_draft",
        "interpretation",
    }
    assert {state.value for state in AnalysisAIRequestState} == {
        "generating",
        "generated",
        "failed",
    }
    table_sql = ddl()
    assert "kind IN ('draft','compute_draft','interpretation')" in table_sql
    assert (
        "(kind IN ('draft','compute_draft') AND analysis_run_id IS NULL) OR (kind = 'interpretation' AND analysis_run_id IS NOT NULL)"
        in table_sql
    )
    assert "state IN ('generating','generated','failed')" in table_sql
    assert "state <> 'generated' OR output IS NOT NULL" in table_sql
    assert AnalysisAIRequest.__table__.c.state.default.arg == "generating"


def test_output_and_source_digests_are_real_and_nullable_outputs_are_sql_null():
    table = AnalysisAIRequest.__table__
    assert table.c.output.nullable
    assert table.c.output.type.none_as_null
    table_sql = ddl()
    assert "(output IS NULL) = (output_digest IS NULL)" in table_sql
    for name in ("request_fingerprint", "input_digest", "source_digest"):
        assert not table.c[name].nullable
        assert table.c[name].type.length == 64
        assert f"{name} ~ '^[0-9a-f]{{64}}$'" in table_sql
    assert "output_digest IS NULL OR output_digest ~ '^[0-9a-f]{64}$'" in table_sql
    for name in ("source_selection", "source_manifest", "input_context"):
        assert not table.c[name].nullable
        assert isinstance(table.c[name].type, sa.JSON)
        assert table.c[name].default.is_callable


def test_request_lineage_preserves_exact_run_and_never_points_to_itself():
    table = AnalysisAIRequest.__table__
    expected = {
        "project_id": ("projects.id", "CASCADE"),
        "protocol_id": ("protocols.id", "RESTRICT"),
        "created_by_user_id": ("users.id", "RESTRICT"),
        "analysis_run_id": ("analysis_runs.id", "RESTRICT"),
        "previous_request_id": ("analysis_ai_requests.id", "RESTRICT"),
    }
    actual = {
        foreign_key.parent.name: (foreign_key.target_fullname, foreign_key.ondelete)
        for foreign_key in table.foreign_keys
    }
    assert actual == expected
    assert "previous_request_id IS NULL OR previous_request_id <> id" in ddl()


def test_deadlines_and_owner_indexes_support_private_recovery():
    table = AnalysisAIRequest.__table__
    for name in ("deadline", "created_at", "finished_at"):
        assert table.c[name].type.timezone
    assert not table.c.deadline.nullable
    assert not table.c.created_at.nullable
    assert table.c.finished_at.nullable
    assert str(table.c.created_at.server_default.arg) == "now()"
    indexes = {index.name: tuple(index.columns.keys()) for index in table.indexes}
    assert indexes["ix_analysis_ai_requests_owner_protocol_created"] == (
        "created_by_user_id",
        "protocol_id",
        "created_at",
    )
    assert indexes["ix_analysis_ai_requests_state_deadline"] == ("state", "deadline")
    assert indexes["ix_analysis_ai_requests_analysis_run_id"] == ("analysis_run_id",)


@pytest.mark.parametrize("model", [AnalysisPreview, AnalysisRun])
def test_manual_assets_have_empty_nonnullable_ai_provenance(model):
    column = model.__table__.c.ai_provenance
    assert isinstance(column.type, sa.JSON)
    assert not column.nullable
    assert column.default.is_callable
    assert column.server_default.arg == "{}"


def column_signature(column):
    return (
        str(column.type.compile(dialect=postgresql.dialect())),
        column.nullable,
        column.primary_key,
        str(column.server_default.arg) if column.server_default else None,
    )


def constraint_signature(table):
    signatures = set()
    for constraint in table.constraints:
        if isinstance(constraint, sa.CheckConstraint):
            signatures.add(("check", constraint.name, str(constraint.sqltext)))
        elif isinstance(constraint, sa.UniqueConstraint):
            signatures.add(
                ("unique", constraint.name, tuple(constraint.columns.keys()))
            )
        elif isinstance(constraint, sa.ForeignKeyConstraint):
            signatures.add(
                (
                    "foreign_key",
                    tuple(constraint.columns.keys()),
                    tuple(element.target_fullname for element in constraint.elements),
                    constraint.ondelete,
                )
            )
    return signatures


def test_frozen_0060_ddl_matches_new_request_and_added_provenance_columns(monkeypatch):
    migration = import_module("migrations.versions.0060_analysis_ai")
    metadata = sa.MetaData()
    for name in (
        "projects",
        "protocols",
        "users",
        "analysis_runs",
        "analysis_previews",
    ):
        sa.Table(name, metadata, sa.Column("id", sa.UUID(), primary_key=True))
    tables = {}
    indexes = {}
    additions = {}

    def create_table(name, *columns_and_constraints):
        tables[name] = sa.Table(name, metadata, *columns_and_constraints)

    def create_index(name, table, columns):
        indexes[name] = (table, tuple(columns))

    def add_column(table, column):
        additions[table] = column

    monkeypatch.setattr(migration.op, "create_table", create_table)
    monkeypatch.setattr(migration.op, "create_index", create_index)
    monkeypatch.setattr(migration.op, "add_column", add_column)
    migration.upgrade()
    assert tuple(tables) == migration.TABLE_NAMES
    migrated = tables["analysis_ai_requests"]
    declared = AnalysisAIRequest.__table__
    assert {column.name: column_signature(column) for column in migrated.c} == {
        column.name: column_signature(column) for column in declared.c
    }
    changed_constraints = {"ck_analysis_ai_kind", "ck_analysis_ai_run_kind"}
    assert {
        signature
        for signature in constraint_signature(migrated)
        if signature[1] not in changed_constraints
    } == {
        signature
        for signature in constraint_signature(declared)
        if signature[1] not in changed_constraints
    }
    assert "kind IN ('draft','interpretation')" in str(
        CreateTable(migrated).compile(dialect=postgresql.dialect())
    )
    migration62 = import_module("migrations.versions.0062_analysis_compute_ai")
    assert migration62.down_revision == "0061_analysis_compute"

    def drop_constraint(name, table, **kwargs):
        target = tables[table]
        target.constraints.remove(next(c for c in target.constraints if c.name == name))

    def create_constraint(name, table, condition):
        tables[table].append_constraint(sa.CheckConstraint(condition, name=name))

    monkeypatch.setattr(migration62.op, "drop_constraint", drop_constraint)
    monkeypatch.setattr(migration62.op, "create_check_constraint", create_constraint)
    migration62.upgrade()
    assert constraint_signature(migrated) == constraint_signature(declared)
    assert indexes == {
        index.name: (declared.name, tuple(index.columns.keys()))
        for index in declared.indexes
    }
    assert str(CreateTable(migrated).compile(dialect=postgresql.dialect()))
    assert set(additions) == {"analysis_previews", "analysis_runs"}
    for model in (AnalysisPreview, AnalysisRun):
        column = additions[model.__tablename__]
        assert column.name == "ai_provenance"
        assert column_signature(column) == column_signature(
            model.__table__.c.ai_provenance
        )
        assert column.server_default.arg == "{}"
    source = Path(migration.__file__).read_text(encoding="utf-8")
    assert "import_models" not in source
    assert "Base.metadata" not in source


def test_downgrade_only_removes_0060_request_table_and_provenance_columns(monkeypatch):
    migration = import_module("migrations.versions.0060_analysis_ai")
    calls = []
    monkeypatch.setattr(
        migration.op,
        "drop_column",
        lambda table, column: calls.append(("column", table, column)),
    )
    monkeypatch.setattr(
        migration.op, "drop_table", lambda table: calls.append(("table", table))
    )
    migration.downgrade()
    assert calls == [
        ("column", "analysis_runs", "ai_provenance"),
        ("column", "analysis_previews", "ai_provenance"),
        ("table", "analysis_ai_requests"),
    ]


@pytest.mark.parametrize("has_drafts", [True, False])
def test_0062_downgrade_locks_and_preserves_advanced_paid_history(
    monkeypatch, has_drafts
):
    migration = import_module("migrations.versions.0062_analysis_compute_ai")
    calls = []

    class Connection:
        def execute(self, statement):
            calls.append(str(statement))

        def scalar(self, statement):
            calls.append(str(statement))
            return has_drafts

    monkeypatch.setattr(migration.op, "get_bind", Connection)
    monkeypatch.setattr(migration, "_replace", lambda *args: calls.append(args))
    if has_drafts:
        with pytest.raises(RuntimeError, match="advanced analysis AI drafts"):
            migration.downgrade()
        assert len(calls) == 2
    else:
        migration.downgrade()
        assert calls[2][0] == "kind IN ('draft','interpretation')"
    assert "ACCESS EXCLUSIVE" in calls[0]
    assert "compute_draft" in calls[1]
    assert "input_context->>'result_kind' = 'compute'" in calls[1]
    assert "run.engine_version = 'airalogy.compute.analysis.v1'" in calls[1]
    source = Path(migration.__file__).read_text(encoding="utf-8")
    assert "Base.metadata" not in source and "import_models" not in source
