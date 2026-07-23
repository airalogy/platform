"""Lease-based, retryable database jobs for migrations and projections."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resource import JobStatus, PersistentJob


def utcnow() -> datetime:
    return datetime.now(UTC)


async def enqueue_job(
    db_session: AsyncSession,
    *,
    kind: str,
    payload: dict,
    idempotency_key: str,
    lab_id: UUID | None = None,
    max_attempts: int = 5,
) -> PersistentJob:
    existing = (
        await db_session.execute(
            select(PersistentJob).where(
                PersistentJob.idempotency_key == idempotency_key
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    job = PersistentJob(
        lab_id=lab_id,
        kind=kind,
        payload=payload,
        idempotency_key=idempotency_key,
        max_attempts=max_attempts,
        status=JobStatus.PENDING.value,
    )
    db_session.add(job)
    await db_session.flush()
    return job


async def claim_job(
    db_session: AsyncSession,
    *,
    worker_id: str,
    kinds: set[str] | None = None,
    lease_seconds: int = 60,
) -> PersistentJob | None:
    now = utcnow()
    conditions = [
        PersistentJob.available_at <= now,
        PersistentJob.attempts < PersistentJob.max_attempts,
        or_(
            PersistentJob.status == JobStatus.PENDING.value,
            (
                (PersistentJob.status == JobStatus.RUNNING.value)
                & (PersistentJob.lease_expires_at < now)
            ),
        ),
    ]
    if kinds:
        conditions.append(PersistentJob.kind.in_(kinds))
    job = (
        await db_session.execute(
            select(PersistentJob)
            .where(*conditions)
            .order_by(PersistentJob.available_at, PersistentJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
    ).scalar_one_or_none()
    if job is None:
        return None
    job.status = JobStatus.RUNNING.value
    job.lease_owner = worker_id
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    job.attempts += 1
    job.last_error = None
    await db_session.flush()
    return job


async def renew_job_lease(
    db_session: AsyncSession,
    *,
    job: PersistentJob,
    worker_id: str,
    lease_seconds: int = 60,
) -> None:
    if (
        job.status != JobStatus.RUNNING.value
        or job.lease_owner != worker_id
    ):
        raise ValueError("job lease is not owned by this worker")
    job.lease_expires_at = utcnow() + timedelta(seconds=lease_seconds)
    await db_session.flush()


async def complete_job(
    db_session: AsyncSession,
    *,
    job: PersistentJob,
    worker_id: str,
    result: dict | None = None,
) -> None:
    if job.lease_owner != worker_id:
        raise ValueError("job lease is not owned by this worker")
    job.status = JobStatus.SUCCEEDED.value
    job.result = result or {}
    job.lease_owner = None
    job.lease_expires_at = None
    await db_session.flush()


async def fail_job(
    db_session: AsyncSession,
    *,
    job: PersistentJob,
    worker_id: str,
    error: str,
    retry_delay_seconds: int = 30,
) -> None:
    if job.lease_owner != worker_id:
        raise ValueError("job lease is not owned by this worker")
    job.last_error = error[:8000]
    job.lease_owner = None
    job.lease_expires_at = None
    if job.attempts >= job.max_attempts:
        job.status = JobStatus.FAILED.value
    else:
        job.status = JobStatus.PENDING.value
        job.available_at = utcnow() + timedelta(seconds=retry_delay_seconds)
    await db_session.flush()
