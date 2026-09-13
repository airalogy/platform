"""Purpose-scoped preview URLs; every request rechecks the live source ACL."""

from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.database import DBSession
from app.models.airalogy_file import AiralogyFile
from app.services.workflow_files import (
    is_workflow_file,
    stream_workflow_file,
    token_user,
)

router = APIRouter(prefix="/workflow-files", tags=["workflow_files"])


@router.get("/{file_id}/preview")
async def preview_workflow_file(file_id: UUID, token: str, db_session: DBSession):
    user = await token_user(db_session, token, purpose="file", identity=file_id)
    file = await db_session.get(AiralogyFile, file_id)
    if file is None or not is_workflow_file(file):
        raise HTTPException(404, "Workflow file is unavailable")
    return await stream_workflow_file(db_session, file, user, inline=True)


@router.get("/exports/{export_id}/download")
async def download_workflow_record_export(
    export_id: UUID, token: str, db_session: DBSession
):
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from urllib.parse import quote

    from fastapi.responses import StreamingResponse

    from app.models.record_export import RecordExport, RecordExportAuditAction
    from app.routers.record_exports import _reauthorize_export_download
    from app.services.record_exports import add_export_audit
    from app.services.workflow_files import authorize_export_files, verified_blob_spool

    user = await token_user(db_session, token, purpose="export", identity=export_id)
    export = await db_session.get(RecordExport, export_id)
    if export is None or export.requested_by_user_id != user.id:
        raise HTTPException(404, "Record export is unavailable")
    if (
        export.status != "succeeded"
        or not export.output_object_key
        or export.expires_at is None
        or export.expires_at <= datetime.now(UTC)
    ):
        raise HTTPException(409, "Record export has expired or is not complete")
    await _reauthorize_export_download(db_session, export, user.id)
    if not await authorize_export_files(db_session, export, user):
        raise HTTPException(409, "Record export has no protected file manifest")
    handle = await verified_blob_spool(
        SimpleNamespace(
            size_bytes=export.output_size_bytes,
            checksum_sha256=export.checksum_sha256,
            storage_object_key=export.output_object_key,
            storage_backend=export.output_backend,
        ),
        # An archive can contain several independently valid files. Its exact
        # server-generated receipt bounds reads, not the single-file size cap.
        max_bytes=export.output_size_bytes,
    )
    try:
        await _reauthorize_export_download(db_session, export, user.id)
        await add_export_audit(
            db_session,
            export,
            RecordExportAuditAction.DOWNLOADED,
            actor_user_id=user.id,
        )
        await db_session.commit()
    except BaseException:
        handle.close()
        raise

    def chunks():
        try:
            while chunk := handle.read(64 * 1024):
                yield chunk
        finally:
            handle.close()

    return StreamingResponse(
        chunks(),
        media_type=export.output_content_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(export.output_filename)}",
            "Content-Length": str(export.output_size_bytes),
            "X-Content-SHA256": export.checksum_sha256,
        },
    )
