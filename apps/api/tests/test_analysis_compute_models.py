"""Frozen schema contracts for analysis approval and shared Compute execution."""

from importlib import import_module
from pathlib import Path
from unittest.mock import Mock

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.analysis import AnalysisRun
from app.models.analysis_compute import (
    AnalysisCompute,
    AnalysisComputeApprovalState,
    AnalysisComputeEvent,
    AnalysisComputeInputFile,
)
from app.models.research_execution import ResearchComputeJob, ResearchComputeJobInput
from migrations.model_registry import MODEL_MODULES, import_models

JOB_CONTEXT = (
    "(action_id IS NOT NULL AND analysis_run_id IS NULL) OR "
    "(action_id IS NULL AND analysis_run_id IS NOT NULL)"
)
INPUT_SOURCE = (
    "(data_asset_id IS NOT NULL AND data_asset_version_id IS NOT NULL "
    "AND analysis_run_id IS NULL) OR "
    "(data_asset_id IS NULL AND data_asset_version_id IS NULL "
    "AND analysis_run_id IS NOT NULL)"
)


@pytest.fixture(scope="module", autouse=True)
def registered_models():
    import_models()


def ddl(model):
    return str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))


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


def index_signature(table):
    return {
        (index.name, tuple(index.columns.keys()), bool(index.unique))
        for index in table.indexes
    }


def test_analysis_compute_registration_and_linear_migration():
    assert "app.models.analysis_compute" in MODEL_MODULES
    migration = import_module("migrations.versions.0061_analysis_compute")
    assert migration.revision == "0061_analysis_compute"
    assert migration.down_revision == "0060_analysis_ai"
    assert migration.TABLE_NAMES == ("analysis_computations", "analysis_compute_events")
    assert migration.branch_labels is None and migration.depends_on is None


def test_compute_job_has_exactly_one_unique_execution_context():
    table = ResearchComputeJob.__table__
    assert table.c.action_id.nullable and table.c.analysis_run_id.nullable
    assert JOB_CONTEXT in ddl(ResearchComputeJob)
    assert (
        next(iter(table.c.analysis_run_id.foreign_keys)).target_fullname
        == "analysis_runs.id"
    )
    assert next(iter(table.c.analysis_run_id.foreign_keys)).ondelete == "RESTRICT"
    assert (
        "ix_research_compute_jobs_analysis_run_id",
        ("analysis_run_id",),
        True,
    ) in index_signature(table)
    assert "UNIQUE (action_id)" in ddl(ResearchComputeJob)
    # Sharing the runner must not weaken code/environment pinning or leases.
    assert not table.c.source_code.nullable and not table.c.source_sha256.nullable
    assert "length(source_sha256) = 64" in ddl(ResearchComputeJob)
    assert not table.c.compute_environment_revision_id.nullable
    assert table.c.lease_expires_at.type.timezone
    assert "source_code" in ResearchComputeJob.json_exclude_fields
    assert "lease_token_digest" in ResearchComputeJob.json_exclude_fields


def test_compute_input_is_one_asset_revision_or_one_sealed_analysis_snapshot():
    table = ResearchComputeJobInput.__table__
    assert INPUT_SOURCE in ddl(ResearchComputeJobInput)
    for name in ("data_asset_id", "data_asset_version_id", "analysis_run_id"):
        assert table.c[name].nullable
        assert next(iter(table.c[name].foreign_keys)).ondelete == "RESTRICT"
    assert (
        "ix_research_compute_job_inputs_analysis_run_id",
        ("analysis_run_id",),
        False,
    ) in index_signature(table)
    assert not table.c.compute_job_id.nullable and not table.c.mount_name.nullable
    assert "source_snapshot" not in table.c
    assert not AnalysisRun.__table__.c.source_snapshot.nullable
    assert not AnalysisRun.__table__.c.source_digest.nullable
    assert "source_digest ~ '^[0-9a-f]{64}$'" in ddl(AnalysisRun)


