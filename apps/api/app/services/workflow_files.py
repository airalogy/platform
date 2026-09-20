"""Sealed file bindings with live source ACL intersection and private byte access.

Aliases use a deliberately unsupported storage backend. They cannot mint ordinary
object URLs, be copied by legacy import/export code, or delete their source blob.
Only this service resolves them after reauthorizing their immutable lineage.
"""

import hashlib
import tempfile
from contextvars import ContextVar
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from jose import jwt
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import config
from app.libs.file_storage import (
    default_storage_backend,
    default_storage_namespace,
    get_file_with_stream,
    upload_file,
)
from app.models.airalogy_file import AiralogyFile
from app.models.knowledge import ResearchFileBlob
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.research import ResearchAction, ResearchRun, ResearchTask
from app.models.research_asset import ResearchActionOutputSnapshot
from app.models.research_execution import ResearchComputeJob, ResearchComputeJobOutput
from app.models.user import User
from app.models.workflow_file import WorkflowFileBinding
from app.routers.permission import check_user_permission
from app.services.research_runtime import canonical_digest, emit_research_event
from app.services.workflow_file_contracts import parse_workflow_file_id

WORKFLOW_FILE_BACKEND = "workflow_reference"
MAX_WORKFLOW_FILE_BYTES = 256 * 1024 * 1024
FILE_TOKEN_SECONDS = 300
_ACTIVE_FILES = ContextVar("workflow_file_authorization_chain", default=frozenset())


def is_workflow_file(file):
    return file.storage_backend == WORKFLOW_FILE_BACKEND


def blob_snapshot(blob):
    return {
        "id": str(blob.id),
        "sha256": blob.checksum_sha256,
        "size_bytes": blob.size_bytes,
        "content_type": blob.content_type,
        "storage_backend": blob.storage_backend,
        "storage_namespace": blob.storage_namespace,
        "storage_object_key": blob.storage_object_key,
    }


def file_snapshot(file):
    return {
        "id": str(file.id),
        "filename": file.filename,
        "content_type": file.content_type,
        "size_bytes": file.size_bytes,
        "sha256": file.checksum_sha256,
        "protocol_id": str(file.protocol_id),
        "project_id": str(file.project_id),
        "user_id": str(file.user_id),
        "type": file.type,
        "storage": file.storage_location(),
    }


def binding_payload(row):
    result = {
        "schema": "airalogy.workflow-file-binding.v1",
        **{
            key: str(getattr(row, key))
            for key in (
                "file_id",
                "workflow_revision_id",
                "task_id",
                "run_id",
                "action_id",
                "source_action_id",
                "blob_id",
                "created_by_user_id",
            )
        },
        "source_file_id": str(row.source_file_id) if row.source_file_id else None,
        "binding_id": row.binding_id,
        "source_kind": row.source_kind,
        "source_ref": row.source_ref,
        "snapshot": row.snapshot,
    }
    if row.source_kind == "data_asset":
        result["schema"] = "airalogy.workflow-file-binding.v2"
        result["source_action_id"] = None
        result["asset_input_id"] = str(row.asset_input_id)
    return result


def verify_binding_seal(row):
    if row.digest != canonical_digest(binding_payload(row)):
        raise HTTPException(409, "Workflow file binding integrity check failed")


def validate_file_header(handle, filename):
    """Reject common disguised formats; never run parsers or render active content."""
    if (
        not filename
        or len(filename) > 512
        or any(character in filename for character in ("/", "\\", "\x00", "\r", "\n"))
    ):
        raise ValueError("Workflow file requires a safe single-component filename")
    signatures = {
        "pdf": (b"%PDF-",),
        "png": (b"\x89PNG\r\n\x1a\n",),
        "jpg": (b"\xff\xd8\xff",),
        "jpeg": (b"\xff\xd8\xff",),
        "gif": (b"GIF87a", b"GIF89a"),
        "zip": (b"PK\x03\x04", b"PK\x05\x06"),
    }
    header = handle.read(16)
    handle.seek(0)
    expected = signatures.get(filename.rsplit(".", 1)[-1].lower())
    if expected and not any(header.startswith(prefix) for prefix in expected):
        raise ValueError("Workflow file bytes do not match their declared file format")


