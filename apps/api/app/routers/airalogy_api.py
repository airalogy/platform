import mimetypes
from typing import Annotated, List
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.params import Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import config
from app.database import DBSession
from app.libs.aes_crypt import aes_decrypt
from app.models.airalogy_file import AiralogyFile
from app.models.lab import Lab
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.record import Record
from app.models.user import User
from app.routers.permission import check_user_permission


async def get_current_user(
    db_session: DBSession,
    airalogy_api_key: Annotated[str | None, Header()],
) -> User:
    try:
        str = aes_decrypt(airalogy_api_key, config.AES_KEY)
        id, secret = str.split(",")
        user = await User.find_by(
            db_session,
            [
                User.id == UUID(id),
                User.api_key_iv == secret,
            ],
        )
        if user is None:
            raise ValueError("Invalid api key")
    except Exception as e:
        print("invalid api key:", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_protocol(
    db_session: DBSession, airalogy_protocol_id: str
) -> Protocol:
    short_prefix = "airalogy.id.protocol."
    if airalogy_protocol_id.startswith(short_prefix):
        protocol_uuid = airalogy_protocol_id.removeprefix(short_prefix)
        try:
            protocol = await Protocol.find(db_session, UUID(protocol_uuid))
        except ValueError as err:
            raise HTTPException(
                status_code=404,
                detail=f"Invalid protocol id: #{airalogy_protocol_id}",
            ) from err
        if protocol is None:
            raise HTTPException(
                status_code=404,
                detail=f"Invalid protocol id: #{airalogy_protocol_id}",
            )
        return protocol

    # airalogy_protocol_id format: airalogy.id.lab.<lab_id>.project.<project_id>.protocol.<protocol_id>.v.<version>
    if not airalogy_protocol_id.startswith("airalogy.id.lab"):
        raise HTTPException(
            status_code=404, detail=f"Invalid protocol id: {airalogy_protocol_id}"
        )
    ary = airalogy_protocol_id.split(".")
    if len(ary) < 12:
        raise HTTPException(
            status_code=404,
            detail=f"Invalid protocol id: #{airalogy_protocol_id}",
        )
    lab_uid = ary[3]
    project_uid = ary[5]
    protocol_uid = ary[7]
    # version = f"{ary[9]}.{ary[10]}.{ary[11]}"
    lab = await Lab.find_by(db_session, [Lab.uid == lab_uid])
    if lab is None:
        raise HTTPException(
            status_code=404,
            detail=f"Invalid protocol id: #{airalogy_protocol_id}",
        )
    proj = await Project.find_by(
        db_session, [Project.uid == project_uid, Project.lab_id == lab.id]
    )

    if proj is None:
        raise HTTPException(
            status_code=404,
            detail=f"Invalid protocol id: #{airalogy_protocol_id}",
        )

    protocol = await Protocol.find_by(
        db_session,
        [
            Protocol.uid == protocol_uid,
            Protocol.project_id == proj.id,
            Protocol.deleted_at.is_(None),
        ],
    )
    if protocol is None:
        raise HTTPException(
            status_code=404,
            detail=f"Invalid protocol id: #{airalogy_protocol_id}",
        )
    return protocol


async def get_record(
    db_session: DBSession, current_user: User, airalogy_record_id: str
):
    # record_airalogy_id: airalogy.id.record.<uuid> or airalogy.id.record.<uuid>.v.<version>
    if not airalogy_record_id.startswith("airalogy.id.record."):
        raise HTTPException(
            status_code=404,
            detail=f"Invalid record id: #{airalogy_record_id}",
        )

    # Extract the record ID, handling both formats
    parts = airalogy_record_id.split(".")
    if len(parts) < 4 or len(parts) > 6:
        raise HTTPException(
            status_code=404,
            detail=f"Invalid record id: #{airalogy_record_id}",
        )

    # Extract the UUID part (always at index 3)
    id = parts[3]

    # If there's a version suffix, it will be in parts as v and version number
    version = None
    if len(parts) >= 6 and parts[4] == "v":
        try:
            version = int(parts[5])
        except ValueError:
            raise HTTPException(
                status_code=404,
                detail=f"Invalid version in record id: #{airalogy_record_id}",
            )

    # Query conditions for finding the record
    conditions = [Record.id == id]
    if version is not None:
        conditions.append(Record.version == version)

    record: Record | None = await Record.find_by(db_session, conditions)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Record not found: #{airalogy_record_id}",
        )
    if record.version > 1:
        init_record = await Record.find_by(
            db_session,
            [
                Record.id == record.id,
                Record.version == 1,
            ],
        )
    else:
        init_record = record
    user = await User.find(db_session, id=record.user_id)
    protocol: Protocol = await Protocol.find(db_session, id=record.protocol_id)
    project: Project = await Project.find(db_session, id=protocol.project_id)
    # check permission
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="read_record",
        protocol=protocol,
        record=record,
    )
    lab: Lab = await Lab.find(db_session, id=project.lab_id)
    protocol.lab_uid = lab.uid
    protocol.project_uid = project.uid
    return {
        "airalogy_record_id": record.airalogy_id,
        "record_id": record.id,
        "record_version": record.version,
        "metadata": {
            "airalogy_protocol_id": protocol.airalogy_id,
            "protocol_id": protocol.uid,
            "protocol_uuid": record.protocol_id,
            "protocol_version": record.protocol_version,
            "record_current_version_submission_time": record.created_at,
            "record_current_version_submission_user_id": user.username,
            "record_initial_version_submission_time": init_record.created_at,
            "record_initial_version_submission_user_id": user.username,
            "lab_id": lab.uid,
            "project_id": project.uid,
            "record_num": record.number,
            "sha1": record.hash,
        },
        "data": record.data,
    }