def test_approval_is_explicit_revisioned_and_does_not_grant_sharing():
    table = AnalysisCompute.__table__
    assert {state.value for state in AnalysisComputeApprovalState} == {
        "pending",
        "approved",
        "rejected",
        "cancelled",
    }
    assert table.c.analysis_run_id.primary_key
    assert "id" not in table.c and "source_snapshot" not in table.c
    assert table.c.approval_state.default.arg == "pending"
    assert table.c.approval_state.server_default.arg == "pending"
    assert table.c.approval_revision.default.arg == 1
    assert "approval_revision >= 1" in ddl(AnalysisCompute)
    assert "approval_state IN ('pending','approved','rejected','cancelled')" in ddl(
        AnalysisCompute
    )
    assert "contract_digest ~ '^[0-9a-f]{64}$'" in ddl(AnalysisCompute)
    assert not table.c.approver_user_id.nullable
    assert next(iter(table.c.approver_user_id.foreign_keys)).ondelete == "RESTRICT"
    assert table.c.decided_by_user_id.nullable
    assert table.c.decision_reason.default.arg == ""
    assert "visibility" not in table.c and "public" not in table.c


def test_budget_is_an_optional_finite_nonnegative_amount_currency_pair():
    table = AnalysisCompute.__table__
    assert table.c.max_cost.nullable and table.c.budget_currency.nullable
    assert table.c.max_cost.type.precision == 38 and table.c.max_cost.type.scale == 18
    assert table.c.budget_currency.type.length == 3
    table_sql = ddl(AnalysisCompute)
    assert "max_cost IS NULL AND budget_currency IS NULL" in table_sql
    assert "max_cost IS NOT NULL AND max_cost >= 0" in table_sql
    assert "max_cost <> 'NaN'::numeric" in table_sql
    assert "budget_currency IS NOT NULL" in table_sql
    assert "budget_currency ~ '^[A-Z]{3}$'" in table_sql


def test_approval_timestamps_and_indexes_support_pending_recovery():
    table = AnalysisCompute.__table__
    for name in ("requested_at", "deadline_at", "decided_at"):
        assert table.c[name].type.timezone
    assert not table.c.requested_at.nullable
    assert table.c.deadline_at.nullable and table.c.decided_at.nullable
    assert str(table.c.requested_at.server_default.arg) == "now()"
    assert index_signature(table) == {
        (
            "ix_analysis_computations_approver_state",
            ("approver_user_id", "approval_state"),
            False,
        ),
        (
            "ix_analysis_computations_state_deadline",
            ("approval_state", "deadline_at"),
            False,
        ),
    }


def test_events_are_idempotent_per_analysis_and_retain_nullable_actor_history():
    table = AnalysisComputeEvent.__table__
    assert table.c.id.primary_key
    assert str(table.c.id.server_default.arg) == "uuid_generate_v7()"
    assert not table.c.analysis_run_id.nullable
    assert "UNIQUE (analysis_run_id, idempotency_key)" in ddl(AnalysisComputeEvent)
    assert table.c.idempotency_key.type.length == 128
    assert table.c.kind.type.length == 64
    assert not table.c.payload.nullable and table.c.payload.default.is_callable
    assert table.c.payload.server_default.arg == "{}"
    assert table.c.actor_user_id.nullable
    assert next(iter(table.c.actor_user_id.foreign_keys)).ondelete == "SET NULL"
    assert table.c.created_at.type.timezone
    assert "updated_at" not in table.c


