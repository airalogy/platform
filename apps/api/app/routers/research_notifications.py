"""Private Research attention inbox for the signed-in user."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.database import DBSession
from app.models.lab import Lab
from app.models.project import Project
from app.models.research import ResearchTask
from app.models.research_execution import (
    ResearchNotification,
    ResearchNotificationDelivery,
)
from app.routers.depends import CurrentUser
from app.services.research_notifications import research_notification_data
from app.services.research_runtime import has_research_capability, utcnow

router = APIRouter(prefix="/research-notifications", tags=["research-notifications"])


async def _accessible_notification_context(
    db_session: DBSession,
    *,
    notification: ResearchNotification,
    current_user: CurrentUser,
) -> tuple[ResearchTask, Project, Lab] | None:
    if notification.recipient_user_id != current_user.id:
        return None
    task = await db_session.get(ResearchTask, notification.task_id)
    project = await db_session.get(Project, notification.project_id)
    lab = await db_session.get(Lab, notification.lab_id)
    if (
        task is None
        or project is None
        or lab is None
        or not await has_research_capability(
            db_session,
            user=current_user,
            project=project,
            capability="research.read",
        )
    ):
        return None
    return task, project, lab


async def _notification_payload(
    db_session: DBSession,
    *,
    notification: ResearchNotification,
    context: tuple[ResearchTask, Project, Lab],
) -> dict:
    task, project, lab = context
    deliveries = list(
        (
            await db_session.scalars(
                select(ResearchNotificationDelivery).where(
                    ResearchNotificationDelivery.notification_id == notification.id
                )
            )
        ).all()
    )
    return {
        **research_notification_data(notification, deliveries=deliveries),
        "task": {"id": str(task.id), "title": task.title, "status": task.status},
        "project": {"id": str(project.id), "uid": project.uid, "name": project.name},
        "lab": {"id": str(lab.id), "uid": lab.uid, "name": lab.name},
    }


@router.get("")
async def list_research_notifications(
    current_user: CurrentUser,
    db_session: DBSession,
    unread_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    conditions = [ResearchNotification.recipient_user_id == current_user.id]
    if unread_only:
        conditions.append(ResearchNotification.read_at.is_(None))
    rows = list(
        (
            await db_session.scalars(
                select(ResearchNotification)
                .where(*conditions)
                .order_by(
                    ResearchNotification.read_at.is_not(None),
                    ResearchNotification.created_at.desc(),
                )
            )
        ).all()
    )
    accessible: list[
        tuple[ResearchNotification, tuple[ResearchTask, Project, Lab]]
    ] = []
    for notification in rows:
        context = await _accessible_notification_context(
            db_session,
            notification=notification,
            current_user=current_user,
        )
        if context is not None:
            accessible.append((notification, context))
    unread_count = sum(
        1 for notification, _context in accessible if not notification.read_at
    )
    selected = accessible[(page - 1) * page_size : page * page_size]
    return {
        "notifications": [
            await _notification_payload(
                db_session,
                notification=notification,
                context=context,
            )
            for notification, context in selected
        ],
        "total_count": len(accessible),
        "unread_count": unread_count,
    }


@router.post("/{notification_id}/read")
async def read_research_notification(
    notification_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    notification = await db_session.get(ResearchNotification, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="Research notification not found")
    context = await _accessible_notification_context(
        db_session,
        notification=notification,
        current_user=current_user,
    )
    if context is None:
        raise HTTPException(status_code=404, detail="Research notification not found")
    if notification.read_at is None:
        notification.read_at = utcnow()
        await db_session.commit()
    return await _notification_payload(
        db_session,
        notification=notification,
        context=context,
    )
