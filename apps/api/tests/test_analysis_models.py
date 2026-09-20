"""Persistence contracts for private, reproducible Record analysis."""

from importlib import import_module
from pathlib import Path
from unittest.mock import Mock

import pytest
import sqlalchemy as sa
from app.models.analysis import (
    AnalysisPipeline,
    AnalysisPipelineRevision,
    AnalysisPreview,
    AnalysisRun,
    AnalysisRunStatus,
)
from migrations.model_registry import MODEL_MODULES, import_models
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

MODELS = (AnalysisPipeline, AnalysisPipelineRevision, AnalysisRun, AnalysisPreview)


@pytest.fixture(scope="module", autouse=True)
def registered_models():
    import_models()


def ddl(model):
    return str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))


def test_analysis_models_are_registered_as_four_separate_assets():
    assert "app.models.analysis" in MODEL_MODULES
    migration = import_module("migrations.versions.0059_analysis")
    assert migration.revision == "0059_analysis"
    assert migration.down_revision == "0058_optional_embeddings"
    assert migration.TABLE_NAMES == tuple(model.__tablename__ for model in MODELS)
    assert migration.branch_labels is None
    assert migration.depends_on is None


@pytest.mark.parametrize("model", MODELS)
def test_analysis_identity_and_timestamps_follow_repository_contract(model):
    table = model.__table__
    assert table.c.id.primary_key
    assert str(table.c.id.server_default.arg) == "uuid_generate_v7()"
    assert not table.c.created_by_user_id.nullable
    assert table.c.created_at.type.timezone
    assert not table.c.created_at.nullable
    assert str(table.c.created_at.server_default.arg) == "now()"
    for column in table.c:
        if isinstance(column.type, sa.DateTime):
            assert column.type.timezone


def test_pipeline_revision_identity_does_not_depend_on_a_run():
    pipeline_sql = ddl(AnalysisPipeline)
    revision_sql = ddl(AnalysisPipelineRevision)
    assert "CHECK (current_revision >= 1)" in pipeline_sql
    assert "UNIQUE (pipeline_id, revision)" in revision_sql
    assert "CHECK (revision >= 1)" in revision_sql
    assert "run_id" not in AnalysisPipelineRevision.__table__.c
    assert not AnalysisPipelineRevision.__table__.c.provenance.nullable
    assert AnalysisPipelineRevision.__table__.c.provenance.default.is_callable
    assert not AnalysisPipelineRevision.__table__.c.source_selection.nullable
    assert AnalysisPipelineRevision.__table__.c.source_selection.default.is_callable
    assert {
        foreign_key.target_fullname
        for foreign_key in AnalysisPipelineRevision.__table__.foreign_keys
    } == {
        "analysis_pipelines.id",
        "users.id",
    }


def test_private_analysis_scope_does_not_create_visibility_or_implicit_sharing():
    for model in (AnalysisPipeline, AnalysisRun, AnalysisPreview):
        columns = model.__table__.c
        assert not columns.project_id.nullable
        assert columns.protocol_id.nullable
        assert not columns.source_scope.nullable
        assert columns.source_scope.server_default.arg == "protocol"
        assert "source_scope = 'protocol' AND protocol_id IS NOT NULL" in ddl(model)
        assert "source_scope = 'project' AND protocol_id IS NULL" in ddl(model)
        assert not columns.created_by_user_id.nullable
        assert "visibility" not in columns
        assert "public" not in columns


def test_run_has_owner_bound_idempotency_real_snapshot_and_execution_state():
    run_sql = ddl(AnalysisRun)
    assert "UNIQUE (created_by_user_id, client_idempotency_key)" in run_sql
    assert AnalysisRun.__table__.c.client_idempotency_key.type.length == 128
    assert not AnalysisRun.__table__.c.source_snapshot.nullable
    assert not AnalysisRun.__table__.c.source_selection.nullable
    assert not AnalysisRun.__table__.c.engine_version.nullable
    assert AnalysisRun.__table__.c.status.default.arg == "pending"
    assert {item.value for item in AnalysisRunStatus} == {
        "pending",
        "running",
        "succeeded",
        "failed",
        "cancelled",
    }
    assert (
        "CHECK (status IN ('pending','running','succeeded','failed','cancelled'))"
        in run_sql
    )
    assert "CHECK (rerun_of_id IS NULL OR rerun_of_id <> id)" in run_sql
    assert (
        "FOREIGN KEY(job_id) REFERENCES persistent_jobs (id) ON DELETE SET NULL"
        in run_sql
    )


