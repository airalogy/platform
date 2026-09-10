"""Private immutable package import and source review; never execute or install."""

import asyncio
import io
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import cast, column, exists, func, select
from sqlalchemy.dialects.postgresql import JSONB, insert

from app.database import DBSession
from app.libs.file_storage import (
    default_storage_backend,
    default_storage_namespace,
    upload_file,
)
from app.models.instrument_package import (
    InstrumentAdapterRelease,
    InstrumentAdapterReleaseAudit,
)
from app.models.knowledge import OwnerScope, ResearchFile, ResearchFileBlob, Visibility
from app.models.lab import Lab, LabUser
from app.models.user import User
from app.routers.depends import CurrentUser, get_current_user
from app.routers.research_instrument_gateways import _membership
from app.services.instrument_package_contract import MAX_ARCHIVE_BYTES, inspect_package
from app.services.instrument_package_matching import (
    MATCH_TRIM_CHARACTERS,
    AdapterMatchRequest,
    compare_package,
)
from app.services.knowledge import assert_research_file_upload_quota
from app.services.research_instruments import validate_bounded_schema
from app.services.research_runtime import canonical_digest

router = APIRouter(
    prefix="/instrument-adapter-packages", tags=["Instrument adapter packages"]
)
PreviewDigest = Annotated[
    str, Header(alias="X-Airalogy-Preview-Digest", pattern=r"^[a-f0-9]{64}$")
]


