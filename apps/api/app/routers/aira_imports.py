import copy
import json
import mimetypes
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from airalogy.archive import ArchiveError, unpack_archive, validate_archive
from airalogy.record.hash import get_data_sha1
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from sqlalchemy import func, select

from app.database import DBSession
from app.libs.protocol_agent import prepare_protocol_package, protocol_exec
from app.libs.protocol_import import ProtocolImportResult, import_protocol_directory
from app.models.airalogy_file import AiralogyFile
from app.models.lab import Lab
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.routers.depends import CurrentUser
from app.routers.permission import check_user_permission
from app.routers.utils import UUID

router = APIRouter(
    prefix="/projects/{project_id}/aira",
    tags=["aira-imports"],
)

_AIRALOGY_FILE_ID_RE = re.compile(
    r"^airalogy\.id\.file\.([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.(.+)$"
)
_AIRALOGY_RECORD_ID_RE = re.compile(
    r"^airalogy\.id\.record\.([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.v\.(\d+)$"
)
_AIRALOGY_PROTOCOL_ID_RE = re.compile(
    r"^airalogy\.id\.lab\.[A-Za-z0-9_-]+\.project\.[A-Za-z0-9_-]+\.protocol\.([a-z][a-z0-9_]*)\.v\.(\d{1,3}(?:\.\d{1,3}){2})$"
)


@dataclass
class ImportedProtocol:
    archive_root: str
    result: ProtocolImportResult


@dataclass
class PendingRecord:
    archive_path: str
    payload: dict[str, Any]
    manifest_entry: dict[str, Any]
    protocol: Protocol
    protocol_version: ProtocolVersion
    record_id: uuid.UUID
    record_version: int
    data: dict[str, Any]
    report: str
    number: int | None = None


def _manifest_items(manifest: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = manifest.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid record JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail=f"Record file must be an object: {path}")
    return payload


def _as_uuid(value: Any) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _record_id_from_airalogy_id(value: Any) -> uuid.UUID | None:
    if not isinstance(value, str):
        return None
    match = _AIRALOGY_RECORD_ID_RE.match(value)
    if not match:
        return None
    return uuid.UUID(match.group(1))


