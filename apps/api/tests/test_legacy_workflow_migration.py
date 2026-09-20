"""The 0008 upgrade must not assume today's initial-schema table inventory."""

from importlib import import_module

import sqlalchemy as sa

from app.models.workflow import ProtocolWorkflow


def test_missing_legacy_workflow_is_created_without_future_tables():
    migration = import_module("migrations.versions.0009_research_tasks")
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        for name in ("projects", "users", "protocols"):
            connection.exec_driver_sql(f"CREATE TABLE {name} (id UUID PRIMARY KEY)")
        migration._ensure_legacy_workflow_table(connection)
        inspector = sa.inspect(connection)
        assert set(inspector.get_table_names()) == {
            "projects",
            "users",
            "protocols",
            "protocol_workflows",
        }
        columns = {c["name"]: c for c in inspector.get_columns("protocol_workflows")}
        assert set(columns) == set(ProtocolWorkflow.__table__.c.keys())
        for column in ProtocolWorkflow.__table__.c:
            assert columns[column.name]["nullable"] == column.nullable
        assert len(inspector.get_foreign_keys("protocol_workflows")) == 3
        assert len(inspector.get_indexes("protocol_workflows")) == 4


def test_existing_legacy_workflow_is_not_replaced_or_rewritten():
    migration = import_module("migrations.versions.0009_research_tasks")
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE protocol_workflows (id INTEGER, title TEXT)"
        )
        connection.exec_driver_sql(
            "INSERT INTO protocol_workflows VALUES (1, 'keep me')"
        )
        migration._ensure_legacy_workflow_table(connection)
        migration._ensure_legacy_workflow_table(connection)
        assert connection.exec_driver_sql("SELECT * FROM protocol_workflows").all() == [
            (1, "keep me")
        ]
