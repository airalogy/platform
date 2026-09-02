"""Private Research attention inbox and optional retryable email delivery."""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.models.project import Project
from app.models.research import (
    ResearchAction,
    ResearchApproval,
    ResearchEvent,
    ResearchHumanWorkItem,
    ResearchTask,
)
from app.models.research_execution import (
    ResearchNotification,
    ResearchNotificationDelivery,
    ResearchNotificationDeliveryStatus,
)
from app.models.user import User
from app.services.persistent_jobs import enqueue_job

ATTENTION_EVENT_KINDS = {"work_item.assigned", "approval.requested"}
RESOLVED_ATTENTION_EVENT_KINDS = {
    "work_item.started",
    "work_item.completed",
    "approval.approved",
    "approval.rejected",
    "task.cancelled",
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ResearchNotificationDeliveryError(RuntimeError):
    def __init__(self, delivery_id: UUID, message: str):
        super().__init__(message)
        self.delivery_id = delivery_id


def _masked_destination(value: str) -> str:
    if "@" not in value:
        return ""
    local, domain = value.rsplit("@", 1)
    visible = local[:1]
    return f"{visible}{'*' * max(2, len(local) - 1)}@{domain}"


def research_notification_data(
    notification: ResearchNotification,
    *,
    deliveries: list[ResearchNotificationDelivery],
) -> dict:
    return {
        "id": str(notification.id),
        "lab_id": str(notification.lab_id),
        "project_id": str(notification.project_id),
        "task_id": str(notification.task_id),
        "action_id": str(notification.action_id) if notification.action_id else None,
        "work_item_id": (
            str(notification.work_item_id) if notification.work_item_id else None
        ),
        "approval_id": (
            str(notification.approval_id) if notification.approval_id else None
        ),
        "recipient_user_id": str(notification.recipient_user_id),
        "kind": notification.kind,
        "priority": notification.priority,
        "title": notification.title,
        "message": notification.message,
        "target_path": notification.target_path,
        "read_at": notification.read_at,
        "created_at": notification.created_at,
        "updated_at": notification.updated_at,
        "deliveries": [
            {
                "id": str(item.id),
                "channel": item.channel,
                "destination": _masked_destination(item.destination),
                "status": item.status,
                "attempt_count": item.attempt_count,
                "delivered_at": item.delivered_at,
                "updated_at": item.updated_at,
            }
            for item in deliveries
        ],
    }


async def materialize_research_attention_notification(
    db_session: AsyncSession,
    *,
    event: ResearchEvent,
) -> ResearchNotification | None:
    """Project an actionable event into a private, idempotent user inbox."""

    if event.kind not in ATTENTION_EVENT_KINDS:
        return None
    task = await db_session.get(ResearchTask, event.task_id)
    action = (
        await db_session.get(ResearchAction, event.action_id)
        if event.action_id
        else None
    )
    if task is None or action is None:
        return None

    work_item: ResearchHumanWorkItem | None = None
    approval: ResearchApproval | None = None
    if event.kind == "work_item.assigned":
        if event.work_item_id is None:
            return None
        work_item = await db_session.get(ResearchHumanWorkItem, event.work_item_id)
        if work_item is None:
            return None
        recipient_user_id = work_item.assignee_user_id
        await db_session.execute(
            update(ResearchNotification)
            .where(
                ResearchNotification.work_item_id == work_item.id,
                ResearchNotification.recipient_user_id != recipient_user_id,
                ResearchNotification.read_at.is_(None),
            )
            .values(read_at=_utcnow())
        )
        kind = "work_item_assigned"
        title = "Research work assigned"
        message = action.title
        priority = "high" if work_item.due_at is not None else "normal"
    else:
        raw_approval_id = (event.payload or {}).get("approval_id")
        if not raw_approval_id:
            return None
        try:
            approval = await db_session.get(
                ResearchApproval, UUID(str(raw_approval_id))
            )
        except ValueError:
            return None
        if approval is None:
            return None
        recipient_user_id = approval.approver_user_id
        kind = "approval_requested"
        title = "Research approval requested"
        message = action.title
        priority = "high"

    deduplication_key = f"event:{event.id}:attention"
    existing = (
        await db_session.scalars(
            select(ResearchNotification).where(
                ResearchNotification.recipient_user_id == recipient_user_id,
                ResearchNotification.deduplication_key == deduplication_key,
            )
        )
    ).first()
    if existing is not None:
        return existing

    notification = ResearchNotification(
        lab_id=task.lab_id,
        project_id=task.project_id,
        task_id=task.id,
        action_id=action.id,
        work_item_id=work_item.id if work_item else None,
        approval_id=approval.id if approval else None,
        recipient_user_id=recipient_user_id,
        kind=kind,
        priority=priority,
        title=title,
        message=message,
        target_path=f"/research/tasks/{task.id}",
        deduplication_key=deduplication_key,
    )
    db_session.add(notification)
    await db_session.flush()

    recipient = await db_session.get(User, recipient_user_id)
    address = (recipient.email or "").strip() if recipient else ""
    enabled = config.effective_research_email_notifications_enabled
    delivery = ResearchNotificationDelivery(
        notification_id=notification.id,
        channel="email",
        destination=address,
        status=(
            ResearchNotificationDeliveryStatus.PENDING.value
            if enabled and address
            else ResearchNotificationDeliveryStatus.SKIPPED.value
        ),
        last_error=(
            ""
            if enabled and address
            else (
                "Recipient has no email address"
                if enabled
                else "Research email notifications are disabled"
            )
        ),
    )
    db_session.add(delivery)
    await db_session.flush()
    if delivery.status == ResearchNotificationDeliveryStatus.PENDING.value:
        await enqueue_job(
            db_session,
            kind="research_notification_delivery",
            lab_id=task.lab_id,
            payload={"delivery_id": str(delivery.id)},
            idempotency_key=f"research-notification:{notification.id}:email",
            max_attempts=5,
        )
    return notification


async def resolve_research_attention_notifications(
    db_session: AsyncSession,
    *,
    event: ResearchEvent,
) -> None:
    """Close stale reminders when the authoritative workflow moves on."""

    if event.kind not in RESOLVED_ATTENTION_EVENT_KINDS:
        return
    conditions = [ResearchNotification.read_at.is_(None)]
    if event.kind.startswith("work_item."):
        if event.work_item_id is None:
            return
        conditions.append(ResearchNotification.work_item_id == event.work_item_id)
    elif event.kind.startswith("approval."):
        raw_approval_id = (event.payload or {}).get("approval_id")
        if not raw_approval_id:
            return
        try:
            approval_id = UUID(str(raw_approval_id))
        except ValueError:
            return
        conditions.append(ResearchNotification.approval_id == approval_id)
    else:
        conditions.append(ResearchNotification.task_id == event.task_id)
    await db_session.execute(
        update(ResearchNotification).where(*conditions).values(read_at=_utcnow())
    )


def _send_smtp_message(
    *,
    delivery_id: UUID,
    recipient: str,
    subject: str,
    body: str,
) -> None:
    message = EmailMessage()
    message["From"] = config.SMTP_FROM_ADDRESS
    message["To"] = recipient
    message["Subject"] = subject
    hostname = urlparse(config.SITE_URL).hostname or "localhost"
    message["Message-ID"] = f"<{delivery_id}@{hostname}>"
    message.set_content(body)

    context = ssl.create_default_context()
    if config.SMTP_SECURITY == "ssl":
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            config.SMTP_HOST,
            config.SMTP_PORT,
            timeout=config.SMTP_TIMEOUT_SECONDS,
            context=context,
        )
    else:
        client = smtplib.SMTP(
            config.SMTP_HOST,
            config.SMTP_PORT,
            timeout=config.SMTP_TIMEOUT_SECONDS,
        )
    with client:
        client.ehlo()
        if config.SMTP_SECURITY == "starttls":
            client.starttls(context=context)
            client.ehlo()
        if config.SMTP_USERNAME:
            client.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
        client.send_message(message)


