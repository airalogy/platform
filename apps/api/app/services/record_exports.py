from __future__ import annotations

import csv
import hashlib
import json
import logging
import re
import shutil
import tempfile
import zipfile
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from airalogy.archive import (
    ARCHIVE_MANIFEST_PATH,
    pack_records_archive,
    validate_archive,
)
from sqlalchemy import and_, cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.libs.file_storage import (
    default_storage_backend,
    delete_file,
    file_object_url,
    upload_file,
)
from app.libs.protocol_agent import prepare_protocol_package
from app.models.airalogy_file import AiralogyFile
from app.models.lab import Lab
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.record_export import (
    RecordExport,
    RecordExportAudit,
    RecordExportAuditAction,
    RecordExportFormat,
    RecordExportStatus,
)
from app.models.user import User

EXPORT_RETENTION_DAYS = 7
EXPORT_PAGE_SIZE = 250
FILE_ID_RE = re.compile(
    r"^airalogy\.id\.file\."
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})(?:\..+)?$"
)
logger = logging.getLogger(__name__)


class RecordExportError(ValueError):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RecordExportError(f"Invalid date '{value}'") from exc


def _scope_conditions(record_export: RecordExport) -> list[Any]:
    snapshot_at = record_export.snapshot_at
    if snapshot_at.tzinfo is not None:
        # Record timestamps are legacy naive datetimes written in the API
        # process timezone. Compare the absolute export instant in that same
        # local representation so a non-UTC deployment does not hide freshly
        # created Records from the snapshot.
        snapshot_at = snapshot_at.astimezone().replace(tzinfo=None)
    conditions: list[Any] = [
        Project.lab_id == record_export.lab_id,
        or_(Project.deleted_at.is_(None), Project.deleted_at > snapshot_at),
        or_(Protocol.deleted_at.is_(None), Protocol.deleted_at > snapshot_at),
        or_(Record.deleted_at.is_(None), Record.deleted_at > snapshot_at),
        Record.created_at <= snapshot_at,
    ]
    if record_export.project_id is not None:
        conditions.append(Project.id == record_export.project_id)
    if record_export.protocol_id is not None:
        conditions.append(Protocol.id == record_export.protocol_id)
    return conditions


def _record_filter_conditions(record_export: RecordExport) -> list[Any]:
    conditions: list[Any] = []

    protocol_version = record_export.options.get("protocol_version")
    if protocol_version:
        conditions.append(Record.protocol_version == protocol_version)

    submitter_user_id = record_export.options.get("submitter_user_id")
    if submitter_user_id:
        conditions.append(Record.user_id == UUID(str(submitter_user_id)))

    record_number = record_export.options.get("record_number")
    if record_number:
        conditions.append(Record.number == int(record_number))

    record_version = record_export.options.get("record_version")
    if record_version:
        conditions.append(Record.version == int(record_version))

    query = record_export.options.get("query")
    if isinstance(query, str) and query.strip():
        search_document = func.record_search_document(
            cast(Record.data, JSONB),
            Record.report,
        )
        conditions.append(
            and_(
                *(
                    search_document.ilike(
                        f"%{_escape_like_pattern(keyword)}%",
                        escape="\\",
                    )
                    for keyword in query.split()
                )
            )
        )

    date_from = _parse_date(record_export.options.get("date_from"))
    if date_from:
        conditions.append(
            Record.created_at >= datetime.combine(date_from, datetime.min.time())
        )
    date_to = _parse_date(record_export.options.get("date_to"))
    if date_to:
        conditions.append(
            Record.created_at
            < datetime.combine(date_to + timedelta(days=1), datetime.min.time())
        )
    return conditions


