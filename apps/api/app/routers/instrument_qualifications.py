"""Human acceptance records for installed adapters; no device execution or activation."""

from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import DBSession
from app.models.instrument_qualification import InstrumentQualification
from app.models.knowledge import ResearchFile, ResearchFileBlob
from app.models.resource import Resource
from app.models.user import User
from app.routers.depends import CurrentUser
from app.routers.instrument_installations import (
    RevokeConfirm,
    RevokeDraft,
    _context,
    _managed,
)
from app.services.access_control import resolve_resource_access
from app.services.instrument_qualifications import (
    QualificationDraft,
    binding_invalid_reason,
    command_simulation_only,
    qualification_state,
    validate_command_assessments,
)
from app.services.knowledge import authorize_research_file
from app.services.research_runtime import canonical_digest, utcnow

router = APIRouter(
    prefix="/instrument-installations/{binding_id}", tags=["Instrument qualification"]
)


class QualificationConfirm(QualificationDraft):
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


async def _access(db, user, binding_id, *, lock=False):
    binding = await _managed(db, user, binding_id, lock=lock)
    resource = await db.get(Resource, binding.resource_id)
    access = await resolve_resource_access(
        db,
        user.id,
        binding.lab_id,
        resource_type_id=resource.resource_type_id,
        resource_id=resource.id,
    )
    if not access.allows("equipment.qualify"):
        raise HTTPException(403, "Equipment qualification access denied")
    return binding