async def authorized_file(db, file, user):
    """Ordinary protocol ACL plus the immutable alias's live source permissions."""
    protocol = await db.get(Protocol, file.protocol_id)
    project = await db.get(Project, protocol.project_id) if protocol else None
    if (
        protocol is None
        or protocol.deleted_at is not None
        or project is None
        or project.deleted_at is not None
    ):
        raise HTTPException(403, "File context is unavailable")
    await check_user_permission(
        db, project=project, user=user, action="read_protocol", protocol=protocol
    )
    if is_workflow_file(file):
        return await authorize_binding(db, file.id, user)
    return None


async def authorize_binding(db, file_id, user):
    seen = _ACTIVE_FILES.get()
    if file_id in seen or len(seen) >= 64:
        raise HTTPException(409, "Workflow file lineage is cyclic or too deep")
    token = _ACTIVE_FILES.set(seen | {file_id})
    try:
        return await _authorize_binding(db, file_id, user)
    except (KeyError, TypeError, ValueError) as exc:
        # Source resolvers also signal removed/tampered history as a contract
        # error. Every HTTP/SDK/export entry must deny it without leaking a
        # traceback or returning an internal-server error after revocation.
        raise HTTPException(
            409, "Workflow file source is unavailable or its receipt has changed"
        ) from exc
    finally:
        _ACTIVE_FILES.reset(token)


async def _authorize_binding(db, file_id, user):
    if user is None:
        raise HTTPException(403, "Workflow file source permission is required")
    row = await db.get(WorkflowFileBinding, file_id, populate_existing=True)
    file = await db.get(AiralogyFile, file_id, populate_existing=True)
    if row is None or file is None or not is_workflow_file(file):
        raise HTTPException(409, "Workflow file receipt is unavailable")
    verify_binding_seal(row)
    blob = await db.get(ResearchFileBlob, row.blob_id, populate_existing=True)
    if (
        blob is None
        or blob_snapshot(blob) != row.snapshot["blob"]
        or file_snapshot(file) != row.snapshot["file"]
    ):
        raise HTTPException(409, "Workflow file metadata changed after confirmation")
    task = await db.get(ResearchTask, row.task_id)
    run = await db.get(ResearchRun, row.run_id)
    action = await db.get(ResearchAction, row.action_id)
    source = (
        await db.get(ResearchAction, row.source_action_id)
        if row.source_action_id
        else None
    )
    project = await db.get(Project, task.project_id) if task else None
    protocol = await db.get(Protocol, file.protocol_id)
    if (
        run is None
        or action is None
        or (row.source_kind != "data_asset" and source is None)
        or project is None
        or project.deleted_at is not None
        or protocol is None
        or protocol.deleted_at is not None
        or run.task_id != row.task_id
        or action.run_id != run.id
        or (source is not None and source.run_id != run.id)
        or protocol.project_id != project.id
        or (source is not None and source.status != "completed")
        or str(row.workflow_revision_id)
        != ((run.environment_snapshot or {}).get("manual_workflow") or {}).get(
            "revision_id"
        )
    ):
        raise HTTPException(403, "Workflow file source is no longer available")
    await check_user_permission(
        db, project=project, user=user, action="read_protocol", protocol=protocol
    )
    if row.source_kind == "data_asset":
        from app.models.workflow_asset import WorkflowRunAssetInput
        from app.services.workflow_asset_runtime import (
            asset_rows_for_run,
            asset_source_ref,
        )
        from app.services.workflow_assets import authorize_asset_input

        origin = await db.get(
            WorkflowRunAssetInput, row.asset_input_id, populate_existing=True
        )
        selected, _ = await asset_rows_for_run(db, task=task, run=run)
        if (
            origin is None
            or origin.input_id not in selected
            or selected[origin.input_id].id != origin.id
            or origin.run_id != run.id
            or origin.task_id != task.id
            or origin.workflow_revision_id != row.workflow_revision_id
            or origin.blob_id != blob.id
            or row.source_action_id is not None
            or row.source_file_id is not None
            or row.source_ref.get("origin") != asset_source_ref(origin)
            or row.source_ref.get("source_path") != ["file"]
        ):
            raise HTTPException(409, "Workflow DataAsset file lineage changed")
        await authorize_asset_input(db, origin, user)
        return row, file, blob
    from app.services.research_action_outputs import (
        action_output_digest,
        action_output_payload,
        verify_action_output_snapshot,
    )
    from app.services.workflow_visibility import _readable_record

    origin = row.source_ref["origin"]
    snapshot = await db.get(ResearchActionOutputSnapshot, UUID(origin["snapshot_id"]))
    if snapshot is None:
        raise HTTPException(409, "Workflow file source snapshot is missing")
    verify_action_output_snapshot(snapshot)
    if (
        snapshot.action_id != source.id
        or snapshot.digest != origin["snapshot_digest"]
        or snapshot.run_id != run.id
        or snapshot.task_id != task.id
        or action_output_digest(action_output_payload(source, task_id=task.id))
        != snapshot.digest
    ):
        raise HTTPException(409, "Workflow file source receipt changed")
    await _readable_record(db, source=origin, current_user=user, project=project)
    if row.source_kind == "record":
        value = snapshot.output_data["record"]["data"]
        for segment in row.source_ref["source_path"]:
            value = value[segment]
        if parse_workflow_file_id(value)[0] != row.source_file_id:
            raise HTTPException(409, "Workflow source Record file reference changed")
        original = await db.get(
            AiralogyFile, row.source_file_id, populate_existing=True
        )
        if original is None or file_snapshot(original) != row.source_ref["file"]:
            raise HTTPException(409, "Workflow source file changed after binding")
        await authorized_file(db, original, user)
    else:
        await verify_compute_file(db, source, row.source_ref["output"], blob)
    return row, file, blob


