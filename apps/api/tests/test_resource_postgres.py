"""Real PostgreSQL checks for locks and database-only constraints.

Set RESOURCE_TEST_DATABASE_URL to an isolated, migrated PostgreSQL database.
These tests intentionally do not fall back to SQLite because row locks,
exclusion constraints, NUMERIC, and append-only triggers are the contract.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.resource import (
    EquipmentBooking,
    InventoryBalance,
    InventoryEvent,
    Resource,
    ResourceContainer,
    ResourceType,
)
from app.services.persistent_jobs import claim_job, enqueue_job
from app.services.resource_inventory import (
    InventoryError,
    apply_inventory_event,
    release_expired_inventory_reservations,
    reserve_inventory,
    set_inventory_on_hand,
)

DATABASE_URL = os.environ.get("RESOURCE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="RESOURCE_TEST_DATABASE_URL is required for PostgreSQL guarantees",
)


async def seed_inventory(session_factory):
    user_id = uuid4()
    lab_id = uuid4()
    resource_type_id = uuid4()
    resource_id = uuid4()
    container_id = uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    async with session_factory() as session:
        await session.execute(
            text(
                """
                INSERT INTO users (
                    id, username, email, country_code, phone, password_hash,
                    created_at, updated_at, name, bio, api_key_iv, level
                ) VALUES (
                    :id, :username, :email, '+86', :phone, 'hash',
                    :now, :now, 'Inventory tester', '', 'iv', 1
                )
                """
            ),
            {
                "id": user_id,
                "username": f"inventory_{user_id.hex}",
                "email": f"{user_id.hex}@example.test",
                "phone": user_id.hex[:16],
                "now": now,
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO labs (
                    id, name, uid, create_user_id, users_count,
                    projects_count, groups_count, description,
                    created_at, updated_at
                ) VALUES (
                    :id, 'Inventory Lab', :uid, :user_id, 1, 0, 0, '',
                    :now, :now
                )
                """
            ),
            {
                "id": lab_id,
                "uid": f"lab_{lab_id.hex}",
                "user_id": user_id,
                "now": now,
            },
        )
        resource_type = ResourceType(
            id=resource_type_id,
            lab_id=lab_id,
            code=f"type-{resource_type_id.hex}",
            name="Test material",
            description="",
            created_by_user_id=user_id,
        )
        resource = Resource(
            id=resource_id,
            lab_id=lab_id,
            resource_type_id=resource_type_id,
            name="Test stock",
            code=f"stock-{resource_id.hex}",
            status="active",
            visibility="lab",
            created_by_user_id=user_id,
        )
        container = ResourceContainer(
            id=container_id,
            lab_id=lab_id,
            resource_id=resource_id,
            code=f"container-{container_id.hex}",
            status="active",
            unit="mL",
            data={},
        )
        session.add(resource_type)
        await session.flush()
        session.add(resource)
        await session.flush()
        session.add(container)
        await session.flush()
        session.add(
            InventoryBalance(
                container_id=container_id,
                on_hand=Decimal("10"),
                reserved=Decimal("0"),
                unit="mL",
                version=0,
            )
        )
        await session.commit()
    return user_id, lab_id, resource_id, container_id