async def _files(db, user, binding, ids, *, lock=False):
    pins = []
    for file_id in sorted(ids, key=str):
        query = select(ResearchFile).where(ResearchFile.id == file_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        file = await db.scalar(query)
        if (
            file is None
            or file.archived_at
            or file.scope_type != "lab"
            or file.lab_id != binding.lab_id
        ):
            raise HTTPException(404, "Qualification evidence file unavailable")
        await authorize_research_file(db, user, file)
        blob = await db.get(ResearchFileBlob, file.blob_id)
        if blob is None:
            raise HTTPException(409, "Qualification evidence bytes unavailable")
        pins.append(
            {
                "id": str(file.id),
                "sha256": blob.checksum_sha256,
                "size_bytes": blob.size_bytes,
            }
        )
    return pins


async def _source(db, user, binding, *, lock=False):
    context = await _context(
        db,
        user,
        lab_id=binding.lab_id,
        gateway_id=binding.gateway_id,
        resource_id=binding.resource_id,
        release_id=binding.release_id,
        lock=lock,
    )
    invalid = await binding_invalid_reason(db, binding)
    if invalid:
        raise HTTPException(409, invalid)
    return context[3]


@router.get("/qualification-context")
async def qualification_context(
    binding_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    binding = await _access(db_session, current_user, binding_id)
    release = await _source(db_session, current_user, binding)
    return {
        "binding_id": str(binding.id),
        "descriptor": binding.descriptor,
        "installed_at": binding.installed_at,
        "commands": [
            {
                **command,
                "simulation_only": command_simulation_only(command),
            }
            for command in release.inspection["manifest"]["commands"]
        ],
        "hardware_authorized": False,
    }


async def _preview(db, user, binding, params, *, lock=False):
    release = await _source(db, user, binding, lock=lock)
    draft = QualificationDraft.model_validate(
        params.model_dump(exclude={"preview_digest"})
    )
    if (
        draft.assessed_at > utcnow() + timedelta(minutes=5)
        or draft.expires_at <= utcnow()
    ):
        raise HTTPException(
            422, "Assessment cannot be in the future or already expired"
        )
    if draft.assessed_at < binding.installed_at:
        raise HTTPException(422, "Assessment must follow this installation receipt")
    try:
        commands = validate_command_assessments(draft, release.inspection["manifest"])
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    evidence = await _files(db, user, binding, draft.evidence_file_ids, lock=lock)
    pins = {
        "binding_id": str(binding.id),
        "binding_revision": binding.revision,
        "resource_revision_id": str(binding.resource_revision_id),
        "release_id": str(release.id),
        "release_revision": release.revision,
        "descriptor": binding.descriptor,
        "receipt": binding.receipt,
        "commands": commands,
    }
    result = {
        "operation": "record_instrument_qualification",
        "actor_user_id": str(user.id),
        "report": draft.model_dump(mode="json"),
        "pins": pins,
        "evidence_files": evidence,
        "hardware_authorized": False,
        "activation_performed": False,
    }
    return {**result, "preview_digest": canonical_digest(result)}


async def _snapshot(db, row, binding):
    assessor = await db.get(User, row.created_by_user_id)
    return {
        **row.as_dict(),
        "assessor": {
            "id": str(row.created_by_user_id),
            "name": (assessor.name or assessor.username)
            if assessor
            else str(row.created_by_user_id),
        },
        "effective_state": await qualification_state(db, row, binding),
        "hardware_authorized": False,
        "activation_performed": False,
    }


@router.post("/qualifications/preview")
async def preview_qualification(
    binding_id: UUID,
    params: QualificationDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    binding = await _access(db_session, current_user, binding_id)
    return await _preview(db_session, current_user, binding, params)


@router.post("/qualifications")
async def confirm_qualification(
    binding_id: UUID,
    params: QualificationConfirm,
    current_user: CurrentUser,
    db_session: DBSession,
):
    binding = await _access(db_session, current_user, binding_id, lock=True)
    existing = await db_session.get(InstrumentQualification, params.id)
    if existing:
        if (
            existing.binding_id != binding.id
            or existing.created_by_user_id != current_user.id
            or existing.confirmation_digest != params.preview_digest
            or existing.report
            != QualificationDraft.model_validate(
                params.model_dump(exclude={"preview_digest"})
            ).model_dump(mode="json")
        ):
            raise HTTPException(409, "Qualification identity is already in use")
        await _files(
            db_session,
            current_user,
            binding,
            [UUID(item["id"]) for item in existing.evidence_files],
        )
        return await _snapshot(db_session, existing, binding)
    preview = await _preview(db_session, current_user, binding, params, lock=True)
    if preview["preview_digest"] != params.preview_digest:
        raise HTTPException(409, "Qualification preview changed; review again")
    row = InstrumentQualification(
        id=params.id,
        binding_id=binding.id,
        lab_id=binding.lab_id,
        scope=params.scope,
        outcome="passed"
        if all(check.passed for item in params.commands for check in item.checks)
        else "failed",
        report=preview["report"],
        pins=preview["pins"],
        evidence_files=preview["evidence_files"],
        confirmation_digest=params.preview_digest,
        created_by_user_id=current_user.id,
        assessed_at=params.assessed_at,
        expires_at=params.expires_at,
    )
    db_session.add(row)
    try:
        await db_session.flush()
    except IntegrityError as error:
        await db_session.rollback()
        raise HTTPException(409, "Qualification identity is already in use") from error
    result = jsonable_encoder(await _snapshot(db_session, row, binding))
    await db_session.commit()
    return result


@router.get("/qualifications")
async def list_qualifications(
    binding_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
):
    binding = await _access(db_session, current_user, binding_id)
    rows = (
        await db_session.scalars(
            select(InstrumentQualification)
            .where(InstrumentQualification.binding_id == binding.id)
            .order_by(
                InstrumentQualification.created_at.desc(),
                InstrumentQualification.id.desc(),
            )
            .offset(offset)
            .limit(limit + 1)
        )
    ).all()
    items = []
    for row in rows[:limit]:
        # Recheck evidence access before exposing the private target/report.
        try:
            await _files(
                db_session,
                current_user,
                binding,
                [UUID(item["id"]) for item in row.evidence_files],
            )
        except HTTPException as error:
            if error.status_code in {403, 404}:
                items.append(
                    {
                        "id": str(row.id),
                        "scope": row.scope,
                        "outcome": row.outcome,
                        "effective_state": await qualification_state(
                            db_session, row, binding
                        ),
                        "created_at": row.created_at,
                        "expires_at": row.expires_at,
                        "revoked_at": row.revoked_at,
                        "details_redacted": True,
                        "hardware_authorized": False,
                        "activation_performed": False,
                    }
                )
                continue
            raise
        items.append(await _snapshot(db_session, row, binding))
    return {
        "items": items,
        "has_more": len(rows) > limit,
        "next_offset": offset + min(len(rows), limit),
    }


async def _record(db, user, binding_id, qualification_id, *, lock=False):
    binding = await _access(db, user, binding_id, lock=lock)
    query = select(InstrumentQualification).where(
        InstrumentQualification.id == qualification_id,
        InstrumentQualification.binding_id == binding.id,
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = await db.scalar(query)
    if row is None:
        raise HTTPException(404, "Qualification not found")
    return row, binding


def _revocation(row, user, params):
    if params.expected_revision != 1 or row.revoked_at:
        raise HTTPException(409, "Qualification is already revoked or changed")
    command = {
        "operation": "revoke_instrument_qualification",
        "qualification_id": str(row.id),
        "confirmation_digest": row.confirmation_digest,
        "actor_user_id": str(user.id),
        "reason": params.reason,
    }
    return {
        **command,
        "preview_digest": canonical_digest(command),
        "activation_performed": False,
    }


@router.post("/qualifications/{qualification_id}/revoke/preview")
async def preview_revoke_qualification(
    binding_id: UUID,
    qualification_id: UUID,
    params: RevokeDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    row, _ = await _record(db_session, current_user, binding_id, qualification_id)
    return _revocation(row, current_user, params)


@router.post("/qualifications/{qualification_id}/revoke")
async def revoke_qualification(
    binding_id: UUID,
    qualification_id: UUID,
    params: RevokeConfirm,
    current_user: CurrentUser,
    db_session: DBSession,
):
    row, _binding = await _record(
        db_session, current_user, binding_id, qualification_id, lock=True
    )
    if row.revoked_at:
        command = {
            "operation": "revoke_instrument_qualification",
            "qualification_id": str(row.id),
            "confirmation_digest": row.confirmation_digest,
            "actor_user_id": str(current_user.id),
            "reason": params.reason,
        }
        if (
            row.revoked_by_user_id == current_user.id
            and row.revoke_reason == params.reason
            and canonical_digest(command) == params.preview_digest
            and params.expected_revision == 1
        ):
            return {
                "id": str(row.id),
                "effective_state": "revoked",
                "hardware_authorized": False,
            }
        raise HTTPException(409, "Qualification was already revoked")
    preview = _revocation(row, current_user, params)
    if preview["preview_digest"] != params.preview_digest:
        raise HTTPException(409, "Qualification revocation preview changed")
    row.revoked_at = utcnow()
    row.revoked_by_user_id = current_user.id
    row.revoke_reason = params.reason
    await db_session.commit()
    # Revocation remains available after evidence access is removed. Do not
    # return evidence, private observations or target details from that path.
    return {
        "id": str(row.id),
        "effective_state": "revoked",
        "hardware_authorized": False,
    }
