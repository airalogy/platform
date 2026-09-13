"""Real PostgreSQL checks for locks and database-only constraints.

Set RESOURCE_TEST_DATABASE_URL to an isolated, migrated PostgreSQL database.
These tests intentionally do not fall back to SQLite because row locks,
exclusion constraints, NUMERIC, and append-only triggers are the contract.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock
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
from app.services.persistent_jobs import (
    claim_job,
    complete_job,
    enqueue_job,
    fail_job,
    renew_job_lease,
)
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


def test_optional_embedding_migration_preserves_vectors_and_blocks_lossy_downgrade():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    migration = import_module("migrations.versions.0058_optional_embeddings")

    async def exercise():
        engine = create_async_engine(DATABASE_URL)
        try:
            async with engine.begin() as connection:
                # Connection-private table shadows the live migrated table.
                await connection.execute(
                    text(
                        "CREATE TEMP TABLE embeddings (id int, embedding vector(1024) NOT NULL) ON COMMIT DROP"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO embeddings VALUES (1, array_fill(0.1::real, ARRAY[1024])::vector)"
                    )
                )

                def run_migration(sync_connection, operation):
                    with Operations.context(
                        MigrationContext.configure(sync_connection)
                    ):
                        operation()

                await connection.run_sync(run_migration, migration.upgrade)
                assert (
                    await connection.execute(
                        text(
                            "SELECT vector_dims(embedding) FROM embeddings WHERE id = 1"
                        )
                    )
                ).scalar_one() == 1024
                # A populated old index can still be safely downgraded.
                await connection.run_sync(run_migration, migration.downgrade)
                await connection.run_sync(run_migration, migration.upgrade)
                await connection.execute(
                    text("INSERT INTO embeddings VALUES (2, NULL)")
                )
                with pytest.raises(IntegrityError):
                    async with connection.begin_nested():
                        await connection.run_sync(run_migration, migration.downgrade)
                assert (
                    await connection.execute(text("SELECT count(*) FROM embeddings"))
                ).scalar_one() == 2
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_keyword_index_replacement_and_public_retrieval_survive_ai_outages(monkeypatch):
    from sqlalchemy import select

    from app.libs import masterbrain, text_splitter
    from app.models import embedding as module
    from app.models.embedding import Embedding, EmbeddingResourceType
    from app.models.project import PermissionType, Project, ProjectType
    from app.models.protocol import Protocol
    from app.models.protocol_version import ProtocolVersion
    from app.routers import hub
    from app.routers.chats.context_inject import inject_recommended_airalogy_protocols
    from app.routers.chats.hub import inject_recommend_airalogy_protocols

    async def exercise():
        engine = create_async_engine(DATABASE_URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            user_id, lab_id, _, _ = await seed_inventory(sessions)
            protocols = {}
            async with sessions() as session:
                for scope in (
                    "public",
                    "private",
                    "restricted",
                    "deleted_project",
                    "deleted_protocol",
                ):
                    project = Project(
                        id=uuid4(),
                        lab_id=lab_id,
                        uid=f"project_{uuid4().hex}",
                        name=scope,
                        create_user_id=user_id,
                        type=ProjectType.PRIVATE
                        if scope == "private"
                        else ProjectType.PUBLIC,
                        permission_type=PermissionType.PROTOCOL_LEVEL
                        if scope == "restricted"
                        else PermissionType.INHERIT,
                        deleted_at=datetime.now(UTC).replace(tzinfo=None)
                        if scope == "deleted_project"
                        else None,
                    )
                    session.add(project)
                    await session.flush()
                    protocol = Protocol(
                        id=uuid4(),
                        project_id=project.id,
                        user_id=user_id,
                        uid=f"protocol_{uuid4().hex}",
                        name=scope,
                        latest_version="0.0.1",
                        deleted_at=datetime.now(UTC).replace(tzinfo=None)
                        if scope == "deleted_protocol"
                        else None,
                    )
                    session.add(protocol)
                    await session.flush()
                    session.add(
                        ProtocolVersion(
                            protocol_id=protocol.id,
                            meta_data={"id": protocol.uid},
                            json_schema={},
                            assigners={},
                            fields={},
                            assigner_graph={},
                            aimd=scope,
                        )
                    )
                    protocols[scope] = protocol.id
                await session.commit()

            @asynccontextmanager
            async def database():
                async with sessions() as session:
                    yield session

            settings = SimpleNamespace(effective_embeddings_enabled=False)
            monkeypatch.setattr(module.sessionmanager, "session", database)
            monkeypatch.setattr(text_splitter, "config", settings)
            monkeypatch.setattr(masterbrain, "config", settings)
            monkeypatch.setattr(text_splitter, "text_to_chunks", lambda value: [value])
            monkeypatch.setattr(
                text_splitter, "text_to_words", lambda value: value.split()
            )
            monkeypatch.setattr(module, "text_to_words", lambda value: value.split())
            send = AsyncMock(side_effect=TimeoutError("synthetic outage"))
            monkeypatch.setattr(masterbrain, "json_request", send)
            keyword = f"antibody{uuid4().hex}"
            for protocol_id in protocols.values():
                await Embedding.add_resource(
                    protocol_id, protocol_id, EmbeddingResourceType.PROTOCOL, keyword
                )
            send.assert_not_awaited()

            # Two concurrent replacements must not leave duplicate committed rows.
            public_id = protocols["public"]
            await asyncio.gather(
                *[
                    Embedding.add_resource(
                        public_id, public_id, EmbeddingResourceType.PROTOCOL, keyword
                    )
                    for _ in range(2)
                ]
            )
            async with sessions() as session:
                rows = (
                    (
                        await session.execute(
                            select(Embedding).where(Embedding.protocol_id == public_id)
                        )
                    )
                    .scalars()
                    .all()
                )
                assert len(rows) == 1 and rows[0].embedding is None

            for mode in ("disabled", "outage", "restored"):
                settings.effective_embeddings_enabled = mode != "disabled"
                if mode == "restored":
                    send.side_effect = None
                    send.return_value = {
                        "model": "text-embedding-v4",
                        "dimensions": 1024,
                        "vectors": [[0.1] * 1024],
                    }
                async with sessions() as session:
                    # Never mix another Protocol into scoped discussion retrieval.
                    rows = await Embedding.retrieval_vector(
                        session, public_id, [EmbeddingResourceType.PROTOCOL], keyword
                    )
                    assert len(rows) == 1 and rows[0]["resource_id"] == public_id
                    assert rows[0]["similarity"] is None
                    assert await Embedding.retrieval_full_text(
                        session, public_id, [EmbeddingResourceType.PROTOCOL], keyword
                    ) == [keyword]
                    # Punctuation must not be interpreted as invalid tsquery syntax.
                    await Embedding.retrieval_vector(
                        session,
                        public_id,
                        [EmbeddingResourceType.PROTOCOL],
                        keyword + ' ! : " ( )',
                    )
                    result = await hub.retrieval(
                        session,
                        hub.config.INNER_API_KEY,
                        keyword,
                        top_k=10,
                        distance=0.6,
                    )
                    assert [row["aimd"] for row in result["result"]] == ["public"]
                    for recommend in (
                        inject_recommended_airalogy_protocols,
                        inject_recommend_airalogy_protocols,
                    ):
                        result = await recommend(session, keyword, limit=10)
                        assert [
                            row["markdown"] for row in result["airalogy_protocols"]
                        ] == ["public"]
        finally:
            await engine.dispose()

    asyncio.run(exercise())


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

    async with sessions() as stale_session:
        another = await enqueue_job(
            stale_session,
            kind="lease-fencing-test",
            payload={},
            idempotency_key=uuid4().hex,
        )
        stale = await claim_job(
            stale_session, worker_id="stale", job_id=another.id, lease_seconds=0
        )
        await stale_session.commit()
        async with sessions() as new_session:
            current = await claim_job(
                new_session, worker_id="current", job_id=another.id
            )
            assert current.attempts == 2
            await new_session.commit()
        for operation, kwargs in (
            (complete_job, {}),
            (fail_job, {"error": "late error"}),
            (renew_job_lease, {}),
        ):
            with pytest.raises(ValueError, match="not owned"):
                await operation(stale_session, job=stale, worker_id="stale", **kwargs)
            await stale_session.rollback()

    await engine.dispose()


def test_physical_counts_expired_reservations_and_job_leases_recover():
    asyncio.run(exercise_counts_expiry_and_job_recovery())
