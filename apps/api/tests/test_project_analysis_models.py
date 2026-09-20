"""Frozen scope migration, source FKs and separate immutable interpretation."""

from importlib import import_module
from pathlib import Path
from unittest.mock import Mock

import pytest
import sqlalchemy as sa
from app.models.analysis import (
    AnalysisInterpretationRevision,
    AnalysisPipeline,
    AnalysisPreview,
    AnalysisProjectInput,
    AnalysisRun,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from tests.test_analysis_models import _column_signature, _constraint_signature


def test_frozen_0070_models_and_existing_scope_changes(monkeypatch):
    migration = import_module("migrations.versions.0070_project_analysis")
    assert migration.revision == "0070_project_analysis"
    assert migration.down_revision == "0069_analysis_input_files"
    metadata = sa.MetaData()
    for name in ("analysis_runs", "protocols", "users"):
        sa.Table(name, metadata, sa.Column("id", sa.UUID(), primary_key=True))
    tables = {}
    indexes = {}

    def create_table(name, *columns):
        tables[name] = sa.Table(name, metadata, *columns)

    def create_index(name, table, columns):
        indexes[name] = (table, tuple(columns))

    added, altered, constraints, execute = Mock(), Mock(), Mock(), Mock()
    monkeypatch.setattr(migration.op, "create_table", create_table)
    monkeypatch.setattr(migration.op, "create_index", create_index)
    monkeypatch.setattr(migration.op, "add_column", added)
    monkeypatch.setattr(migration.op, "alter_column", altered)
    monkeypatch.setattr(migration.op, "create_check_constraint", constraints)
    monkeypatch.setattr(migration.op, "execute", execute)
    migration.upgrade()
    assert tuple(tables) == migration.TABLE_NAMES
    for model in (AnalysisProjectInput, AnalysisInterpretationRevision):
        frozen, current = tables[model.__tablename__], model.__table__
        assert {c.name: _column_signature(c) for c in frozen.c} == {
            c.name: _column_signature(c) for c in current.c
        }
        assert _constraint_signature(frozen) == _constraint_signature(current)
        assert str(CreateTable(frozen).compile(dialect=postgresql.dialect()))
        assert {
            name: spec for name, spec in indexes.items() if spec[0] == current.name
        } == {
            index.name: (current.name, tuple(index.columns.keys()))
            for index in current.indexes
        }
    for model, call, alteration, check in zip(
        (AnalysisPipeline, AnalysisRun, AnalysisPreview),
        added.call_args_list,
        altered.call_args_list,
        constraints.call_args_list,
        strict=True,
    ):
        assert call.args[0] == model.__tablename__
        assert _column_signature(call.args[1]) == _column_signature(
            model.__table__.c.source_scope
        )
        assert alteration.args == (model.__tablename__, "protocol_id")
        assert alteration.kwargs["nullable"] is True
        assert check.args[1:] == (model.__tablename__, migration.SCOPE_CHECK)
    sql = "\n".join(str(call.args[0]) for call in execute.call_args_list)
    assert "Finished Project analysis history is immutable" in sql
    assert "Project analysis execution contract is immutable" in sql
    assert "immutable_analysis_interpretation_revisions" in sql
    source = Path(migration.__file__).read_text()
    assert "import_models" not in source and "Base.metadata" not in source


@pytest.mark.parametrize("has_assets", [True, False])
def test_downgrade_locks_and_never_discards_project_history(monkeypatch, has_assets):
    migration = import_module("migrations.versions.0070_project_analysis")
    connection = Mock()
    connection.scalar.return_value = has_assets
    drop = Mock()
    monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
    monkeypatch.setattr(migration.op, "drop_table", drop)
    for name in ("execute", "drop_constraint", "alter_column", "drop_column"):
        monkeypatch.setattr(migration.op, name, Mock())
    if has_assets:
        with pytest.raises(RuntimeError, match="Cannot downgrade"):
            migration.downgrade()
        drop.assert_not_called()
    else:
        migration.downgrade()
        assert [call.args[0] for call in drop.call_args_list] == list(
            reversed(migration.TABLE_NAMES)
        )
    assert "ACCESS EXCLUSIVE MODE" in str(connection.execute.call_args.args[0])
    assert "analysis_interpretation_revisions" in str(
        connection.scalar.call_args.args[0]
    )