def _escape_like_pattern(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def record_export_query(record_export: RecordExport):
    scope_conditions = _scope_conditions(record_export)
    record_filters = _record_filter_conditions(record_export)
    if record_export.include_revision_history:
        selected_conditions = [*scope_conditions, *record_filters]
    else:
        latest = (
            select(
                Record.id.label("record_id"),
                func.max(Record.version).label("record_version"),
            )
            .join(Protocol, Protocol.id == Record.protocol_id)
            .join(Project, Project.id == Protocol.project_id)
            .where(*scope_conditions)
            .group_by(Record.id)
            .subquery()
        )
        selected_conditions = [
            Record.id == latest.c.record_id,
            Record.version == latest.c.record_version,
        ]

    query = (
        select(Record, Protocol, Project, Lab, User)
        .join(Protocol, Protocol.id == Record.protocol_id)
        .join(Project, Project.id == Protocol.project_id)
        .join(Lab, Lab.id == Project.lab_id)
        .join(User, User.id == Record.user_id)
    )
    if record_export.include_revision_history:
        query = query.where(*selected_conditions)
    else:
        query = query.join(latest, and_(*selected_conditions)).where(*record_filters)
    return query.order_by(Record.id, Record.version)


async def iter_export_rows(
    db_session: AsyncSession,
    record_export: RecordExport,
) -> AsyncIterator[tuple[Record, Protocol, Project, Lab, User]]:
    offset = 0
    while True:
        rows = (
            await db_session.execute(
                record_export_query(record_export)
                .offset(offset)
                .limit(EXPORT_PAGE_SIZE)
            )
        ).all()
        if not rows:
            return
        for row in rows:
            yield row
        offset += len(rows)


def serialize_record(
    record: Record,
    protocol: Protocol,
    project: Project,
    lab: Lab,
    user: User,
) -> dict[str, Any]:
    return {
        "format": "airalogy.record",
        "schema_version": 1,
        "airalogy_record_id": record.airalogy_id,
        "record_id": str(record.id),
        "record_version": record.version,
        "metadata": {
            "airalogy_protocol_id": (
                f"airalogy.id.lab.{lab.uid}.project.{project.uid}."
                f"protocol.{protocol.uid}.v.{record.protocol_version}"
            ),
            "protocol_id": protocol.uid,
            "protocol_uuid": str(protocol.id),
            "protocol_version": record.protocol_version,
            "record_current_version_submission_time": record.created_at.isoformat(),
            "record_current_version_submission_user_id": str(record.user_id),
            "record_current_version_submission_username": user.username,
            "lab_id": lab.uid,
            "project_id": project.uid,
            "record_num": record.number,
            "sha1": record.hash,
            "revision_kind": record.revision_kind,
            "revision_reason": record.revision_reason,
            "source_protocol_version": record.source_protocol_version,
            "migration_run_id": (
                str(record.migration_run_id) if record.migration_run_id else None
            ),
        },
        "data": record.data,
        "report": record.report,
    }


def _walk_file_ids(value: Any, path: str = "data"):
    if isinstance(value, str):
        match = FILE_ID_RE.match(value)
        if match:
            yield UUID(match.group(1)), value, path
        return
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk_file_ids(item, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_file_ids(item, f"{path}.{index}")


async def preview_record_export(
    db_session: AsyncSession,
    record_export: RecordExport,
) -> dict[str, Any]:
    record_count = 0
    protocol_versions: set[tuple[UUID, str]] = set()
    file_ids: set[UUID] = set()
    async for record, protocol, _, _, _ in iter_export_rows(db_session, record_export):
        record_count += 1
        protocol_versions.add((protocol.id, record.protocol_version))
        file_ids.update(file_id for file_id, _, _ in _walk_file_ids(record.data))

    files: list[AiralogyFile] = []
    if file_ids:
        files = list(
            (
                await db_session.scalars(
                    select(AiralogyFile).where(AiralogyFile.id.in_(file_ids))
                )
            ).all()
        )
    found_ids = {item.id for item in files}
    warnings: list[dict[str, Any]] = []
    missing = sorted(str(file_id) for file_id in file_ids - found_ids)
    if missing:
        warnings.append({"code": "missing_attachments", "file_ids": missing})
    external = [item.airalogy_id for item in files if item.is_external_reference]
    if external:
        warnings.append(
            {"code": "external_attachments_not_embedded", "file_ids": external}
        )

    protocol_version_names = sorted({version for _, version in protocol_versions})
    return {
        "record_count": record_count,
        "protocol_count": len({protocol_id for protocol_id, _ in protocol_versions}),
        "protocol_version_count": len(protocol_versions),
        "protocol_versions": protocol_version_names,
        "attachment_count": len(file_ids),
        "attachment_bytes": sum(item.size_bytes or 0 for item in files),
        "csv_eligible": (
            record_export.scope_type == "protocol" and len(protocol_versions) == 1
        ),
        "warnings": warnings,
    }


async def add_export_audit(
    db_session: AsyncSession,
    record_export: RecordExport,
    action: RecordExportAuditAction | str,
    *,
    actor_user_id: UUID | None = None,
    details: dict[str, Any] | None = None,
) -> RecordExportAudit:
    # Serialize the per-export sequence counter so concurrent downloads or
    # worker transitions cannot produce duplicate immutable audit positions.
    await db_session.execute(
        select(RecordExport.id)
        .where(RecordExport.id == record_export.id)
        .with_for_update()
    )
    next_sequence = (
        await db_session.scalar(
            select(func.coalesce(func.max(RecordExportAudit.sequence), 0) + 1).where(
                RecordExportAudit.export_id == record_export.id
            )
        )
    ) or 1
    audit = RecordExportAudit(
        export_id=record_export.id,
        lab_id=record_export.lab_id,
        actor_user_id=actor_user_id,
        action=str(action),
        sequence=next_sequence,
        details=details or {},
    )
    db_session.add(audit)
    await db_session.flush()
    return audit


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return cleaned or "records"


def _output_filename(
    record_export: RecordExport,
    lab: Lab,
    project: Project | None,
    protocol: Protocol | None,
) -> str:
    parts = [lab.uid]
    if project is not None:
        parts.append(project.uid)
    if protocol is not None:
        parts.append(protocol.uid)
    parts.extend(
        [
            "records",
            record_export.snapshot_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ"),
        ]
    )
    return f"{_safe_filename('-'.join(parts))}.{record_export.export_format}"


async def _prepare_protocol_dirs(
    db_session: AsyncSession,
    versions: set[tuple[UUID, str]],
) -> list[Path]:
    result: list[Path] = []
    for protocol_id, version in sorted(
        versions, key=lambda item: (str(item[0]), item[1])
    ):
        protocol_version = await ProtocolVersion.find_by(
            db_session,
            [
                ProtocolVersion.protocol_id == protocol_id,
                ProtocolVersion.version == version,
            ],
        )
        if protocol_version is None:
            raise RecordExportError(
                f"Protocol version {protocol_id}@{version} was not found"
            )
        await prepare_protocol_package(protocol_version)
        result.append(Path(config.PROTOCOL_DIR) / protocol_version.package_name)
    return result


async def _file_payload_specs(
    db_session: AsyncSession,
    record_paths: list[Path],
    directory: Path,
    *,
    include_attachments: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    occurrences: list[tuple[Path, str, int, UUID, str, str]] = []
    for record_path in record_paths:
        payload = json.loads(record_path.read_text(encoding="utf-8"))
        record_id = str(payload["record_id"])
        record_version = int(payload["record_version"])
        occurrences.extend(
            (
                record_path,
                record_id,
                record_version,
                file_id,
                airalogy_id,
                field_path,
            )
            for file_id, airalogy_id, field_path in _walk_file_ids(payload["data"])
        )
    if not occurrences:
        return [], []

    file_ids = {item[3] for item in occurrences}
    files = list(
        (
            await db_session.scalars(
                select(AiralogyFile).where(AiralogyFile.id.in_(file_ids))
            )
        ).all()
    )
    files_by_id = {item.id: item for item in files}
    local_paths: dict[UUID, Path] = {}
    warnings: list[dict[str, Any]] = []
    specs: list[dict[str, Any]] = []

    for (
        record_path,
        record_id,
        record_version,
        file_id,
        airalogy_id,
        field_path,
    ) in occurrences:
        stored = files_by_id.get(file_id)
        if stored is None:
            warnings.append(
                {
                    "code": "missing_attachment",
                    "file_id": airalogy_id,
                    "record_id": record_id,
                    "record_version": record_version,
                    "field_path": field_path,
                }
            )
            continue
        spec: dict[str, Any] = {
            "file_id": stored.airalogy_id,
            "filename": stored.filename,
            "mime_type": stored.content_type,
            "source_path": record_path.name,
            "source_index": 1,
            "field_path": field_path,
        }
        if stored.is_external_reference:
            spec["source_uri"] = stored.external_uri
            warnings.append(
                {
                    "code": "external_attachment_not_embedded",
                    "file_id": stored.airalogy_id,
                }
            )
        elif include_attachments:
            local_path = local_paths.get(stored.id)
            if local_path is None:
                local_path = (
                    directory / "attachments" / str(stored.id) / stored.filename
                )
                local_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    await stored.download_file(str(local_path))
                except Exception as exc:  # noqa: BLE001 - storage adapters vary
                    warnings.append(
                        {
                            "code": "attachment_download_failed",
                            "file_id": stored.airalogy_id,
                            "message": str(exc),
                        }
                    )
                    local_path = None
                if local_path is not None:
                    local_paths[stored.id] = local_path
            if local_path is not None:
                spec["path"] = str(local_path)
        specs.append(spec)
    return specs, warnings


def _csv_cell(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if value is None:
        return ""
    return value


def _flatten_csv_data(value: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for section, section_value in value.items():
        if isinstance(section_value, dict):
            for key, item in section_value.items():
                flattened[f"{section}.{key}"] = _csv_cell(item)
        else:
            flattened[section] = _csv_cell(section_value)
    return flattened


def _sha256_and_size(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _aira_blob_path(sha256: str) -> str:
    return f"blobs/sha256/{sha256[:2]}/{sha256[2:4]}/{sha256}"


def _pack_records_archive_streaming_files(
    record_paths: list[Path],
    output_path: Path,
    *,
    protocol_dirs: list[Path],
    file_payloads: list[dict[str, Any]],
) -> None:
    """Pack attachment blobs without retaining their contents in memory.

    Airalogy's public packer is still used to validate and assemble the
    canonical archive. Local file paths are added in a second streaming pass,
    while the corresponding standard manifest entries are populated with the
    same content-addressed blob metadata.
    """
    manifest_specs = [
        {key: value for key, value in spec.items() if key != "path"}
        for spec in file_payloads
    ]
    pack_records_archive(
        record_paths,
        output_path,
        protocol_dirs=protocol_dirs,
        file_payloads=manifest_specs,
        force=True,
    )

    with zipfile.ZipFile(output_path) as archive:
        manifest = json.loads(archive.read(ARCHIVE_MANIFEST_PATH))
    manifest_files = manifest.get("files") or []
    if len(manifest_files) != len(file_payloads):
        raise RecordExportError(
            "Generated .aira file manifest does not match attachment payloads"
        )

    fingerprints: dict[Path, tuple[str, int]] = {}
    blob_sources: dict[str, tuple[Path, str]] = {}
    blob_entries: dict[str, dict[str, Any]] = {}
    for spec, file_entry in zip(file_payloads, manifest_files, strict=True):
        local_path_value = spec.get("path")
        if not isinstance(local_path_value, str) or not local_path_value:
            continue
        local_path = Path(local_path_value)
        if not local_path.is_file():
            raise RecordExportError(f"Attachment file '{local_path}' was not found")
        fingerprint = fingerprints.get(local_path)
        if fingerprint is None:
            fingerprint = _sha256_and_size(local_path)
            fingerprints[local_path] = fingerprint
        sha256, size = fingerprint
        blob_id = f"sha256:{sha256}"
        archive_path = _aira_blob_path(sha256)
        file_entry["blob_id"] = blob_id
        file_entry["size"] = size
        blob_sources.setdefault(blob_id, (local_path, archive_path))
        blob_entries.setdefault(
            blob_id,
            {
                "blob_id": blob_id,
                "archive_path": archive_path,
                "sha256": sha256,
                "size": size,
            },
        )

    if not blob_sources:
        return
    manifest["files"] = manifest_files
    manifest["blobs"] = list(blob_entries.values())

    rewritten_path = output_path.with_name(f".{output_path.name}.streaming")
    try:
        with (
            zipfile.ZipFile(output_path, "r") as source_archive,
            zipfile.ZipFile(
                rewritten_path,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                allowZip64=True,
            ) as target_archive,
        ):
            for member in source_archive.infolist():
                if member.filename == ARCHIVE_MANIFEST_PATH:
                    continue
                if member.is_dir():
                    target_archive.writestr(member, b"")
                    continue
                with (
                    source_archive.open(member) as source,
                    target_archive.open(member, "w", force_zip64=True) as target,
                ):
                    shutil.copyfileobj(source, target, length=1024 * 1024)
            target_archive.writestr(
                ARCHIVE_MANIFEST_PATH,
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            )
            for local_path, archive_path in blob_sources.values():
                target_archive.write(local_path, archive_path)
        rewritten_path.replace(output_path)
    finally:
        rewritten_path.unlink(missing_ok=True)


async def _write_export_file(
    db_session: AsyncSession,
    record_export: RecordExport,
    directory: Path,
) -> tuple[Path, list[dict[str, Any]]]:
    record_paths: list[Path] = []
    protocol_versions: set[tuple[UUID, str]] = set()
    csv_fields: set[str] = set()
    output_path = directory / f"records.{record_export.export_format}"
    csv_rows_path = directory / "csv-rows.jsonl"
    jsonl_output = (
        output_path.open("w", encoding="utf-8")
        if record_export.export_format == RecordExportFormat.JSONL.value
        else None
    )
    csv_rows_output = (
        csv_rows_path.open("w", encoding="utf-8")
        if record_export.export_format == RecordExportFormat.CSV.value
        else None
    )
    processed = 0

    async for record, protocol, project, lab, user in iter_export_rows(
        db_session, record_export
    ):
        payload = serialize_record(record, protocol, project, lab, user)
        protocol_versions.add((protocol.id, record.protocol_version))
        processed += 1

        if record_export.export_format == RecordExportFormat.AIRA.value:
            record_path = (
                directory / "records-json" / f"{record.id}.v{record.version}.json"
            )
            record_path.parent.mkdir(parents=True, exist_ok=True)
            record_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            record_paths.append(record_path)
        elif record_export.export_format == RecordExportFormat.JSONL.value:
            assert jsonl_output is not None
            jsonl_output.write(json.dumps(payload, ensure_ascii=False) + "\n")
        else:
            row = {
                "record_id": str(record.id),
                "record_version": record.version,
                "protocol_id": protocol.uid,
                "protocol_version": record.protocol_version,
                "submitted_at": record.created_at.isoformat(),
                "submitted_by": user.username,
                "record_number": record.number,
                "sha1": record.hash,
                "report": record.report,
                **_flatten_csv_data(record.data),
            }
            csv_fields.update(row)
            assert csv_rows_output is not None
            csv_rows_output.write(json.dumps(row, ensure_ascii=False) + "\n")
        record_export.progress_current = processed
        if processed % EXPORT_PAGE_SIZE == 0:
            await db_session.commit()
            await db_session.refresh(record_export)
            if record_export.status == RecordExportStatus.CANCELLED.value:
                raise RecordExportError("Record export was cancelled")

    if jsonl_output is not None:
        jsonl_output.close()
    if csv_rows_output is not None:
        csv_rows_output.close()

    if not processed:
        raise RecordExportError("No Records matched the export scope")

    if record_export.export_format == RecordExportFormat.AIRA.value:
        protocol_dirs = await _prepare_protocol_dirs(db_session, protocol_versions)
        file_payloads, warnings = await _file_payload_specs(
            db_session,
            record_paths,
            directory,
            include_attachments=record_export.include_attachments,
        )
        _pack_records_archive_streaming_files(
            record_paths,
            output_path,
            protocol_dirs=protocol_dirs,
            file_payloads=file_payloads,
        )
        export_manifest = {
            "format": "airalogy.platform.record-export",
            "version": 1,
            "export_id": str(record_export.id),
            "scope": {
                "type": record_export.scope_type,
                "lab_id": str(record_export.lab_id),
                "project_id": (
                    str(record_export.project_id) if record_export.project_id else None
                ),
                "protocol_id": (
                    str(record_export.protocol_id)
                    if record_export.protocol_id
                    else None
                ),
            },
            "snapshot_at": record_export.snapshot_at.isoformat(),
            "generated_at": utcnow().isoformat(),
            "options": {
                **record_export.options,
                "include_revision_history": record_export.include_revision_history,
                "include_attachments": record_export.include_attachments,
            },
            "statistics": {
                "records": processed,
                "protocol_versions": len(protocol_versions),
                "attachments": record_export.attachment_count or 0,
                "attachment_bytes": record_export.attachment_bytes or 0,
            },
            "warnings": [*(record_export.warnings or []), *warnings],
        }
        with zipfile.ZipFile(
            output_path, "a", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            archive.writestr(
                "platform/export-manifest.json",
                json.dumps(export_manifest, indent=2, ensure_ascii=False) + "\n",
            )
        valid, issues = validate_archive(output_path)
        if not valid:
            raise RecordExportError(
                "Generated .aira archive failed validation: " + "; ".join(issues)
            )
        return output_path, warnings

    if record_export.export_format == RecordExportFormat.CSV.value:
        if len(protocol_versions) != 1:
            raise RecordExportError(
                "CSV export requires exactly one Protocol and Protocol version"
            )
        preferred = [
            "record_id",
            "record_version",
            "protocol_id",
            "protocol_version",
            "submitted_at",
            "submitted_by",
            "record_number",
            "sha1",
            "report",
        ]
        fields = preferred + sorted(csv_fields - set(preferred))
        with output_path.open("w", encoding="utf-8-sig", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            with csv_rows_path.open(encoding="utf-8") as csv_rows_input:
                for line in csv_rows_input:
                    writer.writerow(json.loads(line))
    return output_path, []


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def process_record_export(
    db_session: AsyncSession,
    export_id: UUID,
) -> dict[str, Any]:
    record_export = await db_session.get(RecordExport, export_id)
    if record_export is None:
        raise RecordExportError("Record export was not found")
    if record_export.status == RecordExportStatus.CANCELLED.value:
        return {"cancelled": True}
    if record_export.status == RecordExportStatus.SUCCEEDED.value:
        return {"record_count": record_export.record_count, "already_completed": True}

    record_export.status = RecordExportStatus.RUNNING.value
    record_export.started_at = utcnow()
    record_export.error = None
    await add_export_audit(db_session, record_export, RecordExportAuditAction.STARTED)
    preview = await preview_record_export(db_session, record_export)
    record_export.progress_total = preview["record_count"]
    record_export.record_count = preview["record_count"]
    record_export.protocol_count = preview["protocol_count"]
    record_export.attachment_count = preview["attachment_count"]
    record_export.attachment_bytes = preview["attachment_bytes"]
    record_export.warnings = preview["warnings"]
    await db_session.commit()

    lab = await db_session.get(Lab, record_export.lab_id)
    project = (
        await db_session.get(Project, record_export.project_id)
        if record_export.project_id
        else None
    )
    protocol = (
        await db_session.get(Protocol, record_export.protocol_id)
        if record_export.protocol_id
        else None
    )
    if lab is None:
        raise RecordExportError("Export Lab was not found")

    with tempfile.TemporaryDirectory(prefix="airalogy_record_export_") as tmp_name:
        output_path, generation_warnings = await _write_export_file(
            db_session, record_export, Path(tmp_name)
        )
        await db_session.refresh(record_export)
        if record_export.status == RecordExportStatus.CANCELLED.value:
            return {"cancelled": True}

        checksum = _sha256_file(output_path)
        filename = _output_filename(record_export, lab, project, protocol)
        object_key = (
            f"record-exports/{record_export.lab_id}/{record_export.id}/{filename}"
        )
        content_type = {
            "aira": "application/vnd.airalogy.aira+zip",
            "jsonl": "application/x-ndjson",
            "csv": "text/csv; charset=utf-8",
        }[record_export.export_format]
        await upload_file(
            object_key,
            str(output_path),
            content_type=content_type,
        )
        # The user can cancel while object storage is receiving a large file.
        # Lock and re-read the export before publishing the output metadata so
        # cancellation either wins (and the just-uploaded object is removed)
        # or waits until the completed state is committed.
        await db_session.refresh(record_export, with_for_update=True)
        if record_export.status == RecordExportStatus.CANCELLED.value:
            await delete_file(object_key, backend=default_storage_backend())
            return {"cancelled": True}
        record_export.output_backend = default_storage_backend()
        record_export.output_object_key = object_key
        record_export.output_filename = filename
        record_export.output_content_type = content_type
        record_export.output_size_bytes = output_path.stat().st_size
        record_export.checksum_sha256 = checksum

    record_export.warnings = [*record_export.warnings, *generation_warnings]
    record_export.status = RecordExportStatus.SUCCEEDED.value
    record_export.progress_current = record_export.record_count
    record_export.finished_at = utcnow()
    record_export.expires_at = record_export.finished_at + timedelta(
        days=EXPORT_RETENTION_DAYS
    )
    await add_export_audit(
        db_session,
        record_export,
        RecordExportAuditAction.COMPLETED,
        details={
            "record_count": record_export.record_count,
            "output_size_bytes": record_export.output_size_bytes,
            "checksum_sha256": record_export.checksum_sha256,
        },
    )
    await db_session.flush()
    return {
        "record_count": record_export.record_count,
        "output_size_bytes": record_export.output_size_bytes,
        "warnings": record_export.warnings,
    }


async def mark_record_export_failed(
    db_session: AsyncSession,
    export_id: UUID,
    error: str,
) -> None:
    record_export = await db_session.get(RecordExport, export_id)
    if (
        record_export is None
        or record_export.status == RecordExportStatus.CANCELLED.value
    ):
        return
    record_export.status = RecordExportStatus.FAILED.value
    record_export.error = error
    record_export.finished_at = utcnow()
    await add_export_audit(
        db_session,
        record_export,
        RecordExportAuditAction.FAILED,
        details={"error": error},
    )


async def expire_record_exports(db_session: AsyncSession) -> int:
    expired = list(
        (
            await db_session.scalars(
                select(RecordExport).where(
                    RecordExport.status == RecordExportStatus.SUCCEEDED.value,
                    RecordExport.expires_at.is_not(None),
                    RecordExport.expires_at <= utcnow(),
                )
            )
        ).all()
    )
    for record_export in expired:
        if record_export.output_object_key:
            try:
                await delete_file(
                    record_export.output_object_key,
                    backend=record_export.output_backend,
                )
            except Exception:
                logger.warning(
                    "Failed to delete expired Record export object %s",
                    record_export.id,
                    exc_info=True,
                )
                continue
        record_export.output_object_key = None
        record_export.status = RecordExportStatus.EXPIRED.value
        await add_export_audit(
            db_session, record_export, RecordExportAuditAction.EXPIRED
        )
    return len(expired)


async def record_export_download_url(record_export: RecordExport) -> str:
    if (
        record_export.status != RecordExportStatus.SUCCEEDED.value
        or not record_export.output_object_key
        or not record_export.expires_at
        or record_export.expires_at <= utcnow()
    ):
        raise RecordExportError("Record export is not available for download")
    return await file_object_url(
        record_export.output_object_key,
        expires=1,
        backend=record_export.output_backend,
        download_name=record_export.output_filename,
    )