async def verify_compute_file(db, source, ref, blob):
    from app.models.analysis import AnalysisRun
    from app.models.workflow_analysis import ResearchAnalysisAction
    from app.services.record_analyses import verify_run_integrity
    from app.services.workflow_compute_runtime import verify_bound_compute

    bridge = await db.get(ResearchAnalysisAction, source.id)
    analysis = await db.get(AnalysisRun, bridge.analysis_run_id) if bridge else None
    output = await db.get(ResearchComputeJobOutput, UUID(ref["id"]))
    job = await db.get(ResearchComputeJob, output.compute_job_id) if output else None
    if (
        analysis is None
        or analysis.status != "succeeded"
        or job is None
        or job.status != "completed"
        or job.analysis_run_id != analysis.id
        or output.registered_at is None
        or output.blob_id != blob.id
        or output.mount_name != ref["mount_name"]
    ):
        raise HTTPException(
            409, "Workflow Compute file is not a sealed completed output"
        )
    verify_run_integrity(analysis)
    await verify_bound_compute(db, analysis)
    if (
        ref not in analysis.result.get("outputs", [])
        or ref.get("checksum_sha256") != blob.checksum_sha256
        or ref.get("byte_size") != blob.size_bytes
    ):
        raise HTTPException(409, "Workflow Compute file receipt changed")


async def verified_blob_spool(blob, *, max_bytes=MAX_WORKFLOW_FILE_BYTES):
    """Verify the complete bounded bytes before disclosing any of the response."""
    if type(blob.size_bytes) is not int or type(max_bytes) is not int:
        raise HTTPException(409, "Workflow file byte receipt is invalid")
    if not 0 <= blob.size_bytes <= max_bytes:
        raise HTTPException(413, "Workflow file exceeds the supported byte limit")
    handle = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    digest, size = hashlib.sha256(), 0
    try:
        async for chunk in get_file_with_stream(
            blob.storage_object_key, backend=blob.storage_backend
        ):
            size += len(chunk)
            if size > blob.size_bytes:
                raise HTTPException(409, "Workflow file bytes changed")
            digest.update(chunk)
            handle.write(chunk)
        if size != blob.size_bytes or digest.hexdigest() != blob.checksum_sha256:
            raise HTTPException(409, "Workflow file checksum changed")
        handle.seek(0)
        return handle
    except BaseException:
        handle.close()
        raise


