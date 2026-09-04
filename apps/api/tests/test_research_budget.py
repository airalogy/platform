import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.main import app
from app.models.research import ResearchTask
from app.models.research_execution import ResearchBudgetEntry
from app.routers.research_budget import OperationalLimitsDraft, _limit_preview
from app.routers.research_tasks import ResearchTaskDraft
from app.services.research_budget import (
    ResearchBudgetError,
    project_budget_change,
    project_operational_limit_amendment,
    reached_operational_limit,
    research_budget_snapshot,
)


def compile_table(model) -> str:
    return str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))


def test_budget_schema_is_immutable_and_migration_follows_resource_reservations():
    task_ddl = compile_table(ResearchTask)
    ledger_ddl = compile_table(ResearchBudgetEntry)
    migration = import_module("migrations.versions.0018_research_operational_limits")

    assert "deadline_at" in task_ddl
    assert "budget_limit" in task_ddl
    assert "budget_currency" in task_ddl
    assert "ck_research_tasks_budget_pair" in task_ddl
    assert "UNIQUE (task_id, idempotency_key)" in ledger_ddl
    assert "CHECK (amount > 0)" in ledger_ddl
    assert "ck_research_budget_entry_kind" in ledger_ddl
    assert "ck_research_budget_entry_currency" in ledger_ddl
    assert migration.down_revision == "0017_research_resource_reservations"


def test_operational_limit_migration_handles_fresh_and_upgraded_databases(
    monkeypatch,
):
    migration = import_module("migrations.versions.0018_research_operational_limits")
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(migration.op, "get_bind", lambda: object())
    monkeypatch.setattr(migration, "import_models", lambda: None)
    monkeypatch.setattr(
        migration.op,
        "add_column",
        lambda _table, column: calls.append(("column", column.name)),
    )
    monkeypatch.setattr(
        migration.op,
        "create_check_constraint",
        lambda name, *_args, **_kwargs: calls.append(("constraint", name)),
    )
    monkeypatch.setattr(
        migration.op,
        "drop_constraint",
        lambda name, *_args, **_kwargs: calls.append(("drop_constraint", name)),
    )
    monkeypatch.setattr(
        migration.op,
        "drop_column",
        lambda _table, name: calls.append(("drop_column", name)),
    )
    monkeypatch.setattr(
        migration.op,
        "execute",
        lambda statement: calls.append(("execute", str(statement))),
    )
    monkeypatch.setattr(
        ResearchBudgetEntry.__table__,
        "create",
        lambda *_args, **_kwargs: calls.append(("table", "create")),
    )
    monkeypatch.setattr(
        ResearchBudgetEntry.__table__,
        "drop",
        lambda *_args, **_kwargs: calls.append(("table", "drop")),
    )

    class Inspector:
        def __init__(self, columns: set[str], constraints: set[str]):
            self.columns = columns
            self.constraints = constraints

        def get_columns(self, _table: str):
            return [{"name": name} for name in self.columns]

        def get_check_constraints(self, _table: str):
            return [{"name": name} for name in self.constraints]

    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: Inspector(set(), set()))
    migration.upgrade()
    assert {
        value for kind, value in calls if kind == "column"
    } == migration.ADDED_COLUMNS
    assert ("constraint", migration.BUDGET_CONSTRAINT) in calls

    calls.clear()
    monkeypatch.setattr(
        migration.sa,
        "inspect",
        lambda _bind: Inspector(migration.ADDED_COLUMNS, {migration.BUDGET_CONSTRAINT}),
    )
    migration.upgrade()
    assert not [item for item in calls if item[0] in {"column", "constraint"}]
    assert ("table", "create") in calls

    calls.clear()
    migration.downgrade()
    assert ("table", "drop") in calls
    assert any(
        kind == "execute" and "DROP TRIGGER IF EXISTS" in statement
        for kind, statement in calls
    )
    assert ("drop_constraint", migration.BUDGET_CONSTRAINT) in calls
    assert {
        value for kind, value in calls if kind == "drop_column"
    } == migration.ADDED_COLUMNS


def test_task_budget_and_deadline_are_validated_together():
    payload = {
        "project_id": uuid4(),
        "title": "Bounded study",
        "goal": "Answer a question",
        "success_criteria": ["Measured result"],
    }
    valid = ResearchTaskDraft(
        **payload,
        budget_limit="100",
        budget_currency=" usd ",
        deadline_at=datetime.now(UTC) + timedelta(days=1),
    )
    assert valid.budget_currency == "USD"

    with pytest.raises(ValidationError, match="provided together"):
        ResearchTaskDraft(**payload, budget_limit="100")
    with pytest.raises(ValidationError, match="future"):
        ResearchTaskDraft(
            **payload, deadline_at=datetime.now(UTC) - timedelta(seconds=1)
        )


def test_budget_projection_fails_closed_at_limit_and_negative_balances():
    task = SimpleNamespace(budget_limit=Decimal(100), budget_currency="USD")
    current = {"reserved": "20", "actual": "30"}

    projected = project_budget_change(
        task=task,
        snapshot=current,
        kind="reserve",
        amount=Decimal(40),
        currency="USD",
    )
    assert projected["committed"] == "90"
    assert projected["remaining"] == "10"

    with pytest.raises(ResearchBudgetError, match="exceed"):
        project_budget_change(
            task=task,
            snapshot=current,
            kind="expense",
            amount=Decimal(60),
            currency="USD",
        )
    with pytest.raises(ResearchBudgetError, match="reserved amount"):
        project_budget_change(
            task=task,
            snapshot=current,
            kind="release",
            amount=Decimal(21),
            currency="USD",
        )