class MigrationCapture:
    """Capture real frozen Alembic operations without opening a database."""

    def __init__(self, monkeypatch):
        self.metadata = sa.MetaData()
        for name in (
            "research_actions",
            "research_compute_environments",
            "research_compute_environment_revisions",
            "research_compute_runners",
            "users",
            "data_assets",
            "data_asset_versions",
        ):
            sa.Table(name, self.metadata, sa.Column("id", sa.UUID(), primary_key=True))
        self.created_tables = []
        self.columns_added = []
        self.columns_altered = []
        migration = import_module("migrations.versions.0061_analysis_compute")
        monkeypatch.setattr(migration.op, "create_table", self.create_table)
        monkeypatch.setattr(migration.op, "create_index", self.create_index)
        monkeypatch.setattr(migration.op, "add_column", self.add_column)
        monkeypatch.setattr(migration.op, "alter_column", self.alter_column)
        monkeypatch.setattr(migration.op, "create_check_constraint", self.create_check)

    def create_table(self, name, *columns_and_constraints):
        table = sa.Table(name, self.metadata, *columns_and_constraints)
        # A premature FK to analysis_runs would fail here, just as at revision 0032.
        str(CreateTable(table).compile(dialect=postgresql.dialect()))
        self.created_tables.append(name)

    def create_index(self, name, table, columns, unique=False):
        sa.Index(
            name,
            *(self.metadata.tables[table].c[column] for column in columns),
            unique=unique,
        )

    def add_column(self, table, column):
        self.metadata.tables[table].append_column(column)
        self.columns_added.append((table, column.name))

    def alter_column(self, table, column, *, existing_type, nullable):
        assert isinstance(existing_type, sa.UUID)
        self.metadata.tables[table].c[column].nullable = nullable
        self.columns_altered.append((table, column, nullable))

    def create_check(self, name, table, condition):
        self.metadata.tables[table].append_constraint(
            sa.CheckConstraint(condition, name=name)
        )


def test_frozen_0032_does_not_anticipate_later_output_or_analysis_tables(monkeypatch):
    capture = MigrationCapture(monkeypatch)
    migration = import_module("migrations.versions.0032_research_compute_jobs")
    migration.upgrade()
    assert capture.created_tables == list(migration.TABLE_NAMES)
    assert migration.FROZEN_MODEL_COMMIT == "154cc8d"
    assert "analysis_runs" not in capture.metadata.tables
    for model in (ResearchComputeJob, ResearchComputeJobInput):
        historical = capture.metadata.tables[model.__tablename__]
        excluded = {"analysis_run_id", "output_manifest"}
        assert set(historical.c.keys()) == set(model.__table__.c.keys()) - excluded
        assert not any(
            key.target_fullname.startswith("analysis_")
            for key in historical.foreign_keys
        )
        assert not any("analysis_run_id" in str(c) for c in historical.constraints)
    assert not capture.metadata.tables["research_compute_jobs"].c.action_id.nullable
    inputs = capture.metadata.tables["research_compute_job_inputs"]
    assert (
        not inputs.c.data_asset_id.nullable
        and not inputs.c.data_asset_version_id.nullable
    )
    assert capture.columns_added == [] and capture.columns_altered == []
    source = Path(migration.__file__).read_text(encoding="utf-8")
    assert "import_models" not in source and "Base.metadata" not in source