async def seal_legacy_file(db, file):
    if file.is_external_reference or file.storage_backend not in {"minio", "oss"}:
        raise ValueError(
            "Workflow file binding requires a managed uploaded file, not an external URL"
        )
    handle = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    digest, size = hashlib.sha256(), 0
    try:
        async for chunk in file.get_file_with_stream():
            size += len(chunk)
            if size > MAX_WORKFLOW_FILE_BYTES:
                raise ValueError("Workflow file exceeds the supported byte limit")
            digest.update(chunk)
            handle.write(chunk)
        checksum = digest.hexdigest()
        if (file.size_bytes is not None and file.size_bytes != size) or (
            file.checksum_sha256 and file.checksum_sha256 != checksum
        ):
            raise HTTPException(409, "Workflow source file bytes differ from metadata")
        blob = await db.scalar(
            select(ResearchFileBlob).where(ResearchFileBlob.checksum_sha256 == checksum)
        )
        if blob is None:
            key = f"knowledge/blobs/{checksum[:2]}/{checksum}"
            handle.seek(0)
            await upload_file(
                key,
                handle,
                content_type=file.content_type or "application/octet-stream",
                length=size,
            )
            await db.execute(
                insert(ResearchFileBlob)
                .values(
                    checksum_sha256=checksum,
                    content_type=file.content_type or "application/octet-stream",
                    size_bytes=size,
                    storage_backend=default_storage_backend(),
                    storage_namespace=default_storage_namespace(),
                    storage_object_key=key,
                    extracted_text="",
                )
                .on_conflict_do_nothing(index_elements=["checksum_sha256"])
            )
            blob = await db.scalar(
                select(ResearchFileBlob).where(
                    ResearchFileBlob.checksum_sha256 == checksum
                )
            )
        if blob.size_bytes != size:
            raise HTTPException(409, "Workflow source blob metadata conflicts")
        return blob
    finally:
        handle.close()


async def materialize_file_bindings(
    db, *, task, run, graph, node, action, parents_by_node, sources, outputs
):
    """Create aliases before resolution sealing; only substitute explicitly typed files."""
    values_by_binding = {}
    receipts = []
    bindings = [
        item
        for item in graph.bindings
        if item.target_node_id == node.node_id and item.value_type == "file"
    ]
    for binding in bindings:
        if binding.source_node_id not in outputs:
            raise ValueError("Workflow file binding source branch was not selected")
        source = parents_by_node[binding.source_node_id]
        ref = {
            "origin": deepcopy(sources[binding.source_node_id]),
            "source_path": list(binding.source_path),
            "target_path": list(binding.target_path),
        }
        existing = await db.scalar(
            select(WorkflowFileBinding).where(
                WorkflowFileBinding.action_id == action.id,
                WorkflowFileBinding.binding_id == binding.binding_id,
            )
        )
        if existing is not None:
            raise HTTPException(
                409, "Workflow file binding exists without its resolution"
            )
        original = None
        recipients = [
            await db.get(User, uid)
            for uid in sorted(
                {task.owner_user_id, run.requested_by_user_id, action.assignee_user_id},
                key=str,
            )
        ]
        if any(user is None for user in recipients):
            raise HTTPException(403, "Workflow file recipient is unavailable")
        if source.kind == "protocol_run":
            value = outputs[binding.source_node_id]
            for segment in binding.source_path:
                value = value[segment]
            file_id, extension = parse_workflow_file_id(value)
            original = await db.scalar(
                select(AiralogyFile).where(AiralogyFile.id == file_id).with_for_update()
            )
            if original is None or original.ext != extension:
                raise ValueError("Workflow source FileId has no matching uploaded file")
            source_protocol = await db.get(Protocol, original.protocol_id)
            source_project = (
                await db.get(Project, source_protocol.project_id)
                if source_protocol
                else None
            )
            target_project = await db.get(Project, task.project_id)
            if source_project is None or source_project.lab_id != target_project.lab_id:
                raise ValueError("Workflow file sources must remain in the same Lab")
            for user in recipients:
                await authorized_file(db, original, user)
            ref["file"] = file_snapshot(original)
            if is_workflow_file(original):
                _, _, blob = await authorize_binding(db, original.id, recipients[0])
            else:
                blob = await seal_legacy_file(db, original)
            filename, content_type = original.filename, original.content_type
        else:
            from app.models.analysis import AnalysisRun
            from app.models.workflow_analysis import ResearchAnalysisAction

            source_node = next(
                item for item in graph.nodes if item.node_id == binding.source_node_id
            )
            port = next(
                item
                for item in source_node.compute_file_outputs
                if item.output_id == binding.source_path[1]
            )
            bridge = await db.get(ResearchAnalysisAction, source.id)
            analysis = await db.get(AnalysisRun, bridge.analysis_run_id)
            ref["output"] = next(
                (
                    deepcopy(item)
                    for item in analysis.result.get("outputs", [])
                    if item["mount_name"] == port.mount_name
                ),
                None,
            )
            if ref["output"] is None:
                raise ValueError(
                    "The selected optional Compute output was not produced"
                )
            output = await db.get(ResearchComputeJobOutput, UUID(ref["output"]["id"]))
            blob = await db.get(ResearchFileBlob, output.blob_id)
            await verify_compute_file(db, source, ref["output"], blob)
            filename, content_type = output.mount_name, output.media_type
        spool = await verified_blob_spool(blob)
        try:
            validate_file_header(spool, filename)
        finally:
            spool.close()
        from app.services.knowledge import assert_research_file_upload_quota

        await assert_research_file_upload_quota(
            db, action.assignee_user_id, blob.size_bytes
        )
        file = AiralogyFile(
            id=uuid4(),
            filename=filename,
            content_type=content_type,
            size_bytes=blob.size_bytes,
            checksum_sha256=blob.checksum_sha256,
            protocol_id=node.protocol_id,
            project_id=task.project_id,
            user_id=action.assignee_user_id,
            storage_backend=WORKFLOW_FILE_BACKEND,
        )
        db.add(file)
        await db.flush()
        row = WorkflowFileBinding(
            file_id=file.id,
            workflow_revision_id=UUID(
                run.environment_snapshot["manual_workflow"]["revision_id"]
            ),
            task_id=task.id,
            run_id=run.id,
            action_id=action.id,
            binding_id=binding.binding_id,
            source_action_id=source.id,
            source_file_id=original.id if original else None,
            blob_id=blob.id,
            source_kind="record" if original else "compute",
            source_ref=ref,
            snapshot={"file": file_snapshot(file), "blob": blob_snapshot(blob)},
            created_by_user_id=action.assignee_user_id,
        )
        row.digest = canonical_digest(binding_payload(row))
        db.add(row)
        await db.flush()
        values_by_binding[binding.binding_id] = file.airalogy_id
        receipts.append(
            {
                "binding_id": binding.binding_id,
                "file_id": file.airalogy_id,
                "digest": row.digest,
                "filename": filename,
                "content_type": content_type,
                "size_bytes": blob.size_bytes,
                "sha256": blob.checksum_sha256,
            }
        )
    return values_by_binding, receipts


