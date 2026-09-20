from importlib import import_module
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

MODULE = "migrations.versions.0075_legacy_file_metadata"


def setup_migration(monkeypatch, *, backend=None, has_files=True, existing=()):
    migration = import_module(MODULE)
    bind = MagicMock()
    bind.execute.return_value.scalar.return_value = has_files
    inspector = SimpleNamespace(
        get_columns=lambda _: [{"name": name} for name in existing],
        get_indexes=lambda _: [],
    )
    operations = MagicMock()
    operations.get_bind.return_value = bind
    monkeypatch.setattr(migration, "op", operations)
    monkeypatch.setattr(migration.sa, "inspect", lambda _: inspector)
    monkeypatch.setattr(
        migration.context,
        "get_x_argument",
        lambda **_: {} if backend is None else {"legacy_storage_backend": backend},
    )
    return migration, operations


@pytest.mark.parametrize("backend", [None, "external", "unknown"])
def test_existing_files_require_verified_backend_before_any_ddl(monkeypatch, backend):
    migration, operations = setup_migration(monkeypatch, backend=backend)
    with pytest.raises(RuntimeError, match="explicit verified storage backend"):
        migration.upgrade()
    operations.add_column.assert_not_called()


@pytest.mark.parametrize("backend", ["oss", "minio"])
def test_verified_backend_is_only_used_for_existing_rows(monkeypatch, backend):
    migration, operations = setup_migration(monkeypatch, backend=backend)
    migration.upgrade()
    columns = {
        call.args[1].name: call.args[1] for call in operations.add_column.call_args_list
    }
    assert len(columns) == 9
    assert columns["storage_backend"].server_default.arg == backend
    operations.alter_column.assert_called_once_with(
        "airalogy_files", "storage_backend", server_default=None
    )


def test_existing_modern_columns_are_never_rewritten(monkeypatch):
    names = (
        "content_type",
        "size_bytes",
        "checksum_sha256",
        "project_id",
        "storage_backend",
        "storage_namespace",
        "storage_object_key",
        "external_uri",
        "storage_metadata",
    )
    migration, operations = setup_migration(monkeypatch, existing=names)
    migration.upgrade()
    operations.add_column.assert_not_called()
    operations.alter_column.assert_not_called()
