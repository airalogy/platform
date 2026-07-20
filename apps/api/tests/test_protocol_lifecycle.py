import asyncio
import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.config import config
from app.libs import protocol_import
from app.models.project import Project
from app.models.protocol import Protocol, ProtocolStatus
from app.models.protocol_version import ProtocolMetadata, ProtocolVersion
from app.routers import protocols


def test_delete_protocol_soft_deletes_its_active_records(monkeypatch):
    protocol_id = uuid.uuid4()
    project_id = uuid.uuid4()
    protocol = Protocol(
        id=protocol_id,
        project_id=project_id,
        user_id=uuid.uuid4(),
        uid="test_protocol",
        name="Test protocol",
        latest_version="1.0.0",
        parent_protocol_id=None,
    )
    project = SimpleNamespace(id=project_id)
    db_session = SimpleNamespace(
        execute=AsyncMock(),
        flush=AsyncMock(),
        commit=AsyncMock(),
    )

    monkeypatch.setattr(Protocol, "find", AsyncMock(return_value=protocol))
    monkeypatch.setattr(Project, "find", AsyncMock(return_value=project))
    monkeypatch.setattr(protocols, "check_user_permission", AsyncMock())

    result = asyncio.run(
        protocols.delete_protocol(
            protocol_id=protocol_id,
            current_user=SimpleNamespace(id=uuid.uuid4()),
            db_session=db_session,
        )
    )

    assert result == {"message": "success"}
    assert protocol.status == ProtocolStatus.DELETED
    assert isinstance(protocol.deleted_at, datetime)
    statement = db_session.execute.await_args.args[0]
    compiled = statement.compile()
    assert "UPDATE records SET deleted_at=" in str(compiled)
    assert "records.protocol_id" in str(compiled)
    assert "records.deleted_at IS NULL" in str(compiled)
    assert protocol_id in compiled.params.values()
    assert protocol.deleted_at in compiled.params.values()
    db_session.commit.assert_awaited_once()


def test_import_protocol_directory_restores_soft_deleted_protocol(
    tmp_path,
    monkeypatch,
):
    protocol_id = uuid.uuid4()
    project_id = uuid.uuid4()
    deleted_at = datetime.now()
    protocol = Protocol(
        id=protocol_id,
        project_id=project_id,
        user_id=uuid.uuid4(),
        uid="test_protocol",
        name="Test protocol",
        latest_version="1.0.0",
        status=ProtocolStatus.DELETED,
        deleted_at=deleted_at,
    )
    protocol_version = ProtocolVersion(
        id=uuid.uuid4(),
        protocol_id=protocol_id,
        version="1.0.0",
        meta_data={"id": "test_protocol"},
    )
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    db_session = SimpleNamespace(execute=AsyncMock())
    metadata = ProtocolMetadata(id="test_protocol", version="1.0.0")

    monkeypatch.setattr(config, "PROTOCOL_DIR", str(tmp_path / "protocols"))
    monkeypatch.setattr(
        protocol_import,
        "_load_protocol_info",
        AsyncMock(return_value=({}, metadata)),
    )
    find_protocol = AsyncMock(side_effect=[None, protocol])
    monkeypatch.setattr(Protocol, "find_by", find_protocol)
    monkeypatch.setattr(
        ProtocolVersion,
        "find_by",
        AsyncMock(return_value=protocol_version),
    )

    result = asyncio.run(
        protocol_import.import_protocol_directory(
            db_session=db_session,
            project=SimpleNamespace(id=project_id),
            user=SimpleNamespace(id=uuid.uuid4()),
            source_dir=source_dir,
        )
    )

    assert result.created_protocol is False
    assert result.restored_protocol is True
    assert result.reused_version is True
    assert find_protocol.await_count == 2
    assert protocol.status == ProtocolStatus.ACTIVE
    assert protocol.deleted_at is None
    statement = db_session.execute.await_args.args[0]
    compiled = statement.compile()
    assert "UPDATE records SET deleted_at=" in str(compiled)
    assert protocol_id in compiled.params.values()
    assert deleted_at in compiled.params.values()
