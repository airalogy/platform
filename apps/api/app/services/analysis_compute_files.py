"""Exact private Record attachments for the existing isolated Compute transport.

The approved JSON snapshot stays unchanged. A second, safe JSON mapping names
bounded read-only inputs. Storage locations and alias lineage stay server-side;
deduplicated physical bytes never confer permission to another caller.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from contextvars import ContextVar
from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.models.airalogy_file import AiralogyFile
from app.models.analysis_compute import AnalysisCompute, AnalysisComputeInputFile
from app.models.knowledge import ResearchFileBlob
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.research_execution import ResearchComputeJobInput
from app.services.analysis_compute_contracts import (
    ATTACHMENT_MANIFEST_FILENAME,
    MAX_ANALYSIS_FILE_BYTES,
    MAX_ANALYSIS_INPUT_FILES,
    MAX_ANALYSIS_TOTAL_FILE_BYTES,
)
from app.services.analysis_engine import AnalysisError, canonical_digest
from app.services.workflow_data import protocol_field_catalog
from app.services.workflow_file_contracts import (
    parse_workflow_file_id,
    validate_workflow_file_value,
)
from app.services.workflow_files import (
    authorized_file,
    blob_snapshot,
    file_snapshot,
    is_workflow_file,
    seal_legacy_file,
    validate_file_header,
    verified_blob_spool,
)

ATTACHMENT_SCHEMA = "airalogy.analysis-attachments.v1"
_INPUT_ID = re.compile(r"^[a-z][a-z0-9_]{0,23}$")
_ACTIVE_ANALYSES = ContextVar("analysis_attachment_authorization", default=frozenset())
_PUBLIC_FIELDS = (
    "input_id",
    "field_path",
    "record_id",
    "record_version",
    "record_hash",
    "protocol_version",
    "file_id",
    "filename",
    "media_type",
    "byte_size",
    "checksum_sha256",
    "mount_name",
    "file_metadata_digest",
)


def _invalid(message="Analysis attachment receipt is unavailable or changed"):
    return HTTPException(409, message)


def _declarations(values):
    result = []
    for value in values or []:
        item = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
        if not isinstance(item, dict) or set(item) != {"input_id", "field_path"}:
            raise _invalid("Invalid analysis attachment declaration")
        path = item["field_path"]
        if (
            type(item["input_id"]) is not str
            or not _INPUT_ID.fullmatch(item["input_id"])
            or not isinstance(path, list)
            or len(path) != 2
            or path[0] != "var"
            or type(path[1]) is not str
            or not 1 <= len(path[1]) <= 255
        ):
            raise _invalid("Invalid analysis attachment field or input identifier")
        result.append(deepcopy(item))
    if (
        len(result) > 16
        or len({x["input_id"] for x in result}) != len(result)
        or len({tuple(x["field_path"]) for x in result}) != len(result)
    ):
        raise _invalid("Analysis attachment declarations must be unique and bounded")
    return result


def _catalogs(snapshot):
    if not isinstance(snapshot, dict) or not snapshot.get("records"):
        raise _invalid("Analysis attachment source Records are missing")
    versions = {}
    for row in snapshot.get("schemas", []):
        if not isinstance(row, dict) or row.get("version") in versions:
            raise _invalid("Analysis attachment Schema revisions are ambiguous")
        versions[row.get("version")] = row
    names = {row["protocol_version"] for row in snapshot["records"]}
    if not names or not names <= versions.keys():
        raise _invalid("Analysis attachment Schema revisions are missing")
    return {
        name: protocol_field_catalog(
            SimpleNamespace(version=name, json_schema=versions[name]["json_schema"]),
            include_files=True,
        )
        for name in sorted(names)
    }


def attachment_field_catalog(snapshot):
    """Only explicit FileId fields supported by every selected exact Schema."""
    catalogs = _catalogs(snapshot)
    paths = set.intersection(
        *(
            {path for path, spec in fields.items() if spec.value_type == "file"}
            for fields in catalogs.values()
        )
    )
    result = []
    for path in sorted(paths):
        specs = [fields[path] for fields in catalogs.values()]
        extensions = (
            None
            if any(spec.file_extensions is None for spec in specs)
            else sorted({ext for spec in specs for ext in spec.file_extensions})
        )
        result.append(
            {
                "field_path": list(path),
                "title": path[-1],
                "file_extensions": extensions,
                "nullable": any(spec.nullable for spec in specs),
            }
        )
    return result


def _expected_sources(snapshot, declarations):
    declarations = _declarations(declarations)
    if not declarations:
        return []
    catalogs = _catalogs(snapshot)
    records = snapshot["records"]
    if len(records) * len(declarations) > MAX_ANALYSIS_INPUT_FILES:
        raise HTTPException(
            413, "Select at most 30 Record attachments in one Compute Job"
        )
    result, seen = [], set()
    for record in sorted(records, key=lambda r: (r["record_id"], r["record_version"])):
        identity = UUID(record["record_id"])
        revision = record["record_version"]
        if type(revision) is not int or revision < 1 or (identity, revision) in seen:
            raise _invalid(
                "Analysis attachment Record revisions must be exact and unique"
            )
        seen.add((identity, revision))
        for item in declarations:
            path = item["field_path"]
            spec = catalogs[record["protocol_version"]].get(tuple(path))
            if spec is None or spec.value_type != "file":
                raise _invalid(
                    "Selected attachment field is not an explicit FileId in every Schema"
                )
            try:
                value = record["data"][path[0]][path[1]]
                validate_workflow_file_value(value, spec)
                file_id, extension = parse_workflow_file_id(value)
            except (KeyError, TypeError, ValueError) as exc:
                raise _invalid(
                    "Every selected Record must contain one valid file for each attachment field"
                ) from exc
            result.append(
                {
                    **item,
                    "record_id": str(identity),
                    "record_version": revision,
                    "record_hash": record["record_hash"],
                    "protocol_version": record["protocol_version"],
                    "file_id": str(file_id),
                    "mount_name": f"{item['input_id']}_{identity.hex}_v{revision}.{extension}",
                }
            )
    return result


def manifest_bytes(envelope):
    """A deterministic safe projection, never serialization of server metadata."""
    payload = {
        "schema": ATTACHMENT_SCHEMA,
        "files": [
            {key: row[key] for key in _PUBLIC_FIELDS} for row in envelope["files"]
        ],
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def _envelope(rows):
    result = {
        "schema": ATTACHMENT_SCHEMA,
        "count": len(rows),
        "total_bytes": sum(row["byte_size"] for row in rows),
        "files": rows,
    }
    if result["total_bytes"] > MAX_ANALYSIS_TOTAL_FILE_BYTES:
        raise HTTPException(413, "Analysis attachments exceed the 512 MiB total limit")
    payload = manifest_bytes(result)
    result["manifest"] = {
        "filename": ATTACHMENT_MANIFEST_FILENAME,
        "byte_size": len(payload),
        "checksum_sha256": hashlib.sha256(payload).hexdigest(),
    }
    return result


async def _current_records(db, snapshot, users):
    from app.services.record_analyses import analysis_scope

    protocol_id = UUID(snapshot["protocol_id"])
    scopes = [await analysis_scope(db, protocol_id, user) for user in users]
    for source in snapshot["records"]:
        record = await db.get(
            Record,
            (UUID(source["record_id"]), source["record_version"]),
            populate_existing=True,
        )
        if (
            record is None
            or record.deleted_at is not None
            or record.protocol_id != protocol_id
            or record.hash != source["record_hash"]
            or record.protocol_version != source["protocol_version"]
            or canonical_digest(record.data) != canonical_digest(source["data"])
        ):
            raise _invalid(
                "Analysis attachment source Record is unavailable or changed"
            )
        if any(
            own_only and record.user_id != user.id
            for user, (_, _, own_only) in zip(users, scopes, strict=True)
        ):
            raise HTTPException(
                403, "Analysis attachment source Record is no longer readable"
            )
    for source in snapshot["schemas"]:
        version = await db.get(
            ProtocolVersion, UUID(source["id"]), populate_existing=True
        )
        if (
            version is None
            or version.protocol_id != protocol_id
            or version.version != source["version"]
            or canonical_digest(version.json_schema)
            != canonical_digest(source["json_schema"])
        ):
            raise _invalid(
                "Analysis attachment source Schema is unavailable or changed"
            )


def _readers(user, other_readers):
    users = {item.id: item for item in (user, *other_readers) if item is not None}
    if user is None or len(users) == 0 or any(item is None for item in other_readers):
        raise HTTPException(403, "Analysis attachment reader is unavailable")
    return list(users.values())


async def _source_file(db, source, users):
    file = await db.get(AiralogyFile, UUID(source["file_id"]), populate_existing=True)
    if file is None or file.ext != source["mount_name"].rsplit(".", 1)[-1]:
        raise _invalid("Analysis attachment file is unavailable or changed")
    if file.external_uri or file.storage_backend not in {
        "minio",
        "oss",
        "workflow_reference",
    }:
        raise _invalid("Analysis attachments require managed files, not external URLs")
    binding = None
    for user in users:
        resolved = await authorized_file(db, file, user)
        if is_workflow_file(file):
            if resolved is None:
                raise _invalid()
            binding = resolved
    return file, binding


def _validate_attachment_header(handle, filename):
    try:
        validate_file_header(handle, filename)
    except ValueError as exc:
        # The router deliberately maps AnalysisError to a validation response.
        # Never echo an unsafe filename or an internal storage path to readers.
        raise AnalysisError(
            "Analysis attachment has an unsafe filename or its contents do not match the declared file format"
        ) from exc


async def _file_bytes(file, binding):
    if binding is not None:
        blob = binding[2]
        spool = await verified_blob_spool(blob, max_bytes=MAX_ANALYSIS_FILE_BYTES)
        try:
            _validate_attachment_header(spool, file.filename)
        finally:
            spool.close()
        return blob.size_bytes, blob.checksum_sha256
    digest, size, header = hashlib.sha256(), 0, b""
    async for chunk in file.get_file_with_stream():
        size += len(chunk)
        if size > MAX_ANALYSIS_FILE_BYTES:
            raise HTTPException(
                413, "Analysis attachment exceeds the 256 MiB file limit"
            )
        digest.update(chunk)
        header = (header + chunk)[:16]
    _validate_attachment_header(io.BytesIO(header), file.filename)
    checksum = digest.hexdigest()
    if (file.size_bytes is not None and file.size_bytes != size) or (
        file.checksum_sha256 and file.checksum_sha256 != checksum
    ):
        raise _invalid("Analysis attachment file bytes differ from metadata")
    return size, checksum


async def preview_input_files(db, snapshot, declarations, user, *, other_readers=()):
    if not declarations:
        return None
    sources = _expected_sources(snapshot, declarations)
    users = _readers(user, other_readers)
    await _current_records(db, snapshot, users)
    rows, cached = [], {}
    for source in sources:
        file, binding = await _source_file(db, source, users)
        metadata = file_snapshot(file)
        cache_key = (str(file.id), canonical_digest(metadata))
        if cache_key not in cached:
            cached[cache_key] = await _file_bytes(file, binding)
        size, checksum = cached[cache_key]
        rows.append(
            {
                **source,
                "filename": file.filename,
                "media_type": file.content_type or "application/octet-stream",
                "byte_size": size,
                "checksum_sha256": checksum,
                "file_metadata_digest": canonical_digest(metadata),
            }
        )
        if sum(row["byte_size"] for row in rows) > MAX_ANALYSIS_TOTAL_FILE_BYTES:
            raise HTTPException(
                413, "Analysis attachments exceed the 512 MiB total limit"
            )
    return _envelope(rows)


def _receipt_payload(row):
    return {
        "schema": ATTACHMENT_SCHEMA,
        **{
            key: str(getattr(row, key))
            for key in (
                "input_row_id",
                "analysis_run_id",
                "source_file_id",
                "blob_id",
                "record_id",
            )
        },
        "record_version": row.record_version,
        "input_id": row.input_id,
        "snapshot": row.snapshot,
        "source_metadata": row.source_metadata,
    }


async def materialize_input_files(
    db, *, run, job, recipe, expected, user, other_readers=()
):
    declarations = (
        recipe.get("input_files", [])
        if isinstance(recipe, dict)
        else recipe.input_files
    )
    if not declarations:
        if expected not in (None, {}):
            raise _invalid()
        return None
    sources = _expected_sources(run.source_snapshot, declarations)
    # Freeze exact source metadata before sealing bytes/creating the protected
    # references, in stable order across repeated Records and input fields.
    await db.scalars(
        select(AiralogyFile)
        .where(
            AiralogyFile.id.in_(
                sorted({UUID(source["file_id"]) for source in sources}, key=str)
            )
        )
        .order_by(AiralogyFile.id)
        .with_for_update()
    )
    actual = await preview_input_files(
        db, run.source_snapshot, declarations, user, other_readers=other_readers
    )
    if expected != actual:
        raise _invalid("Analysis attachment preview changed; preview again")
    users = _readers(user, other_readers)
    db.add(
        ResearchComputeJobInput(
            id=uuid4(),
            compute_job_id=job.id,
            analysis_run_id=run.id,
            position=2,
            mount_name=ATTACHMENT_MANIFEST_FILENAME,
        )
    )
    for position, source in enumerate(actual["files"], 3):
        file, binding = await _source_file(db, source, users)
        blob = binding[2] if binding is not None else await seal_legacy_file(db, file)
        if (
            blob.size_bytes != source["byte_size"]
            or blob.checksum_sha256 != source["checksum_sha256"]
            or canonical_digest(file_snapshot(file)) != source["file_metadata_digest"]
        ):
            raise _invalid("Analysis attachment bytes changed during confirmation")
        spool = await verified_blob_spool(blob, max_bytes=MAX_ANALYSIS_FILE_BYTES)
        spool.close()
        input_row = ResearchComputeJobInput(
            id=uuid4(),
            compute_job_id=job.id,
            analysis_run_id=run.id,
            position=position,
            mount_name=source["mount_name"],
        )
        db.add(input_row)
        await db.flush()
        receipt = AnalysisComputeInputFile(
            input_row_id=input_row.id,
            analysis_run_id=run.id,
            source_file_id=file.id,
            blob_id=blob.id,
            record_id=UUID(source["record_id"]),
            record_version=source["record_version"],
            input_id=source["input_id"],
            snapshot=deepcopy(source),
            source_metadata={
                "file": file_snapshot(file),
                "blob": blob_snapshot(blob),
                "binding_digest": binding[0].digest if binding is not None else None,
            },
        )
        receipt.digest = canonical_digest(_receipt_payload(receipt))
        db.add(receipt)
    await db.flush()
    return actual


async def sealed_input_file(db, run, input_row):
    receipt = await db.get(
        AnalysisComputeInputFile, input_row.id, populate_existing=True
    )
    if (
        receipt is None
        or receipt.analysis_run_id != run.id
        or input_row.analysis_run_id != run.id
        or input_row.data_asset_id is not None
        or input_row.data_asset_version_id is not None
    ):
        raise _invalid()
    if receipt.digest != canonical_digest(_receipt_payload(receipt)):
        raise _invalid()
    blob = await db.get(ResearchFileBlob, receipt.blob_id, populate_existing=True)
    source = receipt.snapshot
    if (
        blob is None
        or blob_snapshot(blob) != receipt.source_metadata["blob"]
        or input_row.mount_name != source["mount_name"]
        or str(receipt.record_id) != source["record_id"]
        or receipt.record_version != source["record_version"]
        or receipt.input_id != source["input_id"]
        or str(receipt.source_file_id) != source["file_id"]
        or blob.size_bytes != source["byte_size"]
        or blob.checksum_sha256 != source["checksum_sha256"]
        or canonical_digest(receipt.source_metadata["file"])
        != source["file_metadata_digest"]
    ):
        raise _invalid()
    return receipt, blob


async def verify_input_files(db, *, run, job, inputs, envelope):
    declarations = run.recipe.get("input_files", [])
    rows = sorted(inputs, key=lambda row: row.position)
    if not declarations:
        if envelope not in (None, {}) or len(rows) != 1:
            raise _invalid()
    else:
        sources = _expected_sources(run.source_snapshot, declarations)
        if (
            not isinstance(envelope, dict)
            or envelope != _envelope(envelope.get("files", []))
            or len(sources) != envelope["count"]
            or len(rows) != len(sources) + 2
        ):
            raise _invalid()
        for expected, source in zip(sources, envelope["files"], strict=True):
            if any(source.get(key) != value for key, value in expected.items()):
                raise _invalid()
        if rows[1].mount_name != ATTACHMENT_MANIFEST_FILENAME:
            raise _invalid()
        for input_row, source in zip(rows[2:], envelope["files"], strict=True):
            receipt, _ = await sealed_input_file(db, run, input_row)
            if receipt.snapshot != source:
                raise _invalid()
    if (
        not rows
        or rows[0].mount_name != "records.json"
        or any(
            row.position != position
            or row.compute_job_id != job.id
            or row.analysis_run_id != run.id
            or row.data_asset_id is not None
            or row.data_asset_version_id is not None
            for position, row in enumerate(rows, 1)
        )
    ):
        raise _invalid()


async def authorize_input_files(db, run, user):
    if not run.recipe.get("input_files"):
        return
    active = _ACTIVE_ANALYSES.get()
    if run.id in active or len(active) >= 64:
        raise _invalid("Analysis attachment lineage is cyclic or too deep")
    token = _ACTIVE_ANALYSES.set(active | {run.id})
    try:
        details = await db.get(AnalysisCompute, run.id, populate_existing=True)
        if details is None or not details.input_file_manifest:
            raise _invalid()
        expected = _expected_sources(run.source_snapshot, run.recipe["input_files"])
        envelope = details.input_file_manifest
        if (
            envelope != _envelope(envelope.get("files", []))
            or len(expected) != envelope["count"]
        ):
            raise _invalid()
        await authorize_preview_input_files(db, run.source_snapshot, envelope, user)
        rows = list(
            (
                await db.scalars(
                    select(AnalysisComputeInputFile).where(
                        AnalysisComputeInputFile.analysis_run_id == run.id
                    )
                )
            ).all()
        )
        if len(rows) != len(expected):
            raise _invalid()
        by_source = {
            (str(row.record_id), row.record_version, row.input_id): row for row in rows
        }
        for source, entry in zip(expected, envelope["files"], strict=True):
            if any(entry.get(key) != value for key, value in source.items()):
                raise _invalid()
            receipt = by_source.get(
                (source["record_id"], source["record_version"], source["input_id"])
            )
            input_row = (
                await db.get(ResearchComputeJobInput, receipt.input_row_id)
                if receipt
                else None
            )
            if input_row is None:
                raise _invalid()
            sealed, _ = await sealed_input_file(db, run, input_row)
            if sealed.snapshot != entry:
                raise _invalid()
            file, binding = await _source_file(db, source, [user])
            if (
                file_snapshot(file) != receipt.source_metadata["file"]
                or (binding[0].digest if binding is not None else None)
                != receipt.source_metadata["binding_digest"]
            ):
                raise _invalid()
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise _invalid() from exc
    finally:
        _ACTIVE_ANALYSES.reset(token)


async def authorize_preview_input_files(db, snapshot, envelope, user):
    """Reauthorize a sealed Workflow preview for its actual reader, without I/O."""
    if envelope in (None, {}):
        return
    try:
        if envelope != _envelope(envelope.get("files", [])) or not envelope["files"]:
            raise _invalid()
        declarations = {}
        for source in envelope["files"]:
            item = {"input_id": source["input_id"], "field_path": source["field_path"]}
            if (
                item["input_id"] in declarations
                and declarations[item["input_id"]] != item
            ):
                raise _invalid()
            declarations[item["input_id"]] = item
        sources = _expected_sources(snapshot, list(declarations.values()))
        if len(sources) != len(envelope["files"]):
            raise _invalid()
        users = _readers(user, ())
        await _current_records(db, snapshot, users)
        for source, item in zip(sources, envelope["files"], strict=True):
            if any(item.get(key) != value for key, value in source.items()):
                raise _invalid()
            file, _ = await _source_file(db, source, users)
            if canonical_digest(file_snapshot(file)) != item["file_metadata_digest"]:
                raise _invalid()
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise _invalid() from exc
