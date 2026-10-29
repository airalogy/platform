"""Rehearse additive migrations and loss-protected recovery in a private schema."""

import asyncio
import os
from importlib import import_module
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.skipif(
    not os.getenv("RESOURCE_TEST_DATABASE_URL"),
    reason="Isolated migrated PostgreSQL required",
)


def test_upgrade_downgrade_and_parent_scope_deletion():
    async def exercise():
        engine = create_async_engine(os.environ["RESOURCE_TEST_DATABASE_URL"])
        schema = f"kit_migration_{uuid4().hex}"
        migrations = [
            import_module("migrations.versions.0076_scenario_kits"),
            import_module("migrations.versions.0077_record_resource_reservation"),
        ]
        try:
            async with engine.connect() as connection:
                transaction = await connection.begin()
                try:
                    await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                    await connection.execute(
                        text(f'SET LOCAL search_path TO "{schema}", public')
                    )
                    for table in (
                        "users",
                        "labs",
                        "projects",
                        "resource_types",
                        "inventory_reservations",
                        "record_resource_links",
                    ):
                        await connection.execute(
                            text(f"CREATE TABLE {table} (id uuid PRIMARY KEY)")
                        )

                    async def migration(module, direction):
                        def run(sync):
                            with Operations.context(MigrationContext.configure(sync)):
                                getattr(module, direction)()

                        await connection.run_sync(run)

                    for module in migrations:
                        await migration(module, "upgrade")
                    for module in reversed(migrations):
                        await migration(module, "downgrade")
                    for module in migrations:
                        await migration(module, "upgrade")
                    owner, lab, project, event = (uuid4() for _ in range(4))
                    for table, identity in (
                        ("users", owner),
                        ("labs", lab),
                        ("projects", project),
                    ):
                        await connection.execute(
                            text(f"INSERT INTO {table} VALUES (:id)"), {"id": identity}
                        )
                    await connection.execute(
                        text(
                            "INSERT INTO scenario_kit_events (id, lab_id, project_id, actor_user_id, request_id, operation, request_digest, snapshot) VALUES (:id, :lab, :project, :owner, :request, 'apply', 'synthetic', '{}')"
                        ),
                        {
                            "id": event,
                            "lab": lab,
                            "project": project,
                            "owner": owner,
                            "request": uuid4(),
                        },
                    )
                    for sql in (
                        "DELETE FROM scenario_kit_events",
                        "UPDATE scenario_kit_events SET operation='tampered'",
                    ):
                        with pytest.raises(DBAPIError):
                            async with connection.begin_nested():
                                await connection.execute(text(sql))
                    with pytest.raises(RuntimeError, match="provenance"):
                        await migration(migrations[0], "downgrade")
                    # Only a cascading, authorized parent deletion can remove receipts.
                    await connection.execute(
                        text("DELETE FROM projects WHERE id=:id"), {"id": project}
                    )
                    assert (
                        await connection.scalar(
                            text("SELECT count(*) FROM scenario_kit_events")
                        )
                        == 0
                    )
                    reservation = uuid4()
                    await connection.execute(
                        text("INSERT INTO inventory_reservations VALUES (:id)"),
                        {"id": reservation},
                    )
                    await connection.execute(
                        text(
                            "INSERT INTO record_resource_links VALUES (:id, :reservation)"
                        ),
                        {"id": uuid4(), "reservation": reservation},
                    )
                    with pytest.raises(RuntimeError, match="lineage"):
                        await migration(migrations[1], "downgrade")
                finally:
                    await transaction.rollback()  # also removes the private schema
        finally:
            await engine.dispose()

    asyncio.run(exercise())
