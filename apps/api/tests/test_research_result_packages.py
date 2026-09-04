import asyncio
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.main import app
from app.models.research import ResearchResultPackageSnapshot
from app.routers import research_result_packages as result_package_router
from app.services.research_result_packages import (
    RESULT_PACKAGE_SCHEMA,
    ResearchResultPackageError,
    normalize_final_result_package,
    render_result_package_markdown,
    result_package_digest,
    verify_result_package_digest,
)
from app.services.research_runtime import build_research_result_package


def compile_table(model) -> str:
    return str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))


def complete_package() -> dict:
    return {
        "schema": RESULT_PACKAGE_SCHEMA,
        "task_id": str(uuid4()),
        "run_id": str(uuid4()),
        "goal": "Determine whether treatment A changes response B",
        "success_criteria": ["Validated measurement"],
        "goal_assessment": "goal_met",
        "scientific_outcome": "supports_hypothesis",
        "narrative_conclusion": "Aira draft",
        "reviewed_conclusion": "Treatment A increased response B under condition C.",
        "reviewed_by_user_id": str(uuid4()),
        "reviewed_at": datetime.now(UTC).isoformat(),
        "claims": [
            {
                "id": str(uuid4()),
                "statement": "A increased B under C",
                "state": "reviewed",
                "confidence": "0.9",
                "uncertainty": "One site",
            }
        ],
        "evidence": [
            {
                "id": str(uuid4()),
                "summary": "Validated measurement set",
                "kind": "measurement",
                "quality_state": "validated",
                "artifact_type": "data_asset",
                "artifact_id": str(uuid4()),
                "artifact_version": "1",
            }
        ],
        "data_assets": [],
        "knowledge_items": [],
        "protocol_improvements": [],
        "actions": [],
        "failed_attempts": [],
        "unresolved_questions": ["Does the effect replicate at another site?"],
        "reproducibility": {"plan_version": 3, "environment_snapshot": {}},
        "budget": {"currency": "USD", "actual": "25"},
        "generated_at": datetime.now(UTC).isoformat(),
    }


def test_result_package_snapshot_schema_is_append_only_and_migration_is_chained():
    ddl = compile_table(ResearchResultPackageSnapshot)
    migration = import_module(
        "migrations.versions.0035_research_result_package_snapshots"
    )

    assert "UNIQUE (run_id)" in ddl
    assert "ck_research_result_package_task_revision" in ddl
    assert "ck_research_result_package_digest" in ddl
    assert migration.TABLE_NAMES == ("research_result_package_snapshots",)
    assert migration.down_revision == "0034_research_claim_ai_provenance"
    source = Path(migration.__file__).read_text(encoding="utf-8")
    assert "research_result_package_snapshots_append_only" in source
    assert "BEFORE UPDATE OR DELETE" in source


def test_final_result_package_requires_human_review_and_has_tamper_evident_digest():
    package = normalize_final_result_package(complete_package())
    digest = result_package_digest(package)

    assert len(digest) == 64
    verify_result_package_digest(package, digest)
    with pytest.raises(ResearchResultPackageError, match="does not match"):
        verify_result_package_digest({**package, "goal": "Changed"}, digest)
    with pytest.raises(ResearchResultPackageError, match="human reviewer"):
        normalize_final_result_package({**package, "reviewed_by_user_id": ""})


def test_manual_run_can_build_the_same_complete_result_package_base_as_aira():
    task_id = uuid4()
    run_id = uuid4()
    db_session = SimpleNamespace(
        scalars=AsyncMock(return_value=SimpleNamespace(all=list))
    )
    task = SimpleNamespace(
        id=task_id,
        goal="Complete a governed manual study",
        success_criteria=["Validated Record"],
        budget_limit=None,
        budget_currency=None,
    )
    run = SimpleNamespace(
        id=run_id,
        aira_state={},
        environment_snapshot={"schema": "airalogy.research-environment.v2"},
        plan_version=1,
    )

    package = asyncio.run(build_research_result_package(db_session, task=task, run=run))

    assert package["schema"] == RESULT_PACKAGE_SCHEMA
    assert package["task_id"] == str(task_id)
    assert package["run_id"] == str(run_id)
    assert package["goal"] == task.goal
    assert package["actions"] == []
    assert package["claims"] == []
    assert package["budget"]["enabled"] is False


def test_markdown_result_package_is_human_readable_and_retains_raw_snapshot():
    package = complete_package()
    digest = result_package_digest(package)

    english = render_result_package_markdown(
        task_title="Treatment study",
        run_number=2,
        package=package,
        digest=digest,
        sealed=True,
        finalized_at=package["reviewed_at"],
        language="en",
    )
    chinese = render_result_package_markdown(
        task_title="处理实验",
        run_number=2,
        package=package,
        digest=digest,
        sealed=True,
        finalized_at=package["reviewed_at"],
        language="zh",
    )

    assert "# Research Result Package: Treatment study" in english
    assert digest in english
    assert "A increased B under C" in english
    assert "Validated measurement set" in english
    assert "Complete machine-readable snapshot" in english
    assert "# 科研结果包: 处理实验" in chinese


def test_legacy_package_is_readable_without_claiming_it_was_finalized(monkeypatch):
    task_id = uuid4()
    run_id = uuid4()
    task = SimpleNamespace(
        id=task_id,
        title="Legacy study",
        project_id=uuid4(),
        revision=9,
    )
    run = SimpleNamespace(
        id=run_id,
        task_id=task_id,
        run_number=1,
        result_package={
            **complete_package(),
            "task_id": str(task_id),
            "run_id": str(run_id),
        },
    )
    db_session = SimpleNamespace(
        scalars=AsyncMock(return_value=SimpleNamespace(first=lambda: run))
    )
    monkeypatch.setattr(
        result_package_router,
        "_authorized_task",
        AsyncMock(return_value=task),
    )
    monkeypatch.setattr(
        result_package_router.ResearchResultPackageSnapshot,
        "find_by",
        AsyncMock(return_value=None),
    )

    envelope, returned_task, returned_run = asyncio.run(
        result_package_router._result_package_envelope(
            db_session,
            task_id=task_id,
            current_user=SimpleNamespace(id=uuid4()),
            run_id=None,
        )
    )

    assert returned_task is task
    assert returned_run is run
    assert envelope["snapshot"]["sealed"] is False
    assert envelope["snapshot"]["task_revision"] is None
    assert envelope["snapshot"]["finalized_at"] is None
    assert len(envelope["snapshot"]["digest"]) == 64


def test_openapi_exposes_result_package_read_and_export_routes():
    paths = app.openapi()["paths"]

    assert "/research-tasks/{task_id}/result-package" in paths
    assert "/research-tasks/{task_id}/result-package/export" in paths