async def process_research_notification_delivery(
    db_session: AsyncSession,
    *,
    delivery_id: UUID,
    attempt_number: int,
) -> dict:
    delivery = await db_session.get(ResearchNotificationDelivery, delivery_id)
    if delivery is None:
        raise ValueError("Research notification delivery was not found")
    if delivery.status in {
        ResearchNotificationDeliveryStatus.SENT.value,
        ResearchNotificationDeliveryStatus.SKIPPED.value,
    }:
        return {"delivery_id": str(delivery.id), "status": delivery.status}
    notification = await db_session.get(ResearchNotification, delivery.notification_id)
    if notification is None:
        raise ValueError("Research notification was not found")
    if notification.read_at is not None:
        delivery.status = ResearchNotificationDeliveryStatus.SKIPPED.value
        delivery.last_error = "Attention item was already resolved"
        delivery.attempt_count = max(delivery.attempt_count, attempt_number)
        return {"delivery_id": str(delivery.id), "status": delivery.status}
    if not config.effective_research_email_notifications_enabled:
        delivery.status = ResearchNotificationDeliveryStatus.SKIPPED.value
        delivery.last_error = "Research email notifications are disabled"
        delivery.attempt_count = max(delivery.attempt_count, attempt_number)
        return {"delivery_id": str(delivery.id), "status": delivery.status}
    if not delivery.destination:
        delivery.status = ResearchNotificationDeliveryStatus.SKIPPED.value
        delivery.last_error = "Recipient has no email address"
        delivery.attempt_count = max(delivery.attempt_count, attempt_number)
        return {"delivery_id": str(delivery.id), "status": delivery.status}
    if not await _delivery_recipient_is_current(
        db_session,
        notification=notification,
        delivery=delivery,
    ):
        delivery.status = ResearchNotificationDeliveryStatus.SKIPPED.value
        delivery.last_error = "Recipient address or Research access changed"
        delivery.attempt_count = max(delivery.attempt_count, attempt_number)
        return {"delivery_id": str(delivery.id), "status": delivery.status}

    target_url = f"{config.SITE_URL.rstrip('/')}{notification.target_path}"
    subject = f"[Airalogy] {notification.title}"
    body = (
        f"{notification.message}\n\n"
        "Open Airalogy Platform to review the current task and its authoritative "
        f"state:\n{target_url}\n\n"
        "This email is only a reminder. Permissions and execution remain enforced "
        "inside Platform."
    )
    try:
        await asyncio.to_thread(
            _send_smtp_message,
            delivery_id=delivery.id,
            recipient=delivery.destination,
            subject=subject,
            body=body,
        )
    except Exception as error:
        raise ResearchNotificationDeliveryError(delivery.id, str(error)) from error
    delivery.status = ResearchNotificationDeliveryStatus.SENT.value
    delivery.attempt_count = max(delivery.attempt_count, attempt_number)
    delivery.last_error = ""
    delivery.delivered_at = _utcnow()
    return {"delivery_id": str(delivery.id), "status": delivery.status}


async def _delivery_recipient_is_current(
    db_session: AsyncSession,
    *,
    notification: ResearchNotification,
    delivery: ResearchNotificationDelivery,
) -> bool:
    recipient = await db_session.get(User, notification.recipient_user_id)
    project = await db_session.get(Project, notification.project_id)
    if (
        recipient is None
        or project is None
        or (recipient.email or "").strip() != delivery.destination
    ):
        return False
    from app.services.research_runtime import has_research_capability

    return await has_research_capability(
        db_session,
        user=recipient,
        project=project,
        capability="research.read",
    )


async def record_research_notification_delivery_failure(
    db_session: AsyncSession,
    *,
    delivery_id: UUID,
    attempt_number: int,
    error: str,
    terminal: bool,
) -> None:
    delivery = await db_session.get(ResearchNotificationDelivery, delivery_id)
    if (
        delivery is None
        or delivery.status == ResearchNotificationDeliveryStatus.SENT.value
    ):
        return
    delivery.attempt_count = max(delivery.attempt_count, attempt_number)
    delivery.last_error = error[:2000]
    delivery.status = (
        ResearchNotificationDeliveryStatus.FAILED.value
        if terminal
        else ResearchNotificationDeliveryStatus.PENDING.value
    )