async def verify_resolution_files(db, *, task, run, action, resolution, user=None):
    refs = resolution.receipt.get("files", [])
    if not isinstance(refs, list):
        raise HTTPException(409, "Workflow file resolution receipt is invalid")
    rows = list(
        (
            await db.scalars(
                select(WorkflowFileBinding).where(
                    WorkflowFileBinding.action_id == action.id
                )
            )
        ).all()
    )
    if len(rows) != len(refs):
        raise HTTPException(409, "Workflow file binding set changed")
    by_id = {item.binding_id: item for item in rows}
    recipients = (
        [user]
        if user
        else [
            await db.get(User, uid)
            for uid in {
                task.owner_user_id,
                run.requested_by_user_id,
                action.assignee_user_id,
            }
        ]
    )
    for ref in refs:
        row = by_id.get(ref.get("binding_id"))
        if (
            row is None
            or row.digest != ref.get("digest")
            or parse_workflow_file_id(ref.get("file_id"))[0] != row.file_id
        ):
            raise HTTPException(409, "Workflow file receipt differs from its binding")
        if (
            resolution.initial_values.get(row.source_ref["target_path"][1])
            != ref["file_id"]
        ):
            raise HTTPException(
                409, "Workflow file input differs from its approved reference"
            )
        for recipient in recipients:
            _, _, blob = await authorize_binding(db, row.file_id, recipient)
        if user is None:
            handle = await verified_blob_spool(blob)
            handle.close()


def file_ids(value):
    if isinstance(value, str) and value.startswith("airalogy.id.file"):
        # The existing browser API reads segment 3, while the SDK model reads
        # the penultimate segment. Both accept UUID spellings beyond the strict
        # Workflow contract. A pasted reference must not escape ACL checks just
        # because it is noncanonical or has extra suffix segments.
        segments = value.split(".")
        candidates = segments[3:4] + segments[-2:-1]
        for candidate in set(candidates):
            try:
                yield UUID(candidate)
            except ValueError:
                continue
    elif isinstance(value, dict):
        for child in value.values():
            yield from file_ids(child)
    elif isinstance(value, list):
        for child in value:
            yield from file_ids(child)