def _record_version_from_airalogy_id(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    match = _AIRALOGY_RECORD_ID_RE.match(value)
    if not match:
        return None
    return int(match.group(2))


def _file_uuid_from_airalogy_id(value: Any) -> uuid.UUID | None:
    if not isinstance(value, str):
        return None
    match = _AIRALOGY_FILE_ID_RE.match(value)
    if not match:
        return None
    return uuid.UUID(match.group(1))


def _file_extension_from_airalogy_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = _AIRALOGY_FILE_ID_RE.match(value)
    if not match:
        return None
    return match.group(2)


def _record_version(payload: dict[str, Any], manifest_entry: dict[str, Any]) -> int:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    candidates = [
        payload.get("record_version"),
        manifest_entry.get("record_version"),
        metadata.get("record_ver"),
        _record_version_from_airalogy_id(payload.get("airalogy_record_id")),
    ]
    for candidate in candidates:
        if isinstance(candidate, bool):
            continue
        if isinstance(candidate, int) and candidate >= 1:
            return candidate
        if isinstance(candidate, str) and candidate.isdigit() and int(candidate) >= 1:
            return int(candidate)
    return 1


def _record_uuid(payload: dict[str, Any], manifest_entry: dict[str, Any]) -> uuid.UUID:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    candidates = [
        payload.get("record_id"),
        payload.get("id"),
        manifest_entry.get("record_id"),
        metadata.get("record_id"),
    ]
    for candidate in candidates:
        record_id = _as_uuid(candidate)
        if record_id is not None:
            return record_id

    record_id = _record_id_from_airalogy_id(payload.get("airalogy_record_id"))
    return record_id or uuid.uuid4()


def _record_protocol_uid(payload: dict[str, Any], manifest_entry: dict[str, Any]) -> str | None:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    value = manifest_entry.get("protocol_id") or metadata.get("protocol_id")
    if value:
        return str(value)

    airalogy_id = manifest_entry.get("airalogy_protocol_id") or metadata.get(
        "airalogy_protocol_id"
    )
    if not isinstance(airalogy_id, str):
        return None
    match = _AIRALOGY_PROTOCOL_ID_RE.match(airalogy_id)
    return match.group(1) if match else None


def _record_protocol_version(
    payload: dict[str, Any],
    manifest_entry: dict[str, Any],
) -> str | None:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    value = (
        manifest_entry.get("protocol_version")
        or metadata.get("protocol_version")
        or metadata.get("rn_ver")
    )
    if value:
        return str(value)

    airalogy_id = manifest_entry.get("airalogy_protocol_id") or metadata.get(
        "airalogy_protocol_id"
    )
    if not isinstance(airalogy_id, str):
        return None
    match = _AIRALOGY_PROTOCOL_ID_RE.match(airalogy_id)
    return match.group(2) if match else None


def _normalized_record_data(payload: dict[str, Any]) -> dict[str, Any]:
    raw_data = payload.get("data")
    data = copy.deepcopy(raw_data) if isinstance(raw_data, dict) else {}
    for section in ("step", "var", "check"):
        if not isinstance(data.get(section), dict):
            data[section] = {}
    return data


def _replace_record_value(value: Any, old_value: str, new_value: str) -> Any:
    if value == old_value:
        return new_value
    if isinstance(value, dict):
        return {
            key: _replace_record_value(item, old_value, new_value)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_record_value(item, old_value, new_value) for item in value]
    return value


def _set_record_field_path(data: dict[str, Any], field_path: str, value: Any) -> None:
    parts = [part for part in field_path.split(".") if part]
    if parts and parts[0] == "data":
        parts = parts[1:]
    if not parts:
        return

    current: Any = data
    for part in parts[:-1]:
        if isinstance(current, dict):
            next_value = current.get(part)
            if not isinstance(next_value, (dict, list)):
                next_value = {}
                current[part] = next_value
            current = next_value
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            while len(current) <= index:
                current.append({})
            current = current[index]
        else:
            return

    last = parts[-1]
    if isinstance(current, dict):
        current[last] = value
    elif isinstance(current, list) and last.isdigit():
        index = int(last)
        while len(current) <= index:
            current.append(None)
        current[index] = value


def _filename_from_file_ref(file_ref: dict[str, Any]) -> str:
    filename = file_ref.get("filename")
    if isinstance(filename, str) and filename.strip():
        return filename.strip()

    source_uri = file_ref.get("source_uri")
    if isinstance(source_uri, str) and source_uri.strip():
        parsed = urlparse(source_uri)
        basename = Path(parsed.path).name
        if basename:
            return basename

    file_id = file_ref.get("file_id")
    ext = _file_extension_from_airalogy_id(file_id)
    if ext:
        return f"archive-file.{ext}"
    return "archive-file"


def _protocol_response(
    *,
    imported_protocol: ImportedProtocol,
    project: Project,
    lab: Lab,
) -> dict[str, Any]:
    result = imported_protocol.result
    protocol = result.protocol
    protocol_version = result.protocol_version
    return {
        "archive_root": imported_protocol.archive_root,
        "id": str(protocol.id),
        "uid": protocol.uid,
        "name": protocol.name,
        "project_id": str(project.id),
        "project_uid": project.uid,
        "lab_id": str(lab.id),
        "lab_uid": lab.uid,
        "protocol_version_id": str(protocol_version.id),
        "version": protocol_version.version,
        "created_protocol": result.created_protocol,
        "created_version": result.created_version,
        "reused_version": result.reused_version,
    }


async def _resolve_project(project_id: UUID, db_session: DBSession) -> Project:
    project = await Project.find_by(
        db_session,
        [Project.id == project_id, Project.deleted_at.is_(None)],
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _resolve_protocol_version(
    *,
    db_session: DBSession,
    project: Project,
    protocol_uid: str | None,
    protocol_version: str | None,
) -> tuple[Protocol, ProtocolVersion]:
    if not protocol_uid:
        raise HTTPException(
            status_code=400,
            detail="Record archive does not identify the target protocol",
        )

    protocol = await Protocol.find_by(
        db_session,
        [
            Protocol.uid == protocol_uid,
            Protocol.project_id == project.id,
            Protocol.deleted_at.is_(None),
        ],
    )
    if protocol is None:
        raise HTTPException(
            status_code=400,
            detail=f"Target protocol '{protocol_uid}' was not found in this project",
        )

    target_version = protocol_version or protocol.latest_version
    protocol_version_model = await ProtocolVersion.find_by(
        db_session,
        [
            ProtocolVersion.protocol_id == protocol.id,
            ProtocolVersion.version == target_version,
        ],
    )
    if protocol_version_model is None:
        raise HTTPException(
            status_code=400,
            detail=f"Protocol '{protocol_uid}' version '{target_version}' was not found",
        )
    return protocol, protocol_version_model


class AiraArchiveImporter:
    def __init__(
        self,
        *,
        db_session: DBSession,
        project: Project,
        lab: Lab,
        user: CurrentUser,
        background_tasks: BackgroundTasks,
    ):
        self.db_session = db_session
        self.project = project
        self.lab = lab
        self.user = user
        self.background_tasks = background_tasks
        self.imported_protocols_by_root: dict[str, ImportedProtocol] = {}
        self.protocol_results: list[dict[str, Any]] = []
        self.record_results: list[dict[str, Any]] = []
        self.file_results: list[dict[str, Any]] = []

    async def import_archive(
        self,
        *,
        unpack_dir: Path,
        manifest: dict[str, Any],
    ) -> dict[str, Any]:
        kind = manifest["kind"]

        if kind == "protocol":
            await check_user_permission(
                self.db_session,
                project=self.project,
                user=self.user,
                action="create_protocol",
            )
            await self._import_protocol_entry(
                archive_root="",
                source_dir=unpack_dir,
            )
        elif kind == "protocols":
            await check_user_permission(
                self.db_session,
                project=self.project,
                user=self.user,
                action="create_protocol",
            )
            for protocol_entry in _manifest_items(manifest, "protocols"):
                await self._import_protocol_entry(
                    archive_root=str(protocol_entry["archive_root"]),
                    source_dir=unpack_dir / str(protocol_entry["archive_root"]),
                )
        elif kind == "records":
            embedded_protocols = _manifest_items(manifest, "protocols")
            if embedded_protocols:
                await check_user_permission(
                    self.db_session,
                    project=self.project,
                    user=self.user,
                    action="create_protocol",
                )
            for protocol_entry in embedded_protocols:
                await self._import_protocol_entry(
                    archive_root=str(protocol_entry["archive_root"]),
                    source_dir=unpack_dir / str(protocol_entry["archive_root"]),
                )
            pending_records = await self._load_pending_records(
                unpack_dir=unpack_dir,
                manifest=manifest,
            )
            await self._import_files(
                unpack_dir=unpack_dir,
                manifest=manifest,
                pending_records=pending_records,
            )
            await self._create_records(pending_records)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported archive kind: {kind}")

        return {
            "kind": kind,
            "protocols": self.protocol_results,
            "records": self.record_results,
            "files": self.file_results,
            "imported_protocol_count": len(
                [item for item in self.protocol_results if item["created_version"]]
            ),
            "imported_record_count": len(self.record_results),
            "imported_file_count": len(self.file_results),
        }

    async def import_record_archive_to_protocol(
        self,
        *,
        unpack_dir: Path,
        manifest: dict[str, Any],
        protocol: Protocol,
        protocol_version: ProtocolVersion,
    ) -> dict[str, Any]:
        kind = manifest["kind"]
        if kind != "records":
            raise HTTPException(
                status_code=400,
                detail="Only records .aira archives can be imported into an existing Protocol",
            )

        await check_user_permission(
            self.db_session,
            project=self.project,
            user=self.user,
            action="create_record",
            protocol=protocol,
        )
        pending_records = await self._load_pending_records(
            unpack_dir=unpack_dir,
            manifest=manifest,
            target_protocol=protocol,
            target_protocol_version=protocol_version,
        )
        await self._import_files(
            unpack_dir=unpack_dir,
            manifest=manifest,
            pending_records=pending_records,
        )
        await self._create_records(pending_records)

        return {
            "kind": kind,
            "protocols": self.protocol_results,
            "records": self.record_results,
            "files": self.file_results,
            "imported_protocol_count": 0,
            "imported_record_count": len(self.record_results),
            "imported_file_count": len(self.file_results),
        }

    async def _import_protocol_entry(self, *, archive_root: str, source_dir: Path) -> None:
        result = await import_protocol_directory(
            db_session=self.db_session,
            project=self.project,
            user=self.user,
            source_dir=source_dir,
            background_tasks=self.background_tasks,
        )
        imported_protocol = ImportedProtocol(
            archive_root=archive_root,
            result=result,
        )
        self.imported_protocols_by_root[archive_root] = imported_protocol
        self.protocol_results.append(
            _protocol_response(
                imported_protocol=imported_protocol,
                project=self.project,
                lab=self.lab,
            )
        )

    async def _load_pending_records(
        self,
        *,
        unpack_dir: Path,
        manifest: dict[str, Any],
        target_protocol: Protocol | None = None,
        target_protocol_version: ProtocolVersion | None = None,
    ) -> list[PendingRecord]:
        pending_records: list[PendingRecord] = []
        seen_keys: set[tuple[uuid.UUID, int]] = set()

        for record_entry in _manifest_items(manifest, "records"):
            archive_path = str(record_entry["path"])
            payload = _load_json(unpack_dir / archive_path)
            record_id = _record_uuid(payload, record_entry)
            record_version = _record_version(payload, record_entry)
            key = (record_id, record_version)
            if key in seen_keys:
                raise HTTPException(
                    status_code=400,
                    detail=f"Duplicate record {record_id} version {record_version} in archive",
                )
            seen_keys.add(key)

            embedded_protocol_root = record_entry.get("embedded_protocol_root")
            if target_protocol is not None and target_protocol_version is not None:
                protocol_uid = _record_protocol_uid(payload, record_entry)
                if protocol_uid and protocol_uid != target_protocol.uid:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Record '{archive_path}' targets protocol '{protocol_uid}', "
                            f"not '{target_protocol.uid}'"
                        ),
                    )

                protocol_version = _record_protocol_version(payload, record_entry)
                if protocol_version:
                    protocol_version_model = await ProtocolVersion.find_by(
                        self.db_session,
                        [
                            ProtocolVersion.protocol_id == target_protocol.id,
                            ProtocolVersion.version == protocol_version,
                        ],
                    )
                    if protocol_version_model is None:
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                f"Protocol '{target_protocol.uid}' version "
                                f"'{protocol_version}' was not found"
                            ),
                        )
                else:
                    protocol_version_model = target_protocol_version
                protocol = target_protocol
            elif isinstance(embedded_protocol_root, str) and embedded_protocol_root:
                imported_protocol = self.imported_protocols_by_root.get(
                    embedded_protocol_root
                )
                if imported_protocol is None:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "Record references missing embedded protocol root "
                            f"'{embedded_protocol_root}'"
                        ),
                    )
                protocol = imported_protocol.result.protocol
                protocol_version_model = imported_protocol.result.protocol_version
            else:
                protocol_uid = _record_protocol_uid(payload, record_entry)
                protocol_version = _record_protocol_version(payload, record_entry)
                protocol, protocol_version_model = await _resolve_protocol_version(
                    db_session=self.db_session,
                    project=self.project,
                    protocol_uid=protocol_uid,
                    protocol_version=protocol_version,
                )

            await check_user_permission(
                self.db_session,
                project=self.project,
                user=self.user,
                action="create_record",
                protocol=protocol,
            )

            pending_records.append(
                PendingRecord(
                    archive_path=archive_path,
                    payload=payload,
                    manifest_entry=record_entry,
                    protocol=protocol,
                    protocol_version=protocol_version_model,
                    record_id=record_id,
                    record_version=record_version,
                    data=_normalized_record_data(payload),
                    report=str(payload.get("report") or ""),
                )
            )

        if not pending_records:
            raise HTTPException(status_code=400, detail="No records found in archive")
        return pending_records

    async def _import_files(
        self,
        *,
        unpack_dir: Path,
        manifest: dict[str, Any],
        pending_records: list[PendingRecord],
    ) -> None:
        records_by_path = {record.archive_path: record for record in pending_records}
        blob_by_id = {
            str(blob["blob_id"]): blob for blob in _manifest_items(manifest, "blobs")
        }

        for file_ref in _manifest_items(manifest, "files"):
            record_path = file_ref.get("record_path")
            if isinstance(record_path, str) and record_path:
                pending_record = records_by_path.get(record_path)
            elif len(pending_records) == 1:
                pending_record = pending_records[0]
            else:
                raise HTTPException(
                    status_code=400,
                    detail="File reference must identify a record_path",
                )

            if pending_record is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"File reference points to unknown record '{record_path}'",
                )

            old_file_id = file_ref.get("file_id") if isinstance(file_ref.get("file_id"), str) else None
            requested_uuid = _file_uuid_from_airalogy_id(old_file_id)
            existing_file = None
            if requested_uuid is not None:
                existing_file = await AiralogyFile.find_by(
                    self.db_session,
                    [AiralogyFile.id == requested_uuid],
                )

            blob_id = file_ref.get("blob_id")
            blob = blob_by_id.get(blob_id) if isinstance(blob_id, str) else None
            source_uri = file_ref.get("source_uri")
            has_source_uri = isinstance(source_uri, str) and bool(source_uri.strip())

            if (
                existing_file is not None
                and existing_file.protocol_id == pending_record.protocol.id
            ):
                airalogy_file = existing_file
            else:
                if existing_file is not None and blob is None and not has_source_uri:
                    raise HTTPException(
                        status_code=400,
                        detail=f"File id '{old_file_id}' already exists and has no payload",
                    )
                if blob is None and not has_source_uri:
                    raise HTTPException(
                        status_code=400,
                        detail=f"File reference '{old_file_id or ''}' has no blob or source_uri",
                    )

                filename = _filename_from_file_ref(file_ref)
                content_type = file_ref.get("mime_type") or mimetypes.guess_type(filename)[0]
                file_uuid = (
                    requested_uuid
                    if requested_uuid is not None and existing_file is None
                    else uuid.uuid4()
                )
                airalogy_file = AiralogyFile(
                    id=file_uuid,
                    filename=filename,
                    content_type=content_type,
                    size_bytes=file_ref.get("size") if isinstance(file_ref.get("size"), int) else None,
                    protocol_id=pending_record.protocol.id,
                    project_id=self.project.id,
                    user_id=self.user.id,
                )

                if blob is not None:
                    checksum = blob.get("sha256") if isinstance(blob.get("sha256"), str) else None
                    archive_path = blob.get("archive_path")
                    if not isinstance(archive_path, str):
                        raise HTTPException(status_code=400, detail="Blob archive_path is missing")
                    blob_path = unpack_dir / archive_path
                    airalogy_file.storage_metadata = {
                        "source_uri": source_uri,
                        "archive_blob_id": blob_id,
                    }
                    self.db_session.add(airalogy_file)
                    await airalogy_file.save_file(
                        file=str(blob_path),
                        content_type=content_type,
                        length=blob.get("size") if isinstance(blob.get("size"), int) else -1,
                        checksum_sha256=checksum,
                    )
                else:
                    airalogy_file.set_external_storage_location(
                        external_uri=str(source_uri),
                        metadata={"archive_file_id": old_file_id},
                    )
                    self.db_session.add(airalogy_file)

            new_file_id = airalogy_file.airalogy_id
            field_path = file_ref.get("field_path")
            if isinstance(field_path, str) and field_path:
                _set_record_field_path(pending_record.data, field_path, new_file_id)
            if old_file_id and old_file_id != new_file_id:
                pending_record.data = _replace_record_value(
                    pending_record.data,
                    old_file_id,
                    new_file_id,
                )

            self.file_results.append(
                {
                    "id": str(airalogy_file.id),
                    "airalogy_file_id": new_file_id,
                    "filename": airalogy_file.filename,
                    "record_id": str(pending_record.record_id),
                    "record_version": pending_record.record_version,
                }
            )

    async def _create_records(self, pending_records: list[PendingRecord]) -> None:
        latest_numbers: dict[uuid.UUID, int] = {}
        created_by_key: dict[tuple[uuid.UUID, int], Record] = {}
        prepared_protocol_versions: set[uuid.UUID] = set()

        async def next_number(protocol_id: uuid.UUID) -> int:
            if protocol_id not in latest_numbers:
                latest_number = await self.db_session.scalar(
                    select(func.max(Record.number)).where(Record.protocol_id == protocol_id)
                )
                latest_numbers[protocol_id] = latest_number or 0
            latest_numbers[protocol_id] += 1
            return latest_numbers[protocol_id]

        sorted_records = sorted(
            pending_records,
            key=lambda item: (str(item.record_id), item.record_version),
        )

        for pending_record in sorted_records:
            existing_exact = await Record.find_by(
                self.db_session,
                [
                    Record.id == pending_record.record_id,
                    Record.version == pending_record.record_version,
                ],
            )
            if existing_exact is not None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Record {pending_record.record_id} version "
                        f"{pending_record.record_version} already exists"
                    ),
                )

            if pending_record.record_version == 1:
                number = await next_number(pending_record.protocol.id)
            else:
                previous_key = (
                    pending_record.record_id,
                    pending_record.record_version - 1,
                )
                previous_record = created_by_key.get(previous_key)
                if previous_record is None:
                    previous_record = await Record.find_by(
                        self.db_session,
                        [
                            Record.id == pending_record.record_id,
                            Record.version == pending_record.record_version - 1,
                        ],
                    )
                if previous_record is None:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Record {pending_record.record_id} version "
                            f"{pending_record.record_version} has no previous version"
                        ),
                )
                number = previous_record.number

            if pending_record.protocol_version.id not in prepared_protocol_versions:
                await prepare_protocol_package(pending_record.protocol_version)
                prepared_protocol_versions.add(pending_record.protocol_version.id)
            validation_result = await protocol_exec(
                "var_validate",
                pending_record.protocol_version.package_name,
                pending_record.data.get("var"),
            )
            if validation_result["success"] is False:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": validation_result["message"],
                        "record_path": pending_record.archive_path,
                    },
                )
            validation_data = validation_result["data"]
            if validation_data.get("errors") is not None:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "validate error",
                        "record_path": pending_record.archive_path,
                        "errors": validation_data["errors"],
                    },
                )
            for key, schema in (
                pending_record.protocol_version.json_schema["vars"]["properties"].items()
            ):
                if schema.get("airalogy_type") == "IgnoreStr":
                    pending_record.data["var"][key] = ""

            record = Record(
                id=pending_record.record_id,
                protocol_id=pending_record.protocol.id,
                protocol_version=pending_record.protocol_version.version,
                user_id=self.user.id,
                data=pending_record.data,
                report=pending_record.report,
                number=number,
                version=pending_record.record_version,
                hash=get_data_sha1({"data": pending_record.data}),
            )
            self.db_session.add(record)
            created_by_key[(record.id, record.version)] = record
            self.record_results.append(
                {
                    "id": str(record.id),
                    "version": record.version,
                    "protocol_id": str(record.protocol_id),
                    "protocol_uid": pending_record.protocol.uid,
                    "protocol_version": record.protocol_version,
                    "number": record.number,
                }
            )


@router.post("/import")
async def import_aira_archive(
    project_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    filename = file.filename or ""
    if not filename.lower().endswith(".aira"):
        raise HTTPException(status_code=400, detail="Only .aira files are supported")

    project = await _resolve_project(project_id, db_session)
    lab = await Lab.find(db_session, id=project.lab_id)

    with tempfile.TemporaryDirectory(prefix="aira_import_") as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        archive_path = tmp_dir / "upload.aira"
        try:
            with archive_path.open("wb") as target:
                while chunk := await file.read(1024 * 1024):
                    target.write(chunk)
        finally:
            await file.close()

        is_valid, issues = validate_archive(archive_path)
        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail={"message": "Invalid .aira archive", "errors": issues},
            )

        try:
            unpack_dir, manifest = unpack_archive(
                archive_path,
                tmp_dir / "unpacked",
                force=True,
            )
        except ArchiveError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        importer = AiraArchiveImporter(
            db_session=db_session,
            project=project,
            lab=lab,
            user=current_user,
            background_tasks=background_tasks,
        )
        result = await importer.import_archive(unpack_dir=unpack_dir, manifest=manifest)

    await db_session.commit()
    return result
