"""Actual migrated database guards; these raw rows do not prove computation."""

import asyncio
import os
from importlib import import_module

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.models.analysis import AnalysisPipeline, AnalysisPreview, AnalysisRun
from sqlalchemy import inspect, text, update
from sqlalchemy.exc import DBAPIError

from tests.test_record_analysis_postgres import database, seed_analysis

pytestmark = pytest.mark.skipif(
    not os.environ.get("RESOURCE_TEST_DATABASE_URL"),
    reason="Requires the dedicated migrated research-integration database",
)


def raw_contract(scope):
    return {
        "project_id": scope.project.id,
        "created_by_user_id": scope.analyst.id,
        "protocol_id": None,
        "source_scope": "project",
        "recipe": {},
        "source_selection": {},
        "source_digest": "0" * 64,
        "recipe_digest": "0" * 64,
        "preview_digest": "0" * 64,
    }


def test_0070_actual_scope_columns_and_check_constraints():
    async def exercise():
        async with database() as sessions, sessions() as db:
            connection = await db.connection()

            def columns_and_checks(connection):
                inspector = inspect(connection)
                return {
                    model.__tablename__: (
                        inspector.get_columns(model.__tablename__),
                        inspector.get_check_constraints(model.__tablename__),
                    )
                    for model in (AnalysisRun, AnalysisPipeline, AnalysisPreview)
                }

            actual = await connection.run_sync(columns_and_checks)
            for model in (AnalysisRun, AnalysisPipeline, AnalysisPreview):
                columns, constraints = actual[model.__tablename__]
                columns = {column["name"]: column for column in columns}
                assert set(columns) == set(model.__table__.c.keys())
                assert columns["protocol_id"]["nullable"] is True
                assert columns["source_scope"]["nullable"] is False
                assert "protocol" in columns["source_scope"]["default"]
                checks = [
                    row for row in constraints if row["name"].endswith("source_scope")
                ]
                assert len(checks) == 1
                assert "protocol_id IS NOT NULL" in checks[0]["sqltext"]
                assert "protocol_id IS NULL" in checks[0]["sqltext"]

    asyncio.run(exercise())


def test_project_history_seals_contract_and_terminal_result_in_actual_database():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            async with sessions() as db:
                run = AnalysisRun(
                    **raw_contract(scope),
                    source_snapshot={},
                    client_idempotency_key="synthetic-db-guard",
                    status="pending",
                    engine_version="airalogy.project-analysis.v1",
                )
                db.add(run)
                await db.commit()
                run_id = run.id
                for changes in (
                    {"question": "changed"},
                    {"source_scope": "protocol", "protocol_id": scope.protocol.id},
                ):
                    with pytest.raises(DBAPIError, match="immutable"):
                        async with db.begin_nested():
                            await db.execute(
                                update(AnalysisRun)
                                .where(AnalysisRun.id == run_id)
                                .values(**changes)
                            )
                await db.execute(
                    update(AnalysisRun)
                    .where(AnalysisRun.id == run_id)
                    .values(status="running")
                )
                await db.execute(
                    update(AnalysisRun)
                    .where(AnalysisRun.id == run_id)
                    .values(
                        status="succeeded",
                        result={"synthetic_db_guard_only": True},
                        result_digest="1" * 64,
                    )
                )
                await db.commit()
                for changes in (
                    {"result": {"changed": True}, "result_digest": "2" * 64},
                    {"status": "running"},
                    {"error": "rewrite"},
                ):
                    with pytest.raises(DBAPIError, match="immutable"):
                        async with db.begin_nested():
                            await db.execute(
                                update(AnalysisRun)
                                .where(AnalysisRun.id == run_id)
                                .values(**changes)
                            )
                assert (
                    await db.get(AnalysisRun, run_id, populate_existing=True)
                ).status == "succeeded"
                # Legacy defaults remain Protocol-scoped and do not acquire a
                # fabricated multi-source identity during the migration.
                legacy = AnalysisRun(
                    **{
                        **raw_contract(scope),
                        "protocol_id": scope.protocol.id,
                        "source_scope": "protocol",
                    },
                    source_snapshot={},
                    client_idempotency_key="synthetic-db-legacy",
                    status="pending",
                    engine_version="airalogy.analysis.v1",
                )
                db.add(legacy)
                await db.commit()
                assert legacy.protocol_id == scope.protocol.id

    asyncio.run(exercise())


def test_actual_0070_downgrade_refuses_and_preserves_project_history():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            async with sessions() as db:
                run = AnalysisRun(
                    **raw_contract(scope),
                    source_snapshot={},
                    client_idempotency_key="synthetic-downgrade-guard",
                    status="pending",
                    engine_version="airalogy.project-analysis.v1",
                )
                db.add(run)
                await db.commit()
                run_id = run.id
                connection = await db.connection()

                def downgrade(connection):
                    with Operations.context(MigrationContext.configure(connection)):
                        import_module(
                            "migrations.versions.0070_project_analysis"
                        ).downgrade()

                with pytest.raises(RuntimeError, match="Cannot downgrade"):
                    await connection.run_sync(downgrade)
                await db.rollback()
                assert (await db.get(AnalysisRun, run_id)).source_scope == "project"
                assert await db.scalar(
                    text("SELECT to_regclass('analysis_project_inputs')")
                )

    asyncio.run(exercise())
