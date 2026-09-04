import asyncio
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock
from uuid import uuid4

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.config import config
from app.main import app
from app.models.research import (
    ResearchAction,
    ResearchEvent,
    ResearchHumanWorkItem,
    ResearchTask,
)
from app.models.research_execution import (
    ResearchNotification,
    ResearchNotificationDelivery,
)
from app.services import research_notifications, resource_job_worker
from app.services.research_notifications import (
    materialize_research_attention_notification,
    process_research_notification_delivery,
    research_notification_data,
    resolve_research_attention_notifications,
)


def compile_table(model) -> str:
    return str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))


def test_research_notifications_are_private_and_delivery_is_tracked():
    notification_sql = compile_table(ResearchNotification)
    delivery_sql = compile_table(ResearchNotificationDelivery)

    assert "recipient_user_id" in notification_sql
    assert "deduplication_key" in notification_sql
    assert "work_item_assigned" in notification_sql
    assert "work_item_review_requested" in notification_sql
    assert "approval_requested" in notification_sql
    assert "notification_id" in delivery_sql
    assert "attempt_count" in delivery_sql
    assert "pending" in delivery_sql
    assert "failed" in delivery_sql


def test_human_work_review_notification_migration_is_linear_and_replaces_constraint(
    monkeypatch,
):
    migration = import_module(
        "migrations.versions.0042_human_work_review_notifications"
    )
    calls = []

    class Inspector:
        def get_check_constraints(self, _table: str):
            return [{"name": migration.CONSTRAINT_NAME}]

    monkeypatch.setattr(migration.op, "get_bind", lambda: object())
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: Inspector())
    monkeypatch.setattr(
        migration.op,
        "drop_constraint",
        lambda *args, **kwargs: calls.append(("drop", args, kwargs)),
    )
    monkeypatch.setattr(
        migration.op,
        "create_check_constraint",
        lambda *args, **kwargs: calls.append(("create", args, kwargs)),
    )

    migration.upgrade()

    assert migration.down_revision == "0041_research_service_graph_state"
    assert [item[0] for item in calls] == ["drop", "create"]


def test_notification_payload_masks_email_destination():
    notification = ResearchNotification(
        id=uuid4(),
        lab_id=uuid4(),
        project_id=uuid4(),
        task_id=uuid4(),
        recipient_user_id=uuid4(),
        kind="work_item_assigned",
        priority="normal",
        title="Research work assigned",
        message="Run assay",
        target_path="/research/tasks/example",
        deduplication_key="event:example:attention",
    )
    delivery = ResearchNotificationDelivery(
        id=uuid4(),
        notification_id=notification.id,
        channel="email",
        destination="scientist@example.org",
        status="sent",
        attempt_count=1,
        last_error="",
    )

    payload = research_notification_data(notification, deliveries=[delivery])

    assert payload["deliveries"][0]["destination"] == "s********@example.org"
    assert "scientist@example.org" not in str(payload)