async def exercise_concurrent_consumption_and_idempotency():
    engine = create_async_engine(DATABASE_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    user_id, lab_id, _, container_id = await seed_inventory(sessions)

    async def consume(key: str):
        async with sessions() as session:
            try:
                event = await apply_inventory_event(
                    session,
                    lab_id=lab_id,
                    actor_user_id=user_id,
                    container_id=container_id,
                    kind="consumption",
                    quantity="7",
                    unit="mL",
                    idempotency_key=key,
                    on_hand_direction=-1,
                )
                await session.commit()
                return event.id
            except InventoryError:
                await session.rollback()
                return None

    results = await asyncio.gather(consume("consume-a"), consume("consume-b"))
    assert sum(item is not None for item in results) == 1

    async with sessions() as session:
        balance = await session.get(InventoryBalance, container_id)
        assert balance.on_hand == Decimal("3")
        successful_key = "consume-a" if results[0] is not None else "consume-b"
        duplicate = await apply_inventory_event(
            session,
            lab_id=lab_id,
            actor_user_id=user_id,
            container_id=container_id,
            kind="consumption",
            quantity="7",
            unit="mL",
            idempotency_key=successful_key,
            on_hand_direction=-1,
        )
        await session.commit()
        assert duplicate.id in results
        balance = await session.get(InventoryBalance, container_id)
        assert balance.on_hand == Decimal("3")

    await engine.dispose()


def test_concurrent_consumption_locks_balance_and_idempotency_is_stable():
    asyncio.run(exercise_concurrent_consumption_and_idempotency())


async def exercise_booking_and_append_only_constraints():
    engine = create_async_engine(DATABASE_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    user_id, lab_id, resource_id, container_id = await seed_inventory(sessions)
    starts_at = datetime.now(UTC) + timedelta(hours=1)

    async with sessions() as session:
        first = EquipmentBooking(
            lab_id=lab_id,
            resource_id=resource_id,
            user_id=user_id,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=2),
            status="approved",
            approval_policy="auto",
            purpose="first",
            idempotency_key=f"booking-{uuid4()}",
        )
        session.add(first)
        await session.commit()

    async with sessions() as session:
        session.add(
            EquipmentBooking(
                lab_id=lab_id,
                resource_id=resource_id,
                user_id=user_id,
                starts_at=starts_at + timedelta(minutes=30),
                ends_at=starts_at + timedelta(hours=3),
                status="pending",
                approval_policy="approval",
                purpose="overlap",
                idempotency_key=f"booking-{uuid4()}",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async with sessions() as session:
        event = await apply_inventory_event(
            session,
            lab_id=lab_id,
            actor_user_id=user_id,
            container_id=container_id,
            kind="receipt",
            quantity="1",
            unit="mL",
            idempotency_key=f"receipt-{uuid4()}",
            on_hand_direction=1,
        )
        await session.commit()
        with pytest.raises(DBAPIError, match="append-only"):
            await session.execute(
                update(InventoryEvent)
                .where(InventoryEvent.id == event.id)
                .values(reason="mutated")
            )
        await session.rollback()

    await engine.dispose()


def test_booking_overlap_and_append_only_audit_are_database_enforced():
    asyncio.run(exercise_booking_and_append_only_constraints())


async def exercise_counts_expiry_and_job_recovery():
    engine = create_async_engine(DATABASE_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    user_id, lab_id, resource_id, container_id = await seed_inventory(sessions)

    async with sessions() as session:
        reservation = await reserve_inventory(
            session,
            lab_id=lab_id,
            resource_id=resource_id,
            container_id=container_id,
            quantity="4",
            unit="mL",
            actor_user_id=user_id,
            idempotency_key=f"reservation-{uuid4()}",
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        await session.commit()
        assert reservation.status == "active"

    async with sessions() as session:
        assert await release_expired_inventory_reservations(session) == 1
        await session.commit()
        balance = await session.get(InventoryBalance, container_id)
        assert balance.reserved == Decimal("0")

        await set_inventory_on_hand(
            session,
            lab_id=lab_id,
            actor_user_id=user_id,
            container_id=container_id,
            quantity="0",
            unit="mL",
            idempotency_key=f"count-{uuid4()}",
            reason="physical count",
        )
        await session.commit()
        balance = await session.get(InventoryBalance, container_id)
        assert balance.on_hand == Decimal("0")

        # A zero-delta physical count is still a valid append-only audit event.
        await set_inventory_on_hand(
            session,
            lab_id=lab_id,
            actor_user_id=user_id,
            container_id=container_id,
            quantity="0",
            unit="mL",
            idempotency_key=f"count-{uuid4()}",
        )
        await session.commit()

    async with sessions() as session:
        async with session.begin():
            job_kind = f"record_projection_test_{uuid4().hex}"
            job = await enqueue_job(
                session,
                lab_id=lab_id,
                kind=job_kind,
                payload={"protocol_id": str(uuid4()), "target_version": "2.0.0"},
                idempotency_key=f"job-{uuid4()}",
            )
            first = await claim_job(
                session,
                worker_id="worker-a",
                kinds={job_kind},
                lease_seconds=0,
            )
            assert first.id == job.id

    async with sessions() as session:
        async with session.begin():
            recovered = await claim_job(
                session,
                worker_id="worker-b",
                kinds={job_kind},
            )
            assert recovered.id == job.id
            assert recovered.attempts == 2

    await engine.dispose()


def test_physical_counts_expired_reservations_and_job_leases_recover():
    asyncio.run(exercise_counts_expiry_and_job_recovery())
