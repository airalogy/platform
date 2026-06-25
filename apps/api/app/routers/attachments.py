from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import delete

from app.database import DBSession
from app.models.attachment import Attachment
from app.routers.utils import UUID

from .depends import CurrentUser, get_current_user

router = APIRouter(
    prefix="/attachments",
    tags=["attachments"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/{id}")
async def get_attachment_by_id(
    id: UUID,
    db_session: DBSession,
):
    att = await Attachment.find(db_session, id=id)
    url = await att.local_url()
    return {"url": url, "id": att.id, "filename": att.filename}


@router.post("/")
async def create_attachment(
    file: UploadFile,
    db_session: DBSession,
    current_user: CurrentUser,
):
    att = Attachment(
        filename=file.filename,
        content_type=file.content_type,
        user_id=current_user.id,
    )
    db_session.add(att)
    await db_session.flush()
    await att.save_file(file=file.file, length=file.size)
    await db_session.commit()
    url = await att.local_url()
    return {"id": att.id, "url": url, "filename": att.filename}


@router.delete("/{id}")
async def delete_attachment_by_id(
    id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
):
    att = await Attachment.find(db_session, id=id)
    if att.user_id != current_user.id:
        raise HTTPException(status_code=400, detail="Permission denied")

    delete_stmt = delete(Attachment).where(Attachment.id == id)
    await db_session.execute(delete_stmt)
    await att.delete_file()
    await db_session.commit()
    return {"id": att.id}