def test_budget_snapshot_separates_reserved_and_actual_cost():
    entries = [
        SimpleNamespace(kind="reserve", amount=Decimal(30), as_dict=dict),
        SimpleNamespace(kind="release", amount=Decimal(10), as_dict=dict),
        SimpleNamespace(kind="expense", amount=Decimal(15), as_dict=dict),
    ]
    db_session = SimpleNamespace(
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: entries))
    )
    task = SimpleNamespace(id=uuid4(), budget_limit=Decimal(100), budget_currency="USD")

    snapshot = asyncio.run(research_budget_snapshot(db_session, task=task))

    assert snapshot["reserved"] == "20"
    assert snapshot["actual"] == "15"
    assert snapshot["committed"] == "35"
    assert snapshot["remaining"] == "65"


def test_deadline_is_a_runtime_stop_boundary():
    task = SimpleNamespace(
        deadline_at=datetime.now(UTC) - timedelta(seconds=1),
        budget_limit=None,
    )
    result = asyncio.run(reached_operational_limit(SimpleNamespace(), task=task))

    assert result[0] == "time"
    assert "deadline_at" in result[1]


def test_operational_limit_amendment_preserves_single_currency_ledger():
    now = datetime.now(UTC)
    task = SimpleNamespace(
        deadline_at=now + timedelta(hours=1),
        budget_limit=Decimal(100),
        budget_currency="USD",
    )
    snapshot = {
        "committed": "75",
        "entries": [{"id": str(uuid4())}],
    }

    projected = project_operational_limit_amendment(
        task=task,
        snapshot=snapshot,
        deadline_at=now + timedelta(days=2),
        budget_limit=Decimal(150),
        budget_currency="usd",
        now=now,
    )

    assert projected["budget_limit"] == "150"
    assert projected["budget_currency"] == "USD"
    assert projected["budget_remaining"] == "75"
    assert projected["resume_eligible"] is True

    with pytest.raises(ResearchBudgetError, match="cannot be removed"):
        project_operational_limit_amendment(
            task=task,
            snapshot=snapshot,
            deadline_at=now + timedelta(days=2),
            budget_limit=None,
            budget_currency=None,
            now=now,
        )
    with pytest.raises(ResearchBudgetError, match="change currency"):
        project_operational_limit_amendment(
            task=task,
            snapshot=snapshot,
            deadline_at=now + timedelta(days=2),
            budget_limit=Decimal(150),
            budget_currency="EUR",
            now=now,
        )


def test_operational_limit_amendment_rejects_stale_boundaries_and_noops():
    now = datetime.now(UTC)
    deadline = now + timedelta(days=1)
    task = SimpleNamespace(
        deadline_at=deadline,
        budget_limit=Decimal(100),
        budget_currency="USD",
    )
    snapshot = {"committed": "80", "entries": []}

    with pytest.raises(ResearchBudgetError, match="must exceed"):
        project_operational_limit_amendment(
            task=task,
            snapshot=snapshot,
            deadline_at=deadline,
            budget_limit=Decimal(80),
            budget_currency="USD",
            now=now,
        )
    with pytest.raises(ResearchBudgetError, match="future"):
        project_operational_limit_amendment(
            task=task,
            snapshot=snapshot,
            deadline_at=now - timedelta(seconds=1),
            budget_limit=Decimal(100),
            budget_currency="USD",
            now=now,
        )
    with pytest.raises(ResearchBudgetError, match="have not changed"):
        project_operational_limit_amendment(
            task=task,
            snapshot=snapshot,
            deadline_at=deadline,
            budget_limit=Decimal(100),
            budget_currency="USD",
            now=now,
        )


def test_operational_limit_preview_digest_excludes_volatile_check_time():
    task = SimpleNamespace(
        id=uuid4(),
        title="Bounded study",
        revision=3,
        status="paused",
        outcome="stopped_time",
        deadline_at=None,
        budget_limit=None,
        budget_currency=None,
    )
    project = SimpleNamespace(id=uuid4(), uid="project", name="Project")
    lab = SimpleNamespace(id=uuid4(), uid="lab", name="Lab")
    db_session = SimpleNamespace(
        scalars=AsyncMock(return_value=SimpleNamespace(all=list))
    )
    params = OperationalLimitsDraft(
        expected_task_revision=3,
        deadline_at=datetime.now(UTC) + timedelta(days=2),
        budget_limit=None,
        budget_currency=None,
        reason="Continue the approved study window",
        idempotency_key="limits-test-001",
    )

    first = asyncio.run(
        _limit_preview(
            db_session,
            task=task,
            project=project,
            lab=lab,
            params=params,
        )
    )
    second = asyncio.run(
        _limit_preview(
            db_session,
            task=task,
            project=project,
            lab=lab,
            params=params,
        )
    )

    assert first["preview_digest"] == second["preview_digest"]
    assert first["resume_required"] is True


def test_openapi_exposes_budget_preview_confirm_contract():
    paths = app.openapi()["paths"]

    assert "/research-tasks/{task_id}/budget" in paths
    assert "/research-tasks/{task_id}/budget/entries/preview" in paths
    assert "/research-tasks/{task_id}/budget/entries" in paths
    assert "/research-tasks/{task_id}/operational-limits" in paths
    assert "/research-tasks/{task_id}/operational-limits/preview" in paths