async def authorize_record_files(db, value, user):
    ids = set(file_ids(value))
    if not ids:
        return []
    files = list(
        (
            await db.scalars(
                select(AiralogyFile).where(
                    AiralogyFile.id.in_(ids),
                    AiralogyFile.storage_backend == WORKFLOW_FILE_BACKEND,
                )
            )
        ).all()
    )
    for file in files:
        await authorized_file(db, file, user)
    return files


async def token_for(db, *, purpose, identity, user):
    from app.services.account_security import get_auth_version

    # Deliberately not an access token: no `user` claim accepted by authentication.
    return jwt.encode(
        {
            "aud": "workflow-private-download",
            "purpose": purpose,
            "sub": str(user.id),
            "identity": str(identity),
            "auth_version": await get_auth_version(db, user.id),
            "exp": datetime.now(UTC) + timedelta(seconds=FILE_TOKEN_SECONDS),
        },
        config.SECRET_KEY,
        algorithm="HS256",
    )


async def token_user(db, token, *, purpose, identity):
    from app.services.account_security import get_auth_version

    try:
        payload = jwt.decode(
            token,
            config.SECRET_KEY,
            algorithms=["HS256"],
            audience="workflow-private-download",
        )
        if payload["purpose"] != purpose or payload["identity"] != str(identity):
            raise ValueError("Wrong private download target")
        user = await db.get(User, UUID(payload["sub"]))
        if user is None or payload["auth_version"] != await get_auth_version(
            db, user.id
        ):
            raise ValueError("Stale private download identity")
        return user
    except (jwt.JWTError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(401, "Private file token is invalid or expired") from exc


async def file_reference_payload(db, file, user):
    if not is_workflow_file(file):
        return file.reference_payload(url=await file.local_url())
    await authorized_file(db, file, user)
    token = await token_for(db, purpose="file", identity=file.id, user=user)
    payload = file.reference_payload(
        url=f"/api/workflow-files/{file.id}/preview?token={quote(token)}"
    )
    payload.update(workflow_managed=True, expires_in_seconds=FILE_TOKEN_SECONDS)
    return payload


async def authorize_export_files(db, export, user):
    from app.models.workflow_file import WorkflowFileExportReference

    ids = list(
        (
            await db.scalars(
                select(WorkflowFileExportReference.file_id).where(
                    WorkflowFileExportReference.export_id == export.id
                )
            )
        ).all()
    )
    for file_id in ids:
        await authorize_binding(db, file_id, user)
    return bool(ids)


async def export_download_payload(db, export, user):
    if not await authorize_export_files(db, export, user):
        return None
    token = await token_for(db, purpose="export", identity=export.id, user=user)
    return {
        "url": f"/api/workflow-files/exports/{export.id}/download?token={quote(token)}",
        "expires_in_seconds": FILE_TOKEN_SECONDS,
    }


async def stream_workflow_file(db, file, user, *, inline=False):
    row, _, blob = await authorized_file(db, file, user)
    handle = await verified_blob_spool(blob)
    try:
        # Recheck after storage I/O before returning any verified bytes.
        await authorized_file(db, file, user)
        await emit_research_event(
            db,
            task_id=row.task_id,
            run_id=row.run_id,
            action_id=row.action_id,
            kind="workflow.file_downloaded",
            actor_user_id=user.id,
            payload={"file_id": str(file.id), "sha256": blob.checksum_sha256},
            idempotency_key=f"workflow-file-read:{uuid4()}",
        )
        await db.commit()
    except BaseException:
        handle.close()
        raise

    def chunks():
        try:
            while chunk := handle.read(64 * 1024):
                yield chunk
        finally:
            handle.close()

    safe_inline = inline and file.content_type in {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
    }
    return StreamingResponse(
        chunks(),
        media_type=file.content_type or "application/octet-stream",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'",
            "Content-Disposition": f"{'inline' if safe_inline else 'attachment'}; filename*=UTF-8''{quote(file.filename)}",
            "Content-Length": str(blob.size_bytes),
            "X-Content-SHA256": blob.checksum_sha256,
        },
    )