def test_results_are_nullable_sql_values_and_paired_with_a_digest():
    result = AnalysisRun.__table__.c.result
    assert result.nullable
    assert result.type.none_as_null
    assert "CHECK ((result IS NULL) = (result_digest IS NULL))" in ddl(AnalysisRun)
    assert "result_digest IS NULL OR result_digest ~ '^[0-9a-f]{64}$'" in ddl(
        AnalysisRun
    )


def test_preview_is_expiring_confirmation_not_a_snapshot_or_enqueued_job():
    table = AnalysisPreview.__table__
    assert not table.c.expires_at.nullable
    assert "source_snapshot" not in table.c
    assert "result" not in table.c
    assert "job_id" not in table.c
    assert "status" not in table.c
    assert {index.name for index in table.indexes} >= {
        "ix_analysis_previews_owner_expires"
    }


def _column_signature(column):
    return (
        str(column.type.compile(dialect=postgresql.dialect())),
        column.nullable,
        column.primary_key,
        str(column.server_default.arg) if column.server_default else None,
    )


def _constraint_signature(table):
    constraints = set()
    for constraint in table.constraints:
        if isinstance(constraint, sa.CheckConstraint):
            constraints.add(("check", constraint.name, str(constraint.sqltext)))
        elif isinstance(constraint, sa.UniqueConstraint):
            constraints.add(
                ("unique", constraint.name, tuple(constraint.columns.keys()))
            )
        elif isinstance(constraint, sa.ForeignKeyConstraint):
            constraints.add(
                (
                    "foreign_key",
                    tuple(constraint.columns.keys()),
                    tuple(element.target_fullname for element in constraint.elements),
                    constraint.ondelete,
                )
            )
    return constraints


def test_frozen_migration_matches_models_columns_constraints_and_indexes(monkeypatch):
    migration = import_module("migrations.versions.0059_analysis")
    metadata = sa.MetaData()
    for name in ("projects", "protocols", "users", "persistent_jobs"):
        sa.Table(name, metadata, sa.Column("id", sa.UUID(), primary_key=True))
    tables = {}
    indexes = {}

    def create_table(name, *columns_and_constraints):
        tables[name] = sa.Table(name, metadata, *columns_and_constraints)

    def create_index(name, table_name, columns):
        indexes[name] = (table_name, tuple(columns))

    monkeypatch.setattr(migration.op, "create_table", create_table)
    monkeypatch.setattr(migration.op, "create_index", create_index)
    migration.upgrade()
    assert tuple(tables) == migration.TABLE_NAMES
    for model in MODELS:
        declared = model.__table__
        migrated = tables[model.__tablename__]
        assert {column.name: _column_signature(column) for column in migrated.c} == {
            column.name: (
                (_column_signature(column)[0], False, *_column_signature(column)[2:])
                if column.name == "protocol_id" else _column_signature(column)
            )
            for column in declared.c
            # Introduced by frozen revision 0060 and verified by its own tests.
            if column.name != "source_scope" and not (
                declared.name in {"analysis_previews", "analysis_runs"}
                and column.name == "ai_provenance"
            )
        }
        assert _constraint_signature(migrated) == {
            item for item in _constraint_signature(declared)
            # Added in 0070, after legacy Protocol-only assets existed.
            if not (item[0] == "check" and item[1].endswith("_source_scope"))
        }
        # Compiling the migration also resolves every internal/external FK.
        assert str(CreateTable(migrated).compile(dialect=postgresql.dialect()))
        declared_indexes = {
            index.name: (declared.name, tuple(index.columns.keys()))
            for index in declared.indexes
        }
        assert {
            name: signature
            for name, signature in indexes.items()
            if signature[0] == declared.name
        } == declared_indexes
    source = Path(migration.__file__).read_text(encoding="utf-8")
    assert "import_models" not in source
    assert "Base.metadata" not in source


def test_downgrade_removes_only_analysis_tables_in_reverse_dependency_order(
    monkeypatch,
):
    migration = import_module("migrations.versions.0059_analysis")
    drop_table = Mock()
    monkeypatch.setattr(migration.op, "drop_table", drop_table)
    migration.downgrade()
    assert [call.args[0] for call in drop_table.call_args_list] == list(
        reversed(migration.TABLE_NAMES)
    )