def test_work_assignment_event_materializes_private_inbox_item(monkeypatch):
    recipient_id = uuid4()
    task = ResearchTask(
        id=uuid4(),
        lab_id=uuid4(),
        project_id=uuid4(),
        owner_user_id=recipient_id,
        created_by_user_id=recipient_id,
        title="Assay task",
        goal="Measure signal",
        success_criteria=[],
        stop_conditions=[],
        autonomy_level="assisted",
        status="active",
    )
    action = ResearchAction(
        id=uuid4(),
        run_id=uuid4(),
        sequence=1,
        plan_version=1,
        kind="protocol_run",
        status="waiting",
        title="Run private assay",
        executor_type="human",
        policy_decision="allow",
        preview_digest="a" * 64,
    )
    work_item = ResearchHumanWorkItem(
        id=uuid4(),
        action_id=action.id,
        assignee_user_id=recipient_id,
        status="open",
    )
    event = ResearchEvent(
        id=uuid4(),
        task_id=task.id,
        action_id=action.id,
        work_item_id=work_item.id,
        kind="work_item.assigned",
        actor_user_id=recipient_id,
    )
    recipient = SimpleNamespace(id=recipient_id, email="scientist@example.org")
    added = []

    def add(item):
        if getattr(item, "id", None) is None:
            item.id = uuid4()
        added.append(item)

    db_session = SimpleNamespace(
        get=AsyncMock(side_effect=[task, action, work_item, recipient]),
        scalars=AsyncMock(return_value=SimpleNamespace(first=lambda: None)),
        add=add,
        execute=AsyncMock(),
        flush=AsyncMock(),
    )
    enqueue = AsyncMock()
    monkeypatch.setattr(research_notifications, "enqueue_job", enqueue)
    monkeypatch.setattr(config, "RESEARCH_EMAIL_NOTIFICATIONS_ENABLED", False)

    notification = asyncio.run(
        materialize_research_attention_notification(db_session, event=event)
    )

    assert notification is not None
    assert notification.recipient_user_id == recipient_id
    assert notification.kind == "work_item_assigned"
    assert notification.target_path == f"/research/work-items/{work_item.id}"
    delivery = next(
        item for item in added if isinstance(item, ResearchNotificationDelivery)
    )
    assert delivery.status == "skipped"
    enqueue.assert_not_awaited()


def test_submitted_human_work_notifies_task_owner_for_review(monkeypatch):
    owner_id = uuid4()
    assignee_id = uuid4()
    task = ResearchTask(
        id=uuid4(),
        lab_id=uuid4(),
        project_id=uuid4(),
        owner_user_id=owner_id,
        created_by_user_id=owner_id,
        title="Field study",
        goal="Collect validated observations",
        success_criteria=[],
        stop_conditions=[],
        autonomy_level="assisted",
        status="active",
    )
    action = ResearchAction(
        id=uuid4(),
        run_id=uuid4(),
        sequence=1,
        plan_version=1,
        kind="human_work_item",
        status="submitted",
        title="Inspect samples",
        executor_type="human",
        policy_decision="allow",
        preview_digest="a" * 64,
    )
    work_item = ResearchHumanWorkItem(
        id=uuid4(),
        action_id=action.id,
        assignee_user_id=assignee_id,
        status="submitted",
    )
    event = ResearchEvent(
        id=uuid4(),
        task_id=task.id,
        action_id=action.id,
        work_item_id=work_item.id,
        kind="work_item.submitted",
        actor_user_id=assignee_id,
    )
    recipient = SimpleNamespace(id=owner_id, email="owner@example.org")
    added = []

    def add(item):
        if getattr(item, "id", None) is None:
            item.id = uuid4()
        added.append(item)

    db_session = SimpleNamespace(
        get=AsyncMock(side_effect=[task, action, work_item, recipient]),
        scalars=AsyncMock(return_value=SimpleNamespace(first=lambda: None)),
        add=add,
        execute=AsyncMock(),
        flush=AsyncMock(),
    )
    monkeypatch.setattr(research_notifications, "enqueue_job", AsyncMock())
    monkeypatch.setattr(config, "RESEARCH_EMAIL_NOTIFICATIONS_ENABLED", False)

    notification = asyncio.run(
        materialize_research_attention_notification(db_session, event=event)
    )

    assert notification is not None
    assert notification.recipient_user_id == owner_id
    assert notification.kind == "work_item_review_requested"
    assert notification.priority == "high"
    assert notification.target_path == f"/research/work-items/{work_item.id}"


def test_resolved_work_event_closes_stale_attention_item():
    db_session = SimpleNamespace(execute=AsyncMock())
    event = ResearchEvent(
        id=uuid4(),
        task_id=uuid4(),
        work_item_id=uuid4(),
        kind="work_item.started",
        actor_user_id=uuid4(),
    )

    asyncio.run(resolve_research_attention_notifications(db_session, event=event))

    db_session.execute.assert_awaited_once()