def test_frozen_0061_and_historical_compute_columns_match_current_models(monkeypatch):
    capture = MigrationCapture(monkeypatch)
    import_module("migrations.versions.0032_research_compute_jobs").upgrade()
    # 0033 owns this addition; 0059 creates the referenced analysis table.
    capture.add_column(
        "research_compute_jobs",
        sa.Column(
            "output_manifest",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    sa.Table(
        "analysis_runs", capture.metadata, sa.Column("id", sa.UUID(), primary_key=True)
    )
    migration = import_module("migrations.versions.0061_analysis_compute")
    migration.upgrade()
    assert capture.created_tables[-2:] == list(migration.TABLE_NAMES)
    assert capture.columns_added[-2:] == [
        ("research_compute_jobs", "analysis_run_id"),
        ("research_compute_job_inputs", "analysis_run_id"),
    ]
    assert capture.columns_altered == [
        ("research_compute_jobs", "action_id", True),
        ("research_compute_job_inputs", "data_asset_id", True),
        ("research_compute_job_inputs", "data_asset_version_id", True),
    ]
    for model in (
        AnalysisCompute,
        AnalysisComputeEvent,
        ResearchComputeJob,
        ResearchComputeJobInput,
    ):
        declared = model.__table__
        migrated = capture.metadata.tables[declared.name]
        later_columns = {"input_file_manifest"} if model is AnalysisCompute else set()
        assert set(migrated.c.keys()) == set(declared.c.keys()) - later_columns
        for column in declared.c:
            if column.name in later_columns:
                continue
            actual, expected = (
                column_signature(migrated.c[column.name]),
                column_signature(column),
            )
            if column.name == "output_manifest":
                # The original 0033 adds a DB default; the model has a Python default.
                assert actual[:3] == expected[:3]
                assert actual[3] == "'[]'::json"
            else:
                assert actual == expected, (declared.name, column.name)
        assert constraint_signature(migrated) == constraint_signature(declared)
        assert index_signature(migrated) == index_signature(declared)
        assert str(CreateTable(migrated).compile(dialect=postgresql.dialect()))
    source = Path(migration.__file__).read_text(encoding="utf-8")
    assert "import_models" not in source and "Base.metadata" not in source
    # 0069, not the frozen 0061, owns private attachment receipt persistence.
    for name in ("airalogy_files", "research_file_blobs"):
        sa.Table(name, capture.metadata, sa.Column("id", sa.UUID(), primary_key=True))
    sa.Table(
        "records", capture.metadata,
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
    )
    attachments = import_module("migrations.versions.0069_analysis_compute_input_files")
    monkeypatch.setattr(attachments.op, "execute", Mock())
    attachments.upgrade()
    assert capture.columns_added[-1] == ("analysis_computations", "input_file_manifest")
    for model in (AnalysisCompute, AnalysisComputeInputFile):
        declared = model.__table__
        migrated = capture.metadata.tables[declared.name]
        assert set(migrated.c.keys()) == set(declared.c.keys())
        for column in declared.c:
            assert column_signature(migrated.c[column.name]) == column_signature(column)
        assert constraint_signature(migrated) == constraint_signature(declared)
        assert index_signature(migrated) == index_signature(declared)


@pytest.mark.parametrize("has_analysis_assets", [False, True])
def test_downgrade_refuses_assets_before_ddl_and_never_deletes_them(
    monkeypatch, has_analysis_assets
):
    migration = import_module("migrations.versions.0061_analysis_compute")
    calls = []

    def guard(statement):
        sql = str(statement)
        calls.append(("guard", sql))
        assert "RAISE EXCEPTION" in sql
        assert "IN ACCESS EXCLUSIVE MODE" in sql
        assert sql.index("LOCK TABLE") < sql.index("IF EXISTS")
        for table in (
            "research_compute_jobs",
            "research_compute_job_inputs",
            "analysis_computations",
            "analysis_compute_events",
        ):
            assert f"SELECT 1 FROM {table}" in sql
        assert "DELETE FROM" not in sql
        if has_analysis_assets:
            raise RuntimeError(
                "Cannot downgrade while analysis computation assets exist"
            )

    monkeypatch.setattr(migration.op, "execute", guard)
    for name in (
        "drop_constraint",
        "drop_index",
        "drop_column",
        "alter_column",
        "drop_table",
    ):
        monkeypatch.setattr(
            migration.op,
            name,
            Mock(
                side_effect=lambda *args, operation=name, **kwargs: calls.append(
                    (operation, args, kwargs)
                )
            ),
        )
    if has_analysis_assets:
        with pytest.raises(RuntimeError, match="Cannot downgrade"):
            migration.downgrade()
        assert len(calls) == 1
    else:
        migration.downgrade()
        assert calls[0][0] == "guard"
        assert [call[1][0] for call in calls if call[0] == "drop_table"] == [
            "analysis_compute_events",
            "analysis_computations",
        ]
        altered = [call for call in calls if call[0] == "alter_column"]
        assert len(altered) == 3 and all(
            call[2]["nullable"] is False for call in altered
        )
