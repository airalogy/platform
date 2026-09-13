"""Exact-scope Lab cleanup never treats a logical alias as a storage owner."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.libs import lab_force_delete as cleanup


def result(values):
    return SimpleNamespace(all=lambda: values)


def session(*, foreign_binding=None, foreign_export=None, wrong_scope=False):
    lab_id, project_id, protocol_id, task_id, file_id = (uuid4() for _ in range(5))
    task = SimpleNamespace(id=task_id, project_id=project_id)
    binding = SimpleNamespace(file_id=file_id, task_id=task_id)
    file = SimpleNamespace(
        id=file_id,
        project_id=uuid4() if wrong_scope else project_id,
        protocol_id=protocol_id,
        storage_backend="workflow_reference",
    )
    db = SimpleNamespace(
        scalars=AsyncMock(
            side_effect=[
                result([task]),
                result([project_id]),
                result([binding]),
                result([file]),
                result([protocol_id]),
            ]
        ),
        scalar=AsyncMock(side_effect=[foreign_binding, foreign_export]),
        execute=AsyncMock(),
    )
    return db, lab_id, task_id, file_id


def test_cleanup_is_scoped_and_removes_exports_before_lineage_before_aliases():
    db, lab_id, task_id, file_id = session()
    asyncio.run(cleanup._delete_lab_workflow_file_references(db, lab_id))
    statements = [
        str(
            call.args[0].compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        for call in db.execute.await_args_list
    ]
    assert len(statements) == 3
    assert statements[0].startswith("DELETE FROM workflow_file_export_references")
    assert str(lab_id) in statements[0] and str(file_id) in statements[0]
    assert statements[1].startswith("DELETE FROM workflow_file_bindings")
    assert str(task_id) in statements[1] and str(file_id) in statements[1]
    assert statements[2].startswith("DELETE FROM airalogy_files")
    assert str(file_id) in statements[2] and "workflow_reference" in statements[2]
    assert all("research_file_blobs" not in statement for statement in statements)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"wrong_scope": True},
        {"foreign_binding": "other-lab"},
        {"foreign_export": "other-lab"},
    ],
)
def test_foreign_scope_is_rejected_before_any_delete(kwargs):
    db, lab_id, _, _ = session(**kwargs)
    with pytest.raises(ValueError):
        asyncio.run(cleanup._delete_lab_workflow_file_references(db, lab_id))
    db.execute.assert_not_awaited()


def test_manifest_mismatch_cannot_start_lineage_cleanup(monkeypatch):
    remove = AsyncMock()
    monkeypatch.setattr(cleanup, "_delete_lab_workflow_file_references", remove)
    with pytest.raises(ValueError, match="manifest"):
        asyncio.run(
            cleanup._delete_lab_from_database(
                SimpleNamespace(), SimpleNamespace(id=uuid4()), {"lab_id": uuid4()}
            )
        )
    remove.assert_not_awaited()


def test_storage_cleanup_does_not_read_or_delete_a_logical_reference_key(monkeypatch):
    delete_key = AsyncMock()
    monkeypatch.setattr(cleanup, "_delete_storage_key", delete_key)
    manifest = {
        "logo_attachment": None,
        "protocol_versions": [],
        "airalogy_files": [
            SimpleNamespace(
                storage_backend="workflow_reference",
                object_key="shared/blob-must-not-delete",
            ),
            SimpleNamespace(storage_backend="minio", object_key="owned/protocol-file"),
        ],
    }
    assert asyncio.run(cleanup._cleanup_storage_objects(manifest)) == []
    delete_key.assert_awaited_once_with("owned/protocol-file", [])
