"""Deterministic contracts, budget accounting, and state helpers for Compute Jobs."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import ResearchFile
from app.models.research import (
    ResearchAction,
    ResearchActionStatus,
    ResearchRun,
    ResearchRunStatus,
    ResearchTask,
    ResearchTaskComputeEnvironment,
)
from app.models.research_asset import DataAsset, DataAssetStatus, DataAssetVersion
from app.models.research_execution import (
    ResearchBudgetEntry,
    ResearchBudgetEntryKind,
    ResearchComputeEnvironment,
    ResearchComputeEnvironmentRevision,
    ResearchComputeJob,
    ResearchComputeJobInput,
    ResearchComputeJobStatus,
    ResearchComputeRunner,
    ResearchComputeRunnerEnvironment,
)
from app.services.research_budget import (
    ResearchBudgetError,
    project_budget_change,
    research_budget_snapshot,
)
from app.services.research_compute import compute_environment_snapshot
from app.services.research_compute_runners import runner_report_is_execution_ready
from app.services.research_runtime import canonical_digest, utcnow

LEASE_SECONDS = 120
MAX_SOURCE_BYTES = 200_000
FINAL_COMPUTE_JOB_STATUSES = {
    ResearchComputeJobStatus.COMPLETED.value,
    ResearchComputeJobStatus.FAILED.value,
    ResearchComputeJobStatus.CANCELLED.value,
}
ACTIVE_COMPUTE_JOB_STATUSES = {
    ResearchComputeJobStatus.LEASED.value,
    ResearchComputeJobStatus.RUNNING.value,
    ResearchComputeJobStatus.CANCEL_REQUESTED.value,
}


def compute_source_digest(source_code: str) -> str:
    return hashlib.sha256(source_code.encode("utf-8")).hexdigest()


def generate_compute_lease_token() -> str:
    return f"aicl_{secrets.token_urlsafe(32)}"


def compute_lease_token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def sign_compute_envelope(envelope: dict[str, Any], runner_digest: str) -> str:
    payload = json.dumps(
        envelope,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(runner_digest.encode("ascii"), payload, hashlib.sha256).hexdigest()


def compute_estimated_cost(
    revision: ResearchComputeEnvironmentRevision,
) -> Decimal | None:
    if revision.estimated_cost_per_hour is None:
        return None
    timeout_seconds = int((revision.resource_limits or {}).get("timeout_seconds") or 0)
    return Decimal(revision.estimated_cost_per_hour) * Decimal(timeout_seconds) / Decimal(
        3600
    )


def compute_actual_cost(job: ResearchComputeJob, wall_seconds: int) -> Decimal | None:
    metadata = (job.environment_snapshot or {}).get("metadata") or {}
    hourly = metadata.get("estimated_cost_per_hour")
    if hourly is None:
        return None
    billable_seconds = min(max(wall_seconds, 0), job.timeout_seconds)
    return Decimal(str(hourly)) * Decimal(billable_seconds) / Decimal(3600)


def compute_job_snapshot(job: ResearchComputeJob) -> dict[str, Any]:
    data = job.as_dict()
    data["source_sha256"] = job.source_sha256
    data["source_bytes"] = len(job.source_code.encode("utf-8"))
    return data


def compute_action_command(
    *,
    task: ResearchTask,
    run: ResearchRun,
    environment: ResearchComputeEnvironment,
    revision: ResearchComputeEnvironmentRevision,
    language: str,
    source_code: str,
    input_payload: dict[str, Any],
    input_versions: list[tuple[DataAsset, DataAssetVersion, str]],
    title: str,
    description: str,
    idempotency_key: str,
) -> dict[str, Any]:
    return {
        "operation": "request_research_compute_job",
        "task_id": str(task.id),
        "task_revision": task.revision,
        "run_id": str(run.id),
        "run_plan_version": run.plan_version,
        "compute_environment_id": str(environment.id),
        "compute_environment_revision_id": str(revision.id),
        "compute_environment_revision": revision.revision,
        "image_ref": revision.image_ref,
        "language": language,
        "source_sha256": compute_source_digest(source_code),
        "source_bytes": len(source_code.encode("utf-8")),
        "input_payload": input_payload,
        "input_assets": [
            {
                "data_asset_id": str(asset.id),
                "data_asset_version_id": str(version.id),
                "data_asset_version": version.version,
                "checksum": version.checksum,
                "mount_name": mount_name,
            }
            for asset, version, mount_name in input_versions
        ],
        "resource_limits": revision.resource_limits,
        "network_policy": revision.network_policy,
        "allowed_egress_hosts": revision.allowed_egress_hosts,
        "estimated_cost": (
            str(compute_estimated_cost(revision))
            if compute_estimated_cost(revision) is not None
            else None
        ),
        "currency": revision.currency,
        "title": title,
        "description": description,
        "idempotency_key": idempotency_key,
    }


async def pinned_compute_environment(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    revision_id: UUID,
    lock: bool = False,
) -> tuple[
    ResearchTaskComputeEnvironment,
    ResearchComputeEnvironment,
    ResearchComputeEnvironmentRevision,
]:
    statement = (
        select(
            ResearchTaskComputeEnvironment,
            ResearchComputeEnvironment,
            ResearchComputeEnvironmentRevision,
        )
        .join(
            ResearchComputeEnvironment,
            ResearchComputeEnvironment.id
            == ResearchTaskComputeEnvironment.compute_environment_id,
        )
        .join(
            ResearchComputeEnvironmentRevision,
            ResearchComputeEnvironmentRevision.id
            == ResearchTaskComputeEnvironment.compute_environment_revision_id,
        )
        .where(
            ResearchTaskComputeEnvironment.task_id == task.id,
            ResearchTaskComputeEnvironment.compute_environment_revision_id
            == revision_id,
        )
    )
    if lock:
        statement = statement.with_for_update()
    row = (await db_session.execute(statement)).first()
    if row is None:
        raise ValueError("Compute Environment revision is not pinned to this Task")
    task_environment, environment, revision = row
    if (
        environment.lab_id != task.lab_id
        or environment.archived_at is not None
        or not revision.enabled
        or revision.revision != task_environment.compute_environment_revision
    ):
        raise ValueError("Pinned Compute Environment is unavailable")
    return task_environment, environment, revision


async def exact_compute_inputs(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    items: list[tuple[UUID, str]],
) -> list[tuple[DataAsset, DataAssetVersion, str]]:
    result: list[tuple[DataAsset, DataAssetVersion, str]] = []
    seen_versions: set[UUID] = set()
    seen_names: set[str] = set()
    for version_id, mount_name in items:
        if version_id in seen_versions or mount_name in seen_names:
            raise ValueError("Compute input assets and mount names must be unique")
        seen_versions.add(version_id)
        seen_names.add(mount_name)
        row = (
            await db_session.execute(
                select(DataAsset, DataAssetVersion, ResearchFile)
                .join(
                    DataAssetVersion,
                    DataAssetVersion.data_asset_id == DataAsset.id,
                )
                .join(
                    ResearchFile,
                    ResearchFile.id == DataAssetVersion.research_file_id,
                )
                .where(DataAssetVersion.id == version_id)
            )
        ).first()
        if row is None:
            raise ValueError("Compute input DataAsset version was not found")
        asset, version, research_file = row
        if (
            asset.lab_id != task.lab_id
            or asset.project_id != task.project_id
            or asset.archived_at is not None
            or asset.status != DataAssetStatus.READY.value
            or version.research_file_id is None
            or research_file.scope_type not in {"lab", "project"}
            or research_file.lab_id != task.lab_id
            or research_file.project_id not in {None, task.project_id}
            or research_file.visibility in {"private", "restricted"}
            or research_file.archived_at is not None
        ):
            raise ValueError(
                "Compute inputs must be ready, Project-local DataAsset file versions"
            )
        result.append((asset, version, mount_name))
    return result


async def validate_pinned_compute_inputs(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    job_id: UUID,
) -> int:
    """Revalidate every persisted job input before approval and delivery."""

    expected = int(
        await db_session.scalar(
            select(func.count())
            .select_from(ResearchComputeJobInput)
            .where(ResearchComputeJobInput.compute_job_id == job_id)
        )
        or 0
    )
    rows = list(
        (
            await db_session.execute(
                select(
                    ResearchComputeJobInput,
                    DataAsset,
                    DataAssetVersion,
                    ResearchFile,
                )
                .join(DataAsset, DataAsset.id == ResearchComputeJobInput.data_asset_id)
                .join(
                    DataAssetVersion,
                    DataAssetVersion.id
                    == ResearchComputeJobInput.data_asset_version_id,
                )
                .join(
                    ResearchFile,
                    ResearchFile.id == DataAssetVersion.research_file_id,
                )
                .where(ResearchComputeJobInput.compute_job_id == job_id)
            )
        ).all()
    )
    if len(rows) != expected:
        raise ValueError("A pinned Compute input is no longer available")
    for input_row, asset, version, research_file in rows:
        if (
            version.data_asset_id != asset.id
            or input_row.data_asset_id != asset.id
            or asset.lab_id != task.lab_id
            or asset.project_id != task.project_id
            or asset.archived_at is not None
            or asset.status != DataAssetStatus.READY.value
            or research_file.scope_type not in {"lab", "project"}
            or research_file.lab_id != task.lab_id
            or research_file.project_id not in {None, task.project_id}
            or research_file.visibility in {"private", "restricted"}
            or research_file.archived_at is not None
        ):
            raise ValueError("A pinned Compute input is no longer eligible")
    return expected


async def eligible_runner_count(
    db_session: AsyncSession,
    *,
    environment_revision_id: UUID,
    ready_only: bool,
) -> int:
    rows = list(
        (
            await db_session.scalars(
                select(ResearchComputeRunner)
                .join(
                    ResearchComputeRunnerEnvironment,
                    ResearchComputeRunnerEnvironment.runner_id
                    == ResearchComputeRunner.id,
                )
                .where(
                    ResearchComputeRunnerEnvironment.compute_environment_revision_id
                    == environment_revision_id,
                    ResearchComputeRunnerEnvironment.archived_at.is_(None),
                    ResearchComputeRunner.enabled.is_(True),
                    ResearchComputeRunner.revoked_at.is_(None),
                )
            )
        ).all()
    )
    if ready_only:
        rows = [runner for runner in rows if runner_report_is_execution_ready(runner)]
    return len(rows)


async def _append_compute_budget_entry(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
    action: ResearchAction,
    job: ResearchComputeJob,
    kind: str,
    amount: Decimal | None,
    actor_user_id: UUID | None,
    suffix: str,
) -> ResearchBudgetEntry | None:
    if task.budget_limit is None or amount is None or amount <= 0 or not job.currency:
        return None
    idempotency_key = f"compute-job:{job.id}:{suffix}"
    existing = await ResearchBudgetEntry.find_by(
        db_session,
        [
            ResearchBudgetEntry.task_id == task.id,
            ResearchBudgetEntry.idempotency_key == idempotency_key,
        ],
    )
    if existing is not None:
        return existing
    command = {
        "operation": f"compute_budget_{kind}",
        "task_id": str(task.id),
        "run_id": str(run.id),
        "action_id": str(action.id),
        "compute_job_id": str(job.id),
        "amount": str(amount),
        "currency": job.currency,
        "kind": kind,
    }
    entry = ResearchBudgetEntry(
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind=kind,
        amount=amount,
        currency=job.currency,
        source_type="compute_job",
        source_ref=str(job.id),
        description=f"Compute Job using environment revision {job.compute_environment_revision}",
        command_digest=canonical_digest(command),
        created_by_user_id=actor_user_id,
        idempotency_key=idempotency_key,
    )
    db_session.add(entry)
    return entry


async def activate_compute_action(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
    action: ResearchAction,
    actor_user_id: UUID,
) -> ResearchComputeJob:
    job = (
        await db_session.scalars(
            select(ResearchComputeJob)
            .where(ResearchComputeJob.action_id == action.id)
            .with_for_update()
        )
    ).first()
    if job is None or job.status != ResearchComputeJobStatus.AWAITING_APPROVAL.value:
        raise ValueError("Compute Job is not awaiting approval")
    _task_environment, environment, revision = await pinned_compute_environment(
        db_session,
        task=task,
        revision_id=job.compute_environment_revision_id,
        lock=True,
    )
    if (
        revision.revision != job.compute_environment_revision
        or compute_environment_snapshot(environment, revision) != job.environment_snapshot
        or compute_source_digest(job.source_code) != job.source_sha256
    ):
        raise ValueError("Compute Job contract changed before approval")
    await validate_pinned_compute_inputs(db_session, task=task, job_id=job.id)
    if not await eligible_runner_count(
        db_session,
        environment_revision_id=revision.id,
        ready_only=False,
    ):
        raise ValueError("No Compute Runner is authorized for this environment revision")
    if task.budget_limit is not None and job.estimated_cost and job.estimated_cost > 0:
        if not job.currency:
            raise ResearchBudgetError("Compute Environment cost currency is missing")
        snapshot = await research_budget_snapshot(db_session, task=task)
        project_budget_change(
            task=task,
            snapshot=snapshot,
            kind=ResearchBudgetEntryKind.RESERVE.value,
            amount=Decimal(job.estimated_cost),
            currency=job.currency,
        )
        await _append_compute_budget_entry(
            db_session,
            task=task,
            run=run,
            action=action,
            job=job,
            kind=ResearchBudgetEntryKind.RESERVE.value,
            amount=Decimal(job.estimated_cost),
            actor_user_id=actor_user_id,
            suffix="reserve",
        )
    now = utcnow()
    job.status = ResearchComputeJobStatus.QUEUED.value
    job.approved_at = now
    job.queued_at = now
    job.revision += 1
    action.status = ResearchActionStatus.QUEUED.value
    action.policy_decision = "allow"
    action.output_data = {"compute_job_id": str(job.id), "status": job.status}
    action.revision += 1
    run.status = ResearchRunStatus.WAITING_FOR_COMPUTE.value
    run.last_error = None
    return job


async def settle_compute_budget(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
    action: ResearchAction,
    job: ResearchComputeJob,
    wall_seconds: int,
) -> Decimal | None:
    actual = compute_actual_cost(job, wall_seconds)
    job.actual_cost = actual
    if task.budget_limit is None or not job.currency:
        return actual
    estimate = Decimal(job.estimated_cost or 0)
    actual_amount = Decimal(actual or 0)
    if actual_amount > estimate:
        raise ResearchBudgetError("Compute usage exceeds the approved maximum cost")
    if estimate > 0:
        snapshot = await research_budget_snapshot(db_session, task=task)
        released = project_budget_change(
            task=task,
            snapshot=snapshot,
            kind=ResearchBudgetEntryKind.RELEASE.value,
            amount=estimate,
            currency=job.currency,
        )
        if actual_amount > 0:
            project_budget_change(
                task=task,
                snapshot=released,
                kind=ResearchBudgetEntryKind.EXPENSE.value,
                amount=actual_amount,
                currency=job.currency,
            )
        await _append_compute_budget_entry(
            db_session,
            task=task,
            run=run,
            action=action,
            job=job,
            kind=ResearchBudgetEntryKind.RELEASE.value,
            amount=estimate,
            actor_user_id=None,
            suffix="settle-release",
        )
        await _append_compute_budget_entry(
            db_session,
            task=task,
            run=run,
            action=action,
            job=job,
            kind=ResearchBudgetEntryKind.EXPENSE.value,
            amount=actual_amount,
            actor_user_id=None,
            suffix="settle-expense",
        )
    return actual


async def release_compute_budget(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    run: ResearchRun,
    action: ResearchAction,
    job: ResearchComputeJob,
    suffix: str,
    actor_user_id: UUID | None,
) -> None:
    estimate = Decimal(job.estimated_cost or 0)
    if task.budget_limit is None or estimate <= 0 or not job.currency:
        return
    snapshot = await research_budget_snapshot(db_session, task=task)
    project_budget_change(
        task=task,
        snapshot=snapshot,
        kind=ResearchBudgetEntryKind.RELEASE.value,
        amount=estimate,
        currency=job.currency,
    )
    await _append_compute_budget_entry(
        db_session,
        task=task,
        run=run,
        action=action,
        job=job,
        kind=ResearchBudgetEntryKind.RELEASE.value,
        amount=estimate,
        actor_user_id=actor_user_id,
        suffix=suffix,
    )


async def runner_active_job_count(
    db_session: AsyncSession, runner_id: UUID
) -> int:
    return int(
        await db_session.scalar(
            select(func.count())
            .select_from(ResearchComputeJob)
            .where(
                ResearchComputeJob.runner_id == runner_id,
                ResearchComputeJob.status.in_(ACTIVE_COMPUTE_JOB_STATUSES),
            )
        )
        or 0
    )
