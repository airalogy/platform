import mimetypes
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.params import Body
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field, StringConstraints

from app.database import DBSession
from app.models.airalogy_file import AiralogyFile
from app.models.project import Project
from app.models.protocol import Protocol
from app.routers.permission import check_user_permission
from app.routers.utils import UUIDStr

from .depends import CurrentUser, get_current_user

router = APIRouter(
    prefix="/airalogy_files",
    tags=["airalogy_files"],
    dependencies=[Depends(get_current_user)],
)

# format: airalogy.id.file.uuid.ext
type AIRALOGY_FILE_ID = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=36,
        pattern=r"^airalogy\.id\.file\.([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.(.*)$",
    ),
]


class RegisterExternalAiralogyFilePayload(BaseModel):
    protocol_id: UUIDStr
    filename: str = Field(min_length=1, max_length=512)
    external_uri: str = Field(min_length=1, max_length=2048)
    storage_backend: str = Field(default="external", min_length=1, max_length=32)
    storage_namespace: str | None = Field(default=None, max_length=256)
    content_type: str | None = Field(default=None, max_length=256)
    size_bytes: int | None = Field(default=None, ge=0)
    sha256: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-fA-F]{64}$",
    )
    metadata: dict | None = None


def _normalize_airalogy_file_id(id: UUIDStr | AIRALOGY_FILE_ID) -> str:
    if isinstance(id, str) and id.startswith("airalogy.id.file."):
        return id.split(".")[3]
    return str(id)


async def _get_authorized_file(
    id: UUIDStr | AIRALOGY_FILE_ID,
    db_session: DBSession,
    current_user: CurrentUser,
):
    file = await AiralogyFile.find(db_session, id=_normalize_airalogy_file_id(id))
    protocol = await Protocol.find(db_session, id=file.protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="read_protocol",
        protocol=protocol,
    )
    return file


@router.post("")
async def upload_airalogy_file(
    db_session: DBSession,
    current_user: CurrentUser,
    file: UploadFile,
    protocol_id: Annotated[UUIDStr, Body()],
):
    protocol = await Protocol.find(db_session, id=protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="create_record",
        protocol=protocol,
    )

    filename = file.filename or "uploaded-file"
    airalogy_file = AiralogyFile(
        filename=filename,
        content_type=file.content_type,
        size_bytes=file.size,
        protocol_id=protocol_id,
        project_id=protocol.project_id,
        user_id=current_user.id,
    )
    db_session.add(airalogy_file)
    await db_session.flush()
    await airalogy_file.save_file(
        file=file.file, content_type=file.content_type, length=file.size
    )
    await db_session.commit()
    url = await airalogy_file.local_url()
    return airalogy_file.reference_payload(url=url)


@router.post("/register")
async def register_external_airalogy_file(
    params: RegisterExternalAiralogyFilePayload,
    db_session: DBSession,
    current_user: CurrentUser,
):
    protocol = await Protocol.find(db_session, id=params.protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="create_record",
        protocol=protocol,
    )

    content_type = params.content_type or mimetypes.guess_type(params.filename)[0]
    airalogy_file = AiralogyFile(
        filename=params.filename,
        content_type=content_type,
        size_bytes=params.size_bytes,
        checksum_sha256=params.sha256.lower() if params.sha256 else None,
        protocol_id=params.protocol_id,
        project_id=protocol.project_id,
        user_id=current_user.id,
    )
    airalogy_file.set_external_storage_location(
        external_uri=params.external_uri,
        backend=params.storage_backend,
        namespace=params.storage_namespace,
        metadata=params.metadata,
    )
    db_session.add(airalogy_file)
    await db_session.commit()
    return airalogy_file.reference_payload(url=await airalogy_file.local_url())


@router.get("/{id}")
async def get_airalogy_file_url(
    id: UUIDStr | AIRALOGY_FILE_ID,
    db_session: DBSession,
    current_user: CurrentUser,
):
    file = await _get_authorized_file(id, db_session, current_user)
    url = await file.local_url()
    return file.reference_payload(url=url)


@router.get("/{id}/url")
async def resolve_airalogy_file_url(
    id: UUIDStr | AIRALOGY_FILE_ID,
    db_session: DBSession,
    current_user: CurrentUser,
    expires: int = 24,
):
    file = await _get_authorized_file(id, db_session, current_user)
    url = await file.local_url(expires=expires)
    return file.reference_payload(url=url)


@router.get("/{id}/download", response_class=StreamingResponse)
async def download_airalogy_file(
    id: UUIDStr | AIRALOGY_FILE_ID,
    db_session: DBSession,
    current_user: CurrentUser,
):
    file = await _get_authorized_file(id, db_session, current_user)
    if file.external_uri:
        if file.external_uri.startswith(("http://", "https://")):
            return RedirectResponse(file.external_uri)
        raise HTTPException(
            status_code=501,
            detail="External storage backend requires a download resolver.",
        )

    media_type = file.content_type or mimetypes.guess_type(file.filename)[0]
    return StreamingResponse(
        content=file.get_file_with_stream(),
        media_type=media_type,
        headers={"content-disposition": f'attachment; filename="{file.filename}"'},
    )


@router.put("/{id}/rename")
async def update_airalogy_file_url(
    id: UUIDStr | AIRALOGY_FILE_ID,
    filename: str,
    db_session: DBSession,
    current_user: CurrentUser,
):
    file = await AiralogyFile.find(db_session, id=_normalize_airalogy_file_id(id))
    if file.user_id != current_user.id:
        raise HTTPException(status_code=400, detail="Permission denied")

    file.filename = filename
    file.content_type = mimetypes.guess_type(filename)[0] or file.content_type
    await db_session.commit()
    url = await file.local_url()
    return file.reference_payload(url=url)