def test_email_delivery_uses_configured_smtp_without_blocking_event_loop(monkeypatch):
    notification_id = uuid4()
    delivery = ResearchNotificationDelivery(
        id=uuid4(),
        notification_id=notification_id,
        channel="email",
        destination="scientist@example.org",
        status="pending",
        attempt_count=0,
        last_error="",
    )
    notification = ResearchNotification(
        id=notification_id,
        lab_id=uuid4(),
        project_id=uuid4(),
        task_id=uuid4(),
        recipient_user_id=uuid4(),
        kind="approval_requested",
        priority="high",
        title="Research approval requested",
        message="Review proposed action",
        target_path="/research/tasks/example",
        deduplication_key="event:approval:attention",
    )
    db_session = SimpleNamespace(
        get=AsyncMock(side_effect=[delivery, notification]),
    )
    send = Mock()
    monkeypatch.setattr(research_notifications, "_send_smtp_message", send)
    monkeypatch.setattr(
        research_notifications,
        "_delivery_recipient_is_current",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(config, "RESEARCH_EMAIL_NOTIFICATIONS_ENABLED", True)
    monkeypatch.setattr(config, "SMTP_HOST", "smtp.example.org")
    monkeypatch.setattr(config, "SMTP_FROM_ADDRESS", "airalogy@example.org")

    result = asyncio.run(
        process_research_notification_delivery(
            db_session,
            delivery_id=delivery.id,
            attempt_number=2,
        )
    )

    assert result == {"delivery_id": str(delivery.id), "status": "sent"}
    assert delivery.status == "sent"
    assert delivery.attempt_count == 2
    assert delivery.delivered_at is not None
    send.assert_called_once_with(
        delivery_id=delivery.id,
        recipient="scientist@example.org",
        subject="[Airalogy] Research approval requested",
        body=ANY,
    )


def test_persistent_worker_dispatches_research_notification_delivery(monkeypatch):
    delivery_id = uuid4()
    process = AsyncMock(return_value={"status": "sent"})
    monkeypatch.setattr(
        resource_job_worker,
        "process_research_notification_delivery",
        process,
    )

    result = asyncio.run(
        resource_job_worker.process_persistent_job(
            SimpleNamespace(),
            SimpleNamespace(
                kind="research_notification_delivery",
                payload={"delivery_id": str(delivery_id)},
                attempts=3,
            ),
        )
    )

    assert result == {"status": "sent"}
    process.assert_awaited_once_with(
        ANY,
        delivery_id=delivery_id,
        attempt_number=3,
    )


def test_email_delivery_is_skipped_when_access_or_address_changed(monkeypatch):
    notification_id = uuid4()
    delivery = ResearchNotificationDelivery(
        id=uuid4(),
        notification_id=notification_id,
        channel="email",
        destination="former@example.org",
        status="pending",
        attempt_count=0,
        last_error="",
    )
    notification = ResearchNotification(
        id=notification_id,
        lab_id=uuid4(),
        project_id=uuid4(),
        task_id=uuid4(),
        recipient_user_id=uuid4(),
        kind="work_item_assigned",
        priority="normal",
        title="Research work assigned",
        message="Private assay",
        target_path="/research/tasks/example",
        deduplication_key="event:revoked:attention",
    )
    db_session = SimpleNamespace(get=AsyncMock(side_effect=[delivery, notification]))
    send = Mock()
    monkeypatch.setattr(research_notifications, "_send_smtp_message", send)
    monkeypatch.setattr(
        research_notifications,
        "_delivery_recipient_is_current",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(config, "RESEARCH_EMAIL_NOTIFICATIONS_ENABLED", True)
    monkeypatch.setattr(config, "SMTP_HOST", "smtp.example.org")
    monkeypatch.setattr(config, "SMTP_FROM_ADDRESS", "airalogy@example.org")

    result = asyncio.run(
        process_research_notification_delivery(
            db_session,
            delivery_id=delivery.id,
            attempt_number=1,
        )
    )

    assert result["status"] == "skipped"
    assert "access changed" in delivery.last_error
    send.assert_not_called()


def test_openapi_exposes_private_research_notification_contracts():
    paths = app.openapi()["paths"]

    assert "/research-notifications" in paths
    assert "/research-notifications/{notification_id}/read" in paths
