"""Deterministic file destination, immutable intake plan and output read models."""

from uuid import uuid5

from fastapi import HTTPException
from sqlalchemy import select

from app.models.instrument_activation import InstrumentActivation
from app.models.instrument_output import InstrumentOutput, InstrumentOutputBatch
from app.models.knowledge import OwnerScope, ResearchFile, ResearchFileBlob
from app.models.research import ResearchAction, ResearchRun, ResearchTask
from app.models.research_asset import DataAssetVersion
from app.models.research_execution import ResearchInstrumentJob
from app.models.resource import EquipmentBooking
from app.models.user import User
from app.services.instrument_output_contract import (
    PLAN_SCHEMA,
    declarations,
    digest,
    validate_plan,
)
from app.services.knowledge import authorize_research_file, resolve_scope


async def receiving_policy(db, task, command):
    row = await db.scalar(
        select(InstrumentActivation).where(
            InstrumentActivation.gateway_id == command.gateway_id,
            InstrumentActivation.resource_id == command.resource_id,
            InstrumentActivation.revoked_at.is_(None),
        )
    )
    if row is None:
        return None
    contract = next(
        (
            item["contract"]
            for item in row.plan["commands"]
            if item["contract"]["key"] == command.command_key
            and item["contract"]["version"] == command.command_version
        ),
        None,
    )
    if contract is None:
        raise HTTPException(409, "Instrument command has no approved file contract")
    outputs = declarations(contract["outputs"])
    if not outputs:
        return None
    return {
        "activation_id": str(row.id),
        "scope_type": "project",
        "lab_id": str(task.lab_id),
        "project_id": str(task.project_id),
        "task_id": str(task.id),
        "visibility": "project",
        "asset_state": "draft",
        "record_association": "awaiting_review",
        "outputs": outputs,
    }


async def authorize_intake(db, user, task, *, read=False):
    from app.routers.research_assets import _task_context

    if user is None:
        raise HTTPException(403, "File intake authority is unavailable")
    await _task_context(db, user, task.id, "research.read" if read else "research.run")
    return await resolve_scope(
        db,
        user,
        scope_type=OwnerScope.PROJECT,
        lab_id=task.lab_id,
        project_id=task.project_id,
        capability="knowledge.read" if read else "knowledge.create",
    )


async def pin_outputs(db, job, command, activation):
    action = await db.get(ResearchAction, job.action_id)
    run = await db.get(ResearchRun, action.run_id)
    task = await db.get(ResearchTask, run.task_id)
    policy = await receiving_policy(db, task, command)
    if policy is None:
        return
    booking = await db.get(EquipmentBooking, job.equipment_booking_id)
    operator = await db.get(User, booking.user_id)
    await authorize_intake(db, operator, task)
    lineage = {
        "type": "instrument_job_output",
        "job_id": str(job.id),
        "action_id": str(action.id),
        "run_id": str(run.id),
        "destination": {
            key: value for key, value in policy.items() if key != "outputs"
        },
        "gateway_id": str(job.gateway_id),
        "resource_id": str(job.resource_id),
        "resource_revision_id": str(job.resource_revision_id),
        "resource_revision": job.resource_revision,
        "command": {
            "id": str(command.id),
            "key": command.command_key,
            "version": command.command_version,
            "revision": command.revision,
        },
        "activation_id": str(activation.id),
        "binding_id": str(activation.binding_id),
        "qualification_id": str(activation.qualification_id),
        "authorization_digest": activation.authorization_digest,
        "installation": activation.plan["descriptor"],
        "target": activation.plan["target"],
    }
    plan = validate_plan(
        {
            "schema": PLAN_SCHEMA,
            "job_id": str(job.id),
            "context_sha256": digest(lineage),
            "outputs": policy["outputs"],
        }
    )
    db.add(
        InstrumentOutputBatch(
            job_id=job.id, created_by_user_id=operator.id, plan=plan, lineage=lineage
        )
    )
    await db.flush()
    for item in plan["outputs"]:
        db.add(
            InstrumentOutput(
                id=uuid5(job.id, item["name"]), job_id=job.id, name=item["name"]
            )
        )
    action.input_data = {**action.input_data, "file_receiving": policy}


async def output_batch(db, job):
    return await db.get(InstrumentOutputBatch, job.id)


async def batch_rows(db, batch):
    return list(
        (
            await db.scalars(
                select(InstrumentOutput)
                .where(InstrumentOutput.job_id == batch.job_id)
                .order_by(InstrumentOutput.name)
            )
        ).all()
    )


async def batch_snapshot(db, batch, *, user=None):
    job = await db.get(ResearchInstrumentJob, batch.job_id)
    state = "delivered" if batch.finalized_at else "awaiting_files"
    if not batch.finalized_at and job.status != "completed":
        state = (
            "execution_stopped"
            if job.status in {"failed", "stopped", "cancelled"}
            else "awaiting_execution"
        )
    capture = {item["name"]: item for item in (batch.capture or {}).get("files", [])}
    rows = await batch_rows(db, batch)
    items = []
    for row in rows:
        item = {
            "id": str(row.id),
            **next(item for item in batch.plan["outputs"] if item["name"] == row.name),
            "state": "awaiting_upload" if row.name in capture else "awaiting_capture",
        }
        if batch.capture is not None and row.name not in capture:
            item["state"] = "omitted"
        if row.research_file_id:
            file = await db.get(ResearchFile, row.research_file_id)
            if file is None or file.archived_at:
                item["state"] = "unavailable"
            else:
                if user is not None:
                    await authorize_research_file(db, user, file)
                blob = await db.get(ResearchFileBlob, file.blob_id)
                version = await db.get(DataAssetVersion, row.data_asset_version_id)
                item.update(
                    state="registered",
                    research_file_id=str(file.id),
                    data_asset_id=str(version.data_asset_id),
                    data_asset_version_id=str(version.id),
                    received_at=row.received_at.isoformat(),
                    **capture[row.name],
                )
                if blob.checksum_sha256 != item["sha256"]:
                    raise HTTPException(
                        409, "Instrument output storage identity changed"
                    )
        items.append(item)
    return {
        "job_id": str(batch.job_id),
        "plan": batch.plan,
        "destination": batch.lineage["destination"],
        "state": state,
        "execution_status": job.status,
        "items": items,
        "finalized_at": batch.finalized_at,
    }