async def _authorize(db, user, lab_id, *, lock=False):
    await _membership(db, user=user, lab_id=lab_id)
    if lock:
        # A Lab lock serializes first import of the same package identity. A role
        # change must also finish before (or wait until after) this write decision.
        await db.scalar(select(Lab).where(Lab.id == lab_id).with_for_update())
        await db.scalar(
            select(LabUser)
            .where(LabUser.lab_id == lab_id, LabUser.user_id == user.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        await _membership(db, user=user, lab_id=lab_id)


async def _read_inspection(request: Request):
    try:
        length = int(request.headers.get("content-length", "-1"))
    except ValueError as error:
        raise HTTPException(411, "A bounded Content-Length is required") from error
    if not 1 <= length <= MAX_ARCHIVE_BYTES:
        raise HTTPException(413, "Adapter archive must be at most 64 MiB")
    if (
        request.headers.get("content-type", "").split(";")[0].lower()
        != "application/zip"
    ):
        raise HTTPException(415, "Expected an application/zip adapter archive")
    raw = bytearray()
    try:
        async with asyncio.timeout(120):
            async for chunk in request.stream():
                if len(raw) + len(chunk) > length:
                    raise HTTPException(413, "Archive exceeds its declared length")
                raw.extend(chunk)
    except TimeoutError as error:
        raise HTTPException(408, "Adapter upload timed out") from error
    if len(raw) != length:
        raise HTTPException(422, "Archive byte count changed")
    payload = bytes(raw)
    try:
        inspection = await asyncio.to_thread(inspect_package, payload)
        for command in inspection["manifest"]["commands"]:
            validate_bounded_schema(command["input_schema"], "input")
            validate_bounded_schema(command["output_schema"], "output")
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return payload, inspection


async def _existing(db, lab_id, request_id, inspection):
    by_id = await db.get(InstrumentAdapterRelease, request_id)
    if by_id is not None and (
        by_id.lab_id != lab_id or by_id.archive_digest != inspection["archive_digest"]
    ):
        raise HTTPException(409, "Import identity is already in use")
    manifest = inspection["manifest"]
    row = await db.scalar(
        select(InstrumentAdapterRelease).where(
            InstrumentAdapterRelease.lab_id == lab_id,
            InstrumentAdapterRelease.package_key == manifest["id"],
            InstrumentAdapterRelease.package_version == manifest["version"],
        )
    )
    if row is not None and row.archive_digest != inspection["archive_digest"]:
        raise HTTPException(
            409,
            "This package version already has different content; publish a new version",
        )
    return row


def _import_preview(user_id, lab_id, request_id, inspection, existing):
    command = {
        "operation": "import_instrument_adapter_package",
        "actor_user_id": str(user_id),
        "lab_id": str(lab_id),
        "request_id": str(request_id),
        "archive_digest": inspection["archive_digest"],
        "manifest_digest": inspection["manifest_digest"],
    }
    return {
        **command,
        "preview_digest": canonical_digest(command),
        "inspection": inspection,
        "existing_release_id": str(existing.id) if existing else None,
        "visibility": "lab",
        "hardware_authorized": False,
        "installation_authorized": False,
    }


async def _fresh_user(db, request, actor_id):
    db.expire_all()
    user = await get_current_user(db, request, request.headers.get("auth-token", ""))
    if user.id != actor_id:
        raise HTTPException(403, "Authenticated identity changed")
    return user


def _snapshot(row):
    return {
        "release_id": str(row.id),
        "lab_id": str(row.lab_id),
        "archive_digest": row.archive_digest,
        "manifest_digest": row.manifest_digest,
        "state": row.state,
        "revision": row.revision,
        "hardware_authorized": False,
        "installation_authorized": False,
    }


def _audit(db, row, user_id, action, reason):
    db.add(
        InstrumentAdapterReleaseAudit(
            release_id=row.id,
            revision=row.revision,
            actor_user_id=user_id,
            action=action,
            reason=reason,
            snapshot=_snapshot(row),
        )
    )


@router.post("/preview")
async def preview_import(
    request: Request,
    lab_id: UUID,
    request_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    actor_id = current_user.id
    await _authorize(db_session, current_user, lab_id)
    _raw, inspection = await _read_inspection(request)
    user = await _fresh_user(db_session, request, actor_id)
    await _authorize(db_session, user, lab_id)
    existing = await _existing(db_session, lab_id, request_id, inspection)
    return _import_preview(actor_id, lab_id, request_id, inspection, existing)


@router.post("")
async def import_package(
    request: Request,
    lab_id: UUID,
    request_id: UUID,
    preview_digest: PreviewDigest,
    current_user: CurrentUser,
    db_session: DBSession,
):
    actor_id = current_user.id
    await _authorize(db_session, current_user, lab_id)
    raw, inspection = await _read_inspection(request)
    user = await _fresh_user(db_session, request, actor_id)
    await _authorize(db_session, user, lab_id, lock=True)
    existing = await _existing(db_session, lab_id, request_id, inspection)
    expected = _import_preview(actor_id, lab_id, request_id, inspection, existing)
    if preview_digest != expected["preview_digest"]:
        raise HTTPException(
            409, "Package content or destination changed; preview again"
        )
    if existing is not None:
        # A response-loss retry returns the same immutable release, without
        # replacing content, resurrecting a revoked version or adding file quota.
        return existing.as_dict()
    await db_session.scalar(select(User).where(User.id == actor_id).with_for_update())
    await assert_research_file_upload_quota(db_session, actor_id, len(raw))
    checksum = inspection["archive_digest"]
    object_key = f"knowledge/blobs/{checksum[:2]}/{checksum}"
    blob = await db_session.scalar(
        select(ResearchFileBlob).where(ResearchFileBlob.checksum_sha256 == checksum)
    )
    if blob is None:
        await upload_file(
            object_key, io.BytesIO(raw), content_type="application/zip", length=len(raw)
        )
        await db_session.execute(
            insert(ResearchFileBlob)
            .values(
                checksum_sha256=checksum,
                content_type="application/zip",
                size_bytes=len(raw),
                storage_backend=default_storage_backend(),
                storage_namespace=default_storage_namespace(),
                storage_object_key=object_key,
                extracted_text="",
            )
            .on_conflict_do_nothing(index_elements=["checksum_sha256"])
        )
        blob = await db_session.scalar(
            select(ResearchFileBlob).where(ResearchFileBlob.checksum_sha256 == checksum)
        )
    if blob is None or blob.size_bytes != len(raw):
        raise HTTPException(409, "Stored package content conflicts")
    manifest = inspection["manifest"]
    research_file = ResearchFile(
        blob_id=blob.id,
        filename=f"{manifest['id']}-{manifest['version']}.zip",
        scope_type=OwnerScope.LAB.value,
        lab_id=lab_id,
        visibility=Visibility.LAB.value,
        uploaded_by_user_id=actor_id,
    )
    db_session.add(research_file)
    await db_session.flush()
    row = InstrumentAdapterRelease(
        id=request_id,
        lab_id=lab_id,
        research_file_id=research_file.id,
        package_key=manifest["id"],
        package_version=manifest["version"],
        archive_digest=checksum,
        manifest_digest=inspection["manifest_digest"],
        inspection=inspection,
        state="imported",
        revision=1,
        created_by_user_id=actor_id,
        updated_by_user_id=actor_id,
    )
    db_session.add(row)
    await db_session.flush()
    _audit(
        db_session,
        row,
        actor_id,
        "imported",
        "Confirmed exact package content and Lab destination",
    )
    await db_session.commit()
    await db_session.refresh(row)
    return row.as_dict()


@router.get("")
async def list_packages(
    lab_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
):
    await _authorize(db_session, current_user, lab_id)
    rows = (
        await db_session.scalars(
            select(InstrumentAdapterRelease)
            .where(InstrumentAdapterRelease.lab_id == lab_id)
            .order_by(
                InstrumentAdapterRelease.created_at.desc(),
                InstrumentAdapterRelease.id.desc(),
            )
            .offset(offset)
            .limit(limit + 1)
        )
    ).all()
    return {
        "items": [row.as_dict() for row in rows[:limit]],
        "has_more": len(rows) > limit,
    }


@router.post("/match")
async def match_packages(
    lab_id: UUID,
    params: AdapterMatchRequest,
    current_user: CurrentUser,
    db_session: DBSession,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=20),
):
    await _authorize(db_session, current_user, lab_id)
    # Filter inside the Lab-scoped query, before pagination. A match on two
    # different declaration rows must not create a fictitious device model.
    declarations = (
        func.jsonb_array_elements(
            cast(
                InstrumentAdapterRelease.inspection["manifest"]["compatibility"][
                    "declared"
                ],
                JSONB,
            )
        )
        .table_valued(column("value", JSONB))
        .alias("declaration")
    )
    has_model = exists(
        select(1)
        .select_from(declarations)
        .where(
            func.btrim(
                declarations.c.value["manufacturer"].astext, MATCH_TRIM_CHARACTERS
            )
            == params.profile.manufacturer,
            func.btrim(declarations.c.value["model"].astext, MATCH_TRIM_CHARACTERS)
            == params.profile.model,
        )
    )
    statement = select(InstrumentAdapterRelease).where(
        InstrumentAdapterRelease.lab_id == lab_id, has_model
    )
    if not params.include_revoked:
        statement = statement.where(InstrumentAdapterRelease.state != "revoked")
    rows = (
        await db_session.scalars(
            statement.order_by(
                InstrumentAdapterRelease.created_at.desc(),
                InstrumentAdapterRelease.id.desc(),
            )
            .offset(offset)
            .limit(limit + 1)
        )
    ).all()
    items = []
    for row in rows[:limit]:
        manifest = row.inspection["manifest"]
        items.append(
            {
                "release": {
                    "id": str(row.id),
                    "lab_id": str(row.lab_id),
                    "package_key": row.package_key,
                    "package_version": row.package_version,
                    "archive_digest": row.archive_digest,
                    "manifest_digest": row.manifest_digest,
                    "state": row.state,
                    "revision": row.revision,
                },
                "comparison": compare_package(manifest, params.profile),
            }
        )
    # No model, file download, installation grant or new qualification is made.
    return {
        "profile": params.profile.model_dump(),
        "items": items,
        "has_more": len(rows) > limit,
        "next_offset": offset + len(items),
        "hardware_authorized": False,
        "installation_authorized": False,
        "qualification_checked": False,
        "model_called": False,
    }


async def _release(db, user, release_id, *, lock=False):
    row = await db.get(InstrumentAdapterRelease, release_id)
    if row is None:
        raise HTTPException(404, "Adapter release not found")
    await _authorize(db, user, row.lab_id, lock=lock)
    if lock:
        row = await db.scalar(
            select(InstrumentAdapterRelease)
            .where(InstrumentAdapterRelease.id == release_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    return row


@router.get("/{release_id}")
async def get_package(
    release_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    # Search results are only a snapshot; inspect/review fresh state separately.
    return (await _release(db_session, current_user, release_id)).as_dict()


@router.get("/{release_id}/history")
async def release_history(
    release_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    await _release(db_session, current_user, release_id)
    rows = (
        await db_session.scalars(
            select(InstrumentAdapterReleaseAudit)
            .where(InstrumentAdapterReleaseAudit.release_id == release_id)
            .order_by(InstrumentAdapterReleaseAudit.revision)
        )
    ).all()
    return {"items": [row.as_dict() for row in rows]}


class ReviewDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    operation: Literal["approve_source", "revoke"]
    reason: str = Field(min_length=1, max_length=2000)
    source_reviewed: bool = False

    @model_validator(mode="after")
    def normalize(self):
        self.reason = self.reason.strip()
        if not self.reason or (
            self.operation == "approve_source" and not self.source_reviewed
        ):
            raise ValueError(
                "Source approval requires an explicit source review and reason"
            )
        return self


class ReviewConfirm(ReviewDraft):
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


def _review_preview(row, user_id, params):
    if row.revision != params.expected_revision:
        raise HTTPException(409, "Package review changed; reload before previewing")
    if row.state == "revoked" or (
        params.operation == "approve_source" and row.state != "imported"
    ):
        raise HTTPException(409, "This source review transition is unavailable")
    command = {
        **_snapshot(row),
        "actor_user_id": str(user_id),
        "operation": params.operation,
        "reason": params.reason,
        "source_reviewed": params.source_reviewed,
    }
    return {**command, "preview_digest": canonical_digest(command)}


@router.post("/{release_id}/review/preview")
async def preview_review(
    release_id: UUID,
    params: ReviewDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    row = await _release(db_session, current_user, release_id)
    return _review_preview(row, current_user.id, params)


@router.post("/{release_id}/review")
async def confirm_review(
    release_id: UUID,
    params: ReviewConfirm,
    current_user: CurrentUser,
    db_session: DBSession,
):
    row = await _release(db_session, current_user, release_id, lock=True)
    preview = _review_preview(row, current_user.id, params)
    if preview["preview_digest"] != params.preview_digest:
        raise HTTPException(409, "Source review preview changed")
    row.state = "approved" if params.operation == "approve_source" else "revoked"
    row.revision += 1
    row.updated_by_user_id = current_user.id
    _audit(db_session, row, current_user.id, row.state, params.reason)
    await db_session.commit()
    await db_session.refresh(row)
    return row.as_dict()