router = APIRouter(
    prefix="/airalogy",
    tags=["airalogy"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/upload")
async def upload_file(
    db_session: DBSession,
    current_user: CurrentUser,
    file: UploadFile,
    airalogy_protocol_id: Annotated[str, Body()],
):
    protocol = await get_current_protocol(db_session, airalogy_protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="exec_assigner",
        protocol=protocol,
    )

    filename = file.filename or "uploaded-file"
    att = AiralogyFile(
        filename=filename,
        content_type=file.content_type,
        size_bytes=file.size,
        protocol_id=protocol.id,
        project_id=protocol.project_id,
        user_id=current_user.id,
    )
    db_session.add(att)
    await db_session.flush()
    await att.save_file(
        file=file.file, content_type=file.content_type, length=file.size
    )
    await db_session.commit()
    return {"id": att.airalogy_id, "filename": att.filename}


@router.get("/download/{airalogy_file_id}", response_class=StreamingResponse)
async def download_file(
    airalogy_file_id: str,
    db_session: DBSession,
    current_user: CurrentUser,
):
    att = await AiralogyFile.find(db_session, airalogy_file_id)
    protocol = await Protocol.find(db_session, att.protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="read_protocol",
        protocol=protocol,
    )
    try:
        content_type, _ = mimetypes.guess_type(att.filename)
        return StreamingResponse(
            content=att.get_file_with_stream(), media_type=content_type
        )
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err))


@router.get("/get_file_url/{airalogy_file_id}")
async def get_file_url(
    airalogy_file_id: str,
    db_session: DBSession,
    current_user: CurrentUser,
):
    att = await AiralogyFile.find(db_session, airalogy_file_id)
    protocol = await Protocol.find(db_session, att.protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="read_protocol",
        protocol=protocol,
    )
    url = await att.file_object_url(expires=24)  # 24 hours
    return {"url": url}


class RecordQuery(BaseModel):
    airalogy_protocol_id: str
    airalogy_record_ids: List[str]


@router.post("/get_records")
async def get_records(
    params: RecordQuery,
    db_session: DBSession,
    current_user: CurrentUser,
):
    data = [
        await get_record(db_session, current_user, airalogy_record_id)
        for airalogy_record_id in params.airalogy_record_ids
    ]
    return data
