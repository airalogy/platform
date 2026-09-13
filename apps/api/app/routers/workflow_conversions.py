"""Owner-authorized, previewed copies alongside untouched legacy /workflow."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from app.database import DBSession
from app.models.workflow import ProtocolWorkflow
from app.models.workflow_conversion import WorkflowLegacyConversion
from app.models.workflow_definition import WorkflowDefinition, WorkflowRevision
from app.routers.depends import CurrentUser
from app.services.research_runtime import canonical_digest
from app.services.workflow_conversions import (
    LegacyConversionConfirm,
    LegacyConversionDraft,
    conversion_context,
    legacy_source,
    preview_conversion,
)
from app.services.workflow_definitions import (
    capabilities,
    definition_payload,
    request_lock,
    scope,
)

router = APIRouter(prefix="/workflow-conversions", tags=["workflow-conversions"])


@router.get("")
async def list_legacy_workflows(
    project_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    project = await scope(db_session, current_user, project_id)
    access = await capabilities(db_session, current_user, project)
    rows = list(
        (
            await db_session.scalars(
                select(ProtocolWorkflow)
                .where(
                    ProtocolWorkflow.project_id == project.id,
                    ProtocolWorkflow.user_id == current_user.id,
                    ProtocolWorkflow.deleted_at.is_(None),
                )
                .order_by(ProtocolWorkflow.updated_at.desc(), ProtocolWorkflow.id)
                .limit(100)
            )
        ).all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "title": row.title,
                "updated_at": row.updated_at,
                "path_status": (row.path_data or {}).get("path_status"),
                "can_convert": access["write"],
            }
            for row in rows
        ],
        "capabilities": access,
    }


@router.get("/receipts/{receipt_id}")
async def get_conversion_receipt(
    receipt_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    receipt = await db_session.scalar(
        select(WorkflowLegacyConversion).where(
            WorkflowLegacyConversion.id == receipt_id,
            WorkflowLegacyConversion.created_by_user_id == current_user.id,
        )
    )
    if receipt is None:
        raise HTTPException(404, "Workflow conversion receipt not found")
    await legacy_source(db_session, current_user, receipt.source_workflow_id)
    return receipt.as_dict(excludes=["request_digest", "idempotency_key"])


@router.get("/{legacy_id}/context")
async def legacy_conversion_context(
    legacy_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    workflow, project = await legacy_source(db_session, current_user, legacy_id)
    return await conversion_context(db_session, current_user, workflow, project)


@router.post("/{legacy_id}/preview")
async def preview_legacy_conversion(
    legacy_id: UUID,
    params: LegacyConversionDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    result, _, _ = await preview_conversion(db_session, current_user, legacy_id, params)
    return result


@router.post("/{legacy_id}/confirm")
async def confirm_legacy_conversion(
    legacy_id: UUID,
    params: LegacyConversionConfirm,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await scope(db_session, current_user, params.project_id, "research.create")
    await request_lock(db_session, current_user.id, params.idempotency_key)
    # Scope and source ownership are rechecked even on an idempotent replay.
    _, project = await legacy_source(
        db_session,
        current_user,
        legacy_id,
        project_id=params.project_id,
        lock=True,
        write=True,
    )
    request_digest = canonical_digest(
        {
            "legacy_id": str(legacy_id),
            "command": params.model_dump(mode="json", exclude={"idempotency_key"}),
        }
    )
    previous = await db_session.scalar(
        select(WorkflowLegacyConversion).where(
            WorkflowLegacyConversion.created_by_user_id == current_user.id,
            WorkflowLegacyConversion.idempotency_key == params.idempotency_key,
        )
    )
    if previous is not None:
        if (
            previous.request_digest != request_digest
            or previous.source_workflow_id != legacy_id
        ):
            raise HTTPException(
                409, "Idempotency key belongs to another Workflow conversion"
            )
        item = await db_session.get(WorkflowDefinition, previous.definition_id)
        if item is None or item.project_id != project.id:
            raise HTTPException(404, "Converted Workflow not found")
        result = await definition_payload(
            db_session, current_user, item, project, history=True
        )
        return {
            **result,
            "confirmed_revision_id": previous.workflow_revision_id,
            "conversion_receipt_id": previous.id,
        }
    collision = await db_session.scalar(
        select(WorkflowRevision.id).where(
            WorkflowRevision.created_by_user_id == current_user.id,
            WorkflowRevision.idempotency_key == params.idempotency_key,
        )
    )
    if collision is not None:
        raise HTTPException(
            409, "Idempotency key already belongs to another Workflow confirmation"
        )
    preview, _, _ = await preview_conversion(
        db_session, current_user, legacy_id, params, lock=True
    )
    if preview["preview_digest"] != params.preview_digest:
        raise HTTPException(
            409, "Conversion preview changed; preview again before confirmation"
        )
    item = WorkflowDefinition(
        project_id=project.id,
        title=params.title,
        description=params.description,
        revision=1,
        created_by_user_id=current_user.id,
    )
    db_session.add(item)
    await db_session.flush()
    content = {key: preview[key] for key in ("title", "description", "graph", "pins")}
    revision = WorkflowRevision(
        definition_id=item.id,
        revision=1,
        **content,
        digest=canonical_digest(content),
        request_digest=request_digest,
        idempotency_key=params.idempotency_key,
        created_by_user_id=current_user.id,
    )
    db_session.add(revision)
    await db_session.flush()
    receipt = WorkflowLegacyConversion(
        source_workflow_id=legacy_id,
        definition_id=item.id,
        workflow_revision_id=revision.id,
        source_digest=params.source_digest,
        request_digest=request_digest,
        node_mapping=[
            {**node.model_dump(mode="json"), "node_id": f"legacy_{node.protocol_index}"}
            for node in params.nodes
        ],
        idempotency_key=params.idempotency_key,
        created_by_user_id=current_user.id,
    )
    db_session.add(receipt)
    await db_session.commit()
    result = await definition_payload(
        db_session, current_user, item, project, history=True
    )
    return {
        **result,
        "confirmed_revision_id": revision.id,
        "conversion_receipt_id": receipt.id,
    }
