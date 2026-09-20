"""Exact, reviewed Protocol assets without executing a scientific analysis."""

from io import BytesIO
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Response,
    UploadFile,
)
from sqlalchemy import select
from starlette.datastructures import Headers

from app.database import DBSession
from app.models.analysis_protocol import AnalysisProtocolDraft
from app.routers.depends import CurrentUser
from app.services import analysis_protocol_drafts as service
from app.services.analysis_protocol_packages import analysis_protocol_package_zip_bytes
from app.services.workflow_analysis_methods import get_method


def private_response(response: Response):
    response.headers["Cache-Control"] = "private, no-store"


router = APIRouter(
    prefix="/analysis-protocol-drafts",
    tags=["analysis-protocol-drafts"],
    dependencies=[Depends(private_response)],
)


@router.post("/template")
async def draft_template(
    params: service.DraftTemplate, current_user: CurrentUser, db_session: DBSession
):
    return await service.template(db_session, current_user, params)


@router.post("/preview")
async def draft_preview(
    params: service.DraftContent, current_user: CurrentUser, db_session: DBSession
):
    return await service.preview_content(db_session, current_user, params)


@router.post("/confirm")
async def draft_confirm(
    params: service.DraftConfirm, current_user: CurrentUser, db_session: DBSession
):
    draft, method = await service.create_draft(db_session, current_user, params)
    payload = await service.draft_payload(db_session, current_user, draft, method)
    await db_session.commit()
    return payload


@router.get("")
async def list_drafts(
    method_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    method = await get_method(db_session, current_user, method_id)
    drafts = list(
        (
            await db_session.scalars(
                select(AnalysisProtocolDraft)
                .where(AnalysisProtocolDraft.method_id == method.id)
                .order_by(AnalysisProtocolDraft.created_at.desc())
            )
        ).all()
    )
    return {
        "items": [
            await service.draft_payload(
                db_session, current_user, row, method, summary=True
            )
            for row in drafts
        ]
    }


@router.get("/{draft_id}")
async def read_draft(draft_id: UUID, current_user: CurrentUser, db_session: DBSession):
    draft, method = await service.get_draft(db_session, current_user, draft_id)
    return await service.draft_payload(db_session, current_user, draft, method)


@router.get("/{draft_id}/revisions/{revision}")
async def read_revision(
    draft_id: UUID, revision: int, current_user: CurrentUser, db_session: DBSession
):
    draft, method = await service.get_draft(db_session, current_user, draft_id)
    if not 1 <= revision <= draft.revision:
        raise HTTPException(404, "Draft revision not found")
    row = await service.revision_row(db_session, draft, revision)
    service.verify_revision(method, row)
    return service.revision_payload(row, include_files=True)


@router.post("/{draft_id}/revisions/preview")
async def revision_preview(
    draft_id: UUID,
    params: service.RevisionContent,
    current_user: CurrentUser,
    db_session: DBSession,
):
    return await service.preview_revision(db_session, current_user, draft_id, params)


@router.post("/{draft_id}/revisions/confirm")
async def revision_confirm(
    draft_id: UUID,
    params: service.RevisionConfirm,
    current_user: CurrentUser,
    db_session: DBSession,
):
    draft, method = await service.confirm_revision(
        db_session, current_user, draft_id, params
    )
    payload = await service.draft_payload(db_session, current_user, draft, method)
    await db_session.commit()
    return payload


@router.post("/{draft_id}/review")
async def review_draft(
    draft_id: UUID,
    params: service.ReviewRequest,
    current_user: CurrentUser,
    db_session: DBSession,
):
    draft, method = await service.review_draft(
        db_session, current_user, draft_id, params
    )
    payload = await service.draft_payload(db_session, current_user, draft, method)
    await db_session.commit()
    return payload


@router.post("/{draft_id}/publish/preview")
async def publish_preview(
    draft_id: UUID,
    params: service.ExactRevision,
    current_user: CurrentUser,
    db_session: DBSession,
):
    return await service.preview_publish(db_session, current_user, draft_id, params)


@router.post("/{draft_id}/publish")
async def publish_draft(
    draft_id: UUID,
    params: service.PublishConfirm,
    current_user: CurrentUser,
    db_session: DBSession,
    background_tasks: BackgroundTasks,
):
    from app.routers.protocol_versions import upload_package

    draft, method = await service.get_draft(
        db_session, current_user, draft_id, lock=True
    )
    current = await service.revision_row(db_session, draft)
    package = service.verify_revision(method, current)
    if (
        current.revision != params.expected_revision
        or current.package_digest != params.package_digest
    ):
        raise HTTPException(409, "Publication request targets another package revision")
    if draft.state == "applied":
        project, protocol, _ = await service.target_context(
            db_session, current_user, method, draft.target_protocol_id
        )
        await service.require_target_write(db_session, current_user, project, protocol)
        return await service.draft_payload(db_session, current_user, draft, method)
    service.verify_receipt(
        params.preview_token,
        user_id=current_user.id,
        purpose=f"publish:{draft.id}:{draft.revision}",
        digest=params.preview_digest,
    )
    preview = await service.preview_publish(
        db_session, current_user, draft.id, params, lock=True
    )
    if preview["preview_digest"] != params.preview_digest:
        raise HTTPException(409, "Protocol publication changed; preview again")
    data = analysis_protocol_package_zip_bytes(package)
    upload = UploadFile(
        BytesIO(data),
        filename="analysis-protocol.zip",
        headers=Headers({"content-type": "application/zip"}),
    )
    try:
        # Keep the ordinary parser, version checks, storage and transaction.
        # Only the exact server-stored, reviewed files enter that path.
        await upload_package(
            current_user,
            db_session,
            upload,
            background_tasks,
            project_id=draft.project_id,
            env_vars="",
            protocol_id=draft.target_protocol_id,
            source_knowledge_item_id=None,
            source_knowledge_revision=None,
            source_protocol_improvement_id=None,
            source_protocol_improvement_revision=None,
            source_analysis_protocol_draft_id=draft.id,
            source_analysis_protocol_revision=draft.revision,
            source_analysis_protocol_digest=current.package_digest,
            source_analysis_protocol_preview_digest=params.preview_digest,
            source_analysis_protocol_preview_token=params.preview_token,
        )
    finally:
        await upload.close()
    draft, method = await service.get_draft(db_session, current_user, draft.id)
    return await service.draft_payload(db_session, current_user, draft, method)
