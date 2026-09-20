"""Reviewed ordinary Protocol packages derived from explicit method snapshots.

This service governs assets, not execution. Analysis still runs through the
existing analysis/Workflow worker; neither a draft nor its approval starts it.
"""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select

from app.config import config
from app.libs.protocol_uid import lock_protocol_uid
from app.models.analysis_protocol import (
    AnalysisProtocolDraft,
    AnalysisProtocolDraftReview,
    AnalysisProtocolDraftRevision,
    AnalysisProtocolMethodLink,
)
from app.models.lab import Lab
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.user import User
from app.routers.permission import check_user_permission
from app.services.analysis_engine import canonical_digest
from app.services.analysis_protocol_packages import (
    AnalysisProtocolPackageError,
    AnalysisProtocolPackageRequest,
    build_analysis_protocol_package,
    validate_analysis_protocol_package,
)
from app.services.research_runtime import has_research_capability, utcnow
from app.services.workflow_analysis_methods import get_method
from app.services.workflow_definitions import request_lock, scope

AUDIENCE = "airalogy.analysis-protocol-draft-preview"
PREVIEW_TTL = timedelta(minutes=30)
MAX_REVISIONS = 100


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DraftTemplate(StrictRequest):
    method_id: UUID
    target_protocol_id: UUID | None = None


class DraftContent(DraftTemplate):
    base_protocol_version_id: UUID | None = None
    files: dict[str, str] = Field(min_length=3, max_length=3)
    reason: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def exact_target(self):
        if (self.target_protocol_id is None) != (self.base_protocol_version_id is None):
            raise ValueError(
                "Target Protocol and exact base version are required together"
            )
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("A draft revision reason is required")
        return self


class PreviewReceipt(StrictRequest):
    preview_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preview_token: str = Field(min_length=1, max_length=8000)


class DraftConfirm(DraftContent, PreviewReceipt):
    idempotency_key: UUID


class RevisionContent(StrictRequest):
    expected_revision: int = Field(ge=1)
    files: dict[str, str] = Field(min_length=3, max_length=3)
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value):
        if not value.strip():
            raise ValueError("A draft revision reason is required")
        return value.strip()


class RevisionConfirm(RevisionContent, PreviewReceipt):
    idempotency_key: UUID


class ExactRevision(StrictRequest):
    expected_revision: int = Field(ge=1)
    package_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReviewRequest(ExactRevision):
    decision: Literal["reviewed", "rejected"]
    note: str = Field(min_length=1, max_length=4000)

    @field_validator("note")
    @classmethod
    def meaningful_note(cls, value):
        if not value.strip():
            raise ValueError("A review note is required")
        return value.strip()


class PublishConfirm(ExactRevision, PreviewReceipt):
    pass


def metadata_dict(package):
    metadata = package.metadata
    return metadata.model_dump() if hasattr(metadata, "model_dump") else dict(metadata)


def _package(method, files=None):
    try:
        original = build_analysis_protocol_package(
            method,
            AnalysisProtocolPackageRequest(
                uid="analysis_method",
                name="Analysis method",
                version="0.1.0",
                locale="en",
            ),
        )
        return (
            original
            if files is None
            else validate_analysis_protocol_package(
                files, expected_manifest_digest=original.manifest_digest
            )
        )
    except (AnalysisProtocolPackageError, ValueError, TypeError) as error:
        raise HTTPException(422, str(error)) from error


async def target_context(db, user, method, target_id=None, base_id=None, *, lock=False):
    project = await scope(db, user, method.project_id)
    if lock:
        project = await db.scalar(
            select(Project)
            .where(Project.id == method.project_id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        # Keep the explicitly confirmed destination and visibility stable until
        # commit, including during the real Protocol parser and file upload.
        await scope(db, user, project.id)
    protocol = version = None
    if target_id is not None:
        query = select(Protocol).where(Protocol.id == target_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        protocol = await db.scalar(query)
        if (
            protocol is None
            or protocol.deleted_at is not None
            or protocol.project_id != project.id
        ):
            raise HTTPException(404, "Target Protocol not found in this Project")
        version = await db.scalar(
            select(ProtocolVersion).where(
                ProtocolVersion.protocol_id == protocol.id,
                ProtocolVersion.version == protocol.latest_version,
            )
        )
        if version is None:
            raise HTTPException(409, "Target Protocol version is unavailable")
        if base_id is not None and version.id != base_id:
            raise HTTPException(409, "Target Protocol advanced; create a fresh draft")
    elif base_id is not None:
        raise HTTPException(422, "A base version requires its exact target Protocol")
    return project, protocol, version


async def require_target_write(db, user, project, protocol):
    try:
        await check_user_permission(
            db,
            project=project,
            user=user,
            action="update_protocol" if protocol is not None else "create_protocol",
            protocol=protocol,
        )
    except HTTPException as error:
        if error.status_code == 400 and error.detail == "Permission denied":
            raise HTTPException(403, "Protocol write access denied") from error
        raise


async def destination(db, project):
    lab = await db.get(Lab, project.lab_id)
    return {
        "project_id": str(project.id),
        "name": project.name,
        "visibility": "private" if project.is_private else "public",
        "lab_uid": lab.uid,
        "project_uid": project.uid,
    }


async def template(db, user, params):
    method = await get_method(db, user, params.method_id)
    project, protocol, version = await target_context(
        db, user, method, params.target_protocol_id
    )
    await require_target_write(db, user, project, protocol)
    try:
        package = build_analysis_protocol_package(
            method,
            AnalysisProtocolPackageRequest(
                uid=protocol.uid
                if protocol
                else f"analysis_{str(method.id).replace('-', '')}",
                name=protocol.name if protocol else " ".join(method.title.split()),
                # A suggested draft is not a version write. The user must set
                # an explicitly higher version before previewing an update.
                version=version.version if version else "0.1.0",
                locale="en",
            ),
        )
    except (AnalysisProtocolPackageError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    return {
        "method_id": str(method.id),
        "project_id": str(project.id),
        "target_protocol_id": str(protocol.id) if protocol else None,
        "base_protocol_version_id": str(version.id) if version else None,
        "files": package.files,
        "destination": await destination(db, project),
        "permissions": {"can_create": True},
    }


def _receipt(*, user_id, purpose, digest):
    now = datetime.now(UTC)
    expires = now + PREVIEW_TTL
    token = jwt.encode(
        {
            "aud": AUDIENCE,
            "sub": str(user_id),
            "purpose": purpose,
            "digest": digest,
            "iat": now,
            "exp": expires,
        },
        config.SECRET_KEY,
        algorithm="HS256",
    )
    return token, expires.isoformat()


def verify_receipt(token, *, user_id, purpose, digest):
    try:
        value = jwt.decode(
            token, config.SECRET_KEY, algorithms=["HS256"], audience=AUDIENCE
        )
        if any(
            value.get(key) != expected
            for key, expected in {
                "sub": str(user_id),
                "purpose": purpose,
                "digest": digest,
            }.items()
        ):
            raise ValueError("Preview identity changed")
    except (JWTError, ValueError) as error:
        raise HTTPException(
            409, "Draft preview changed or expired; preview again"
        ) from error


def files_manifest(files):
    return [
        {
            "path": path,
            "size_bytes": len(text.encode()),
            "sha256": sha256(text.encode()).hexdigest(),
        }
        for path, text in sorted(files.items())
    ]


async def preview_content(db, user, params, *, purpose="create", lock=False):
    method = await get_method(db, user, params.method_id)
    project, protocol, version = await target_context(
        db,
        user,
        method,
        params.target_protocol_id,
        params.base_protocol_version_id,
        lock=lock,
    )
    await require_target_write(db, user, project, protocol)
    package = _package(method, params.files)
    metadata = metadata_dict(package)
    if lock and protocol is None:
        # Serialize the same new UID across different drafts and publishers.
        await lock_protocol_uid(db, project.id, metadata["id"])
    if protocol is not None:
        from app.routers.protocol_versions import is_new_version

        if metadata["id"] != protocol.uid or not is_new_version(
            version.version, metadata["version"]
        ):
            raise HTTPException(
                422, "Keep the target Protocol ID and explicitly increase its version"
            )
    elif await db.scalar(
        select(Protocol.id).where(
            Protocol.project_id == project.id,
            Protocol.uid == metadata["id"],
            Protocol.deleted_at.is_(None),
        )
    ):
        raise HTTPException(
            409,
            "Protocol ID already exists; choose a new ID or an explicit version update",
        )
    content = DraftContent.model_validate(params.model_dump()).model_dump(mode="json")
    target = await destination(db, project)
    digest = canonical_digest(
        {
            "schema": "airalogy.analysis-protocol-draft-preview.v1",
            "user_id": str(user.id),
            "purpose": purpose,
            "content": content,
            "project_id": str(project.id),
            "method_digest": method.digest,
            "package_digest": package.content_digest,
            "destination": target,
        }
    )
    token, expires = _receipt(user_id=user.id, purpose=purpose, digest=digest)
    return {
        "preview_digest": digest,
        "preview_token": token,
        "expires_at": expires,
        "content": {**content, "project_id": str(project.id)},
        "package_digest": package.content_digest,
        "manifest_digest": package.manifest_digest,
        "method_digest": method.digest,
        "files_manifest": files_manifest(package.files),
        "destination": target,
    }


async def get_draft(db, user, draft_id, *, lock=False):
    query = select(AnalysisProtocolDraft).where(AnalysisProtocolDraft.id == draft_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = await db.scalar(query)
    if row is None:
        raise HTTPException(404, "Analysis Protocol draft not found")
    method = await get_method(db, user, row.method_id)
    await scope(db, user, row.project_id)
    if method.project_id != row.project_id:
        raise HTTPException(409, "Draft source scope changed")
    return row, method


async def revision_row(db, draft, revision=None):
    row = await db.get(
        AnalysisProtocolDraftRevision, (draft.id, revision or draft.revision)
    )
    if row is None:
        raise HTTPException(409, "Draft revision is unavailable")
    return row


def verify_revision(method, row):
    package = _package(method, row.files)
    if (package.content_digest, package.manifest_digest, method.digest) != (
        row.package_digest,
        row.manifest_digest,
        row.method_digest,
    ):
        raise HTTPException(409, "Stored Protocol draft integrity check failed")
    return package


def revision_payload(row, *, include_files=False):
    result = {
        "draft_id": str(row.draft_id),
        "revision": row.revision,
        "package_digest": row.package_digest,
        "manifest_digest": row.manifest_digest,
        "method_digest": row.method_digest,
        "reason": row.reason,
        "created_by_user_id": str(row.created_by_user_id),
        "created_at": row.created_at.isoformat(),
    }
    if include_files:
        result["files"] = deepcopy(row.files)
    return result


async def permissions(db, user, draft, method):
    write = False
    try:
        project, protocol, _ = await target_context(
            db, user, method, draft.target_protocol_id
        )
        await require_target_write(db, user, project, protocol)
        write = True
    except HTTPException as error:
        if error.status_code not in {400, 403, 404, 409}:
            raise
        project = await scope(db, user, draft.project_id)
    reviewer = await has_research_capability(
        db, user=user, project=project, capability="research.approve"
    )
    return {
        "can_edit": write
        and draft.created_by_user_id == user.id
        and draft.state != "applied",
        "can_review": write and reviewer and draft.state == "draft",
        "can_publish": write
        and (reviewer or draft.created_by_user_id == user.id)
        and draft.state == "reviewed",
    }


async def draft_payload(db, user, draft, method, *, summary=False):
    current = await revision_row(db, draft)
    package = verify_revision(method, current)
    result = {
        "id": str(draft.id),
        "project_id": str(draft.project_id),
        "method_id": str(draft.method_id),
        "target_protocol_id": str(draft.target_protocol_id)
        if draft.target_protocol_id
        else None,
        "base_protocol_version_id": str(draft.base_protocol_version_id)
        if draft.base_protocol_version_id
        else None,
        "created_by_user_id": str(draft.created_by_user_id),
        "revision": draft.revision,
        "state": draft.state,
        "name": metadata_dict(package)["name"],
        "package_digest": current.package_digest,
        "permissions": await permissions(db, user, draft, method),
        "destination": await destination(db, await scope(db, user, draft.project_id)),
    }
    if summary:
        return result
    revisions = list(
        (
            await db.scalars(
                select(AnalysisProtocolDraftRevision)
                .where(AnalysisProtocolDraftRevision.draft_id == draft.id)
                .order_by(AnalysisProtocolDraftRevision.revision)
            )
        ).all()
    )
    reviews = list(
        (
            await db.scalars(
                select(AnalysisProtocolDraftReview)
                .where(AnalysisProtocolDraftReview.draft_id == draft.id)
                .order_by(AnalysisProtocolDraftReview.revision)
            )
        ).all()
    )
    link = await db.scalar(
        select(AnalysisProtocolMethodLink).where(
            AnalysisProtocolMethodLink.draft_id == draft.id
        )
    )
    applied = None
    if link:
        protocol = await db.get(Protocol, link.protocol_id)
        version = await db.get(ProtocolVersion, link.protocol_version_id)
        project = await scope(db, user, draft.project_id)
        await check_user_permission(
            db, user=user, project=project, action="read_protocol", protocol=protocol
        )
        target = await destination(db, project)
        applied = {
            "protocol_id": str(protocol.id),
            "protocol_version_id": str(version.id),
            "version": version.version,
            "protocol_uid": protocol.uid,
            "lab_uid": target["lab_uid"],
            "project_uid": target["project_uid"],
        }
    result.update(
        {
            "current_revision": revision_payload(current, include_files=True),
            "revisions": [revision_payload(row) for row in revisions],
            "reviews": [
                {
                    "id": str(row.id),
                    "revision": row.revision,
                    "decision": row.decision,
                    "package_digest": row.package_digest,
                    "note": row.note,
                    "reviewed_by_user_id": str(row.reviewed_by_user_id),
                    "created_at": row.created_at.isoformat(),
                }
                for row in reviews
            ],
            "applied": applied,
        }
    )
    return result


def _create_revision(draft, user, content, preview, key, request_digest):
    return AnalysisProtocolDraftRevision(
        draft_id=draft.id,
        revision=draft.revision,
        files=deepcopy(content.files),
        package_digest=preview["package_digest"],
        manifest_digest=preview["manifest_digest"],
        method_digest=preview["method_digest"],
        reason=content.reason,
        created_by_user_id=user.id,
        idempotency_key=key,
        request_digest=request_digest,
    )


async def create_draft(db, user, params):
    content = DraftContent.model_validate(
        params.model_dump(include=set(DraftContent.model_fields))
    )
    fingerprint = canonical_digest(content.model_dump(mode="json"))
    await request_lock(db, user.id, f"analysis-protocol:{params.idempotency_key}")
    existing = await db.scalar(
        select(AnalysisProtocolDraft).where(
            AnalysisProtocolDraft.created_by_user_id == user.id,
            AnalysisProtocolDraft.idempotency_key == params.idempotency_key,
        )
    )
    if existing:
        if existing.request_digest != fingerprint:
            raise HTTPException(409, "Draft creation key belongs to another request")
        return await get_draft(db, user, existing.id)
    verify_receipt(
        params.preview_token,
        user_id=user.id,
        purpose="create",
        digest=params.preview_digest,
    )
    preview = await preview_content(db, user, content, lock=True)
    if preview["preview_digest"] != params.preview_digest:
        raise HTTPException(409, "Draft content or destination changed; preview again")
    draft = AnalysisProtocolDraft(
        project_id=UUID(preview["content"]["project_id"]),
        method_id=content.method_id,
        target_protocol_id=content.target_protocol_id,
        base_protocol_version_id=content.base_protocol_version_id,
        created_by_user_id=user.id,
        revision=1,
        state="draft",
        idempotency_key=params.idempotency_key,
        request_digest=fingerprint,
    )
    db.add(draft)
    await db.flush()
    db.add(
        _create_revision(
            draft, user, content, preview, params.idempotency_key, fingerprint
        )
    )
    await db.flush()
    return draft, await get_method(db, user, draft.method_id)


def revision_content(draft, params):
    return DraftContent(
        method_id=draft.method_id,
        target_protocol_id=draft.target_protocol_id,
        base_protocol_version_id=draft.base_protocol_version_id,
        files=params.files,
        reason=params.reason,
    )


async def preview_revision(db, user, draft_id, params, *, lock=False):
    draft, method = await get_draft(db, user, draft_id, lock=lock)
    if draft.revision != params.expected_revision or draft.revision >= MAX_REVISIONS:
        raise HTTPException(409, "Draft revision changed or reached its limit")
    if not (await permissions(db, user, draft, method))["can_edit"]:
        raise HTTPException(
            403,
            "Only the author can edit an unapplied draft with Protocol write access",
        )
    content = revision_content(draft, params)
    return await preview_content(
        db, user, content, purpose=f"revise:{draft.id}:{draft.revision}", lock=lock
    )


async def confirm_revision(db, user, draft_id, params):
    draft, method = await get_draft(db, user, draft_id, lock=True)
    fingerprint = canonical_digest(
        {
            "expected_revision": params.expected_revision,
            **revision_content(draft, params).model_dump(mode="json"),
        }
    )
    existing = await db.scalar(
        select(AnalysisProtocolDraftRevision).where(
            AnalysisProtocolDraftRevision.draft_id == draft.id,
            AnalysisProtocolDraftRevision.idempotency_key == params.idempotency_key,
        )
    )
    if existing:
        if (
            existing.request_digest != fingerprint
            or existing.created_by_user_id != user.id
        ):
            raise HTTPException(409, "Draft revision key belongs to another request")
        verify_revision(method, existing)
        return draft, method
    purpose = f"revise:{draft.id}:{params.expected_revision}"
    verify_receipt(
        params.preview_token,
        user_id=user.id,
        purpose=purpose,
        digest=params.preview_digest,
    )
    preview = await preview_revision(db, user, draft.id, params, lock=True)
    if preview["preview_digest"] != params.preview_digest:
        raise HTTPException(409, "Draft content or destination changed; preview again")
    draft.revision += 1
    draft.state = "draft"
    draft.updated_at = utcnow()
    await db.flush()
    db.add(
        _create_revision(
            draft,
            user,
            revision_content(draft, params),
            preview,
            params.idempotency_key,
            fingerprint,
        )
    )
    await db.flush()
    return draft, method


async def review_draft(db, user, draft_id, params):
    draft, method = await get_draft(db, user, draft_id, lock=True)
    current = await revision_row(db, draft)
    verify_revision(method, current)
    if (
        draft.revision != params.expected_revision
        or current.package_digest != params.package_digest
    ):
        raise HTTPException(409, "Review must target the current exact package")
    flags = await permissions(db, user, draft, method)
    existing = await db.scalar(
        select(AnalysisProtocolDraftReview).where(
            AnalysisProtocolDraftReview.draft_id == draft.id,
            AnalysisProtocolDraftReview.revision == draft.revision,
        )
    )
    if existing:
        if (existing.decision, existing.note, existing.reviewed_by_user_id) != (
            params.decision,
            params.note.strip(),
            user.id,
        ):
            raise HTTPException(409, "This revision already has a final review")
        return draft, method
    if not flags["can_review"] or not params.note.strip():
        raise HTTPException(
            403, "Review requires current approval and Protocol write authority"
        )
    # A stale base version cannot be approved just because the author still has access.
    await target_context(
        db,
        user,
        method,
        draft.target_protocol_id,
        draft.base_protocol_version_id,
        lock=True,
    )
    db.add(
        AnalysisProtocolDraftReview(
            draft_id=draft.id,
            revision=draft.revision,
            decision=params.decision,
            package_digest=current.package_digest,
            note=params.note.strip(),
            reviewed_by_user_id=user.id,
        )
    )
    await db.flush()
    draft.state = params.decision
    draft.updated_at = utcnow()
    await db.flush()
    return draft, method


async def approved_package(db, user, draft_id, params, *, lock=False):
    draft, method = await get_draft(db, user, draft_id, lock=lock)
    current = await revision_row(db, draft)
    package = verify_revision(method, current)
    if (
        draft.revision != params.expected_revision
        or current.package_digest != params.package_digest
    ):
        raise HTTPException(
            409, "Publication must target the current exact reviewed package"
        )
    if (
        draft.state != "reviewed"
        or not (await permissions(db, user, draft, method))["can_publish"]
    ):
        raise HTTPException(
            403, "An eligible publisher and a reviewed draft are required"
        )
    review = await db.scalar(
        select(AnalysisProtocolDraftReview).where(
            AnalysisProtocolDraftReview.draft_id == draft.id,
            AnalysisProtocolDraftReview.revision == draft.revision,
        )
    )
    if (
        review is None
        or review.decision != "reviewed"
        or review.package_digest != current.package_digest
    ):
        raise HTTPException(409, "Exact Protocol draft review is missing")
    reviewer = await db.get(User, review.reviewed_by_user_id)
    project, protocol, _ = await target_context(
        db,
        user,
        method,
        draft.target_protocol_id,
        draft.base_protocol_version_id,
        lock=lock,
    )
    if reviewer is None or not await has_research_capability(
        db, user=reviewer, project=project, capability="research.approve"
    ):
        raise HTTPException(403, "The reviewer no longer has approval authority")
    await get_method(db, reviewer, draft.method_id)
    await require_target_write(db, reviewer, project, protocol)
    return draft, method, current, package, review


async def preview_publish(db, user, draft_id, params, *, lock=False):
    draft, _method, current, _package_value, review = await approved_package(
        db, user, draft_id, params, lock=lock
    )
    preview = await preview_content(
        db,
        user,
        revision_content(draft, current),
        purpose=f"publish:{draft.id}:{draft.revision}",
        lock=lock,
    )
    # The signed preview also identifies the exact human review. It cannot be
    # replayed as a create/revise request or authorize a different approval.
    digest = canonical_digest(
        {"preview": preview["preview_digest"], "review_id": str(review.id)}
    )
    token, expires = _receipt(
        user_id=user.id, purpose=f"publish:{draft.id}:{draft.revision}", digest=digest
    )
    preview.update(preview_digest=digest, preview_token=token, expires_at=expires)
    return preview


async def link_published_version(db, user, draft, current, protocol, version):
    # Called by ordinary POST /protocols inside the same database transaction,
    # after its real package parser and before commit.
    db.add(
        AnalysisProtocolMethodLink(
            protocol_version_id=version.id,
            protocol_id=protocol.id,
            draft_id=draft.id,
            revision=current.revision,
            method_id=draft.method_id,
            package_digest=current.package_digest,
            applied_by_user_id=user.id,
        )
    )
    await db.flush()
    draft.state = "applied"
    draft.updated_at = utcnow()
    await db.flush()


async def protocol_method_sources(db, user, protocol, version):
    """Package content is not authority; only a checked exact-version link is."""
    if user is None:
        return []
    link = await db.get(AnalysisProtocolMethodLink, version.id)
    if link is None:
        return []
    try:
        draft, method = await get_draft(db, user, link.draft_id)
    except HTTPException as error:
        if error.status_code in {400, 403, 404}:
            return []
        raise
    revision = await revision_row(db, draft, link.revision)
    verify_revision(method, revision)
    if (
        link.protocol_id != protocol.id
        or draft.state != "applied"
        or link.package_digest != revision.package_digest
        or link.method_id != method.id
    ):
        raise HTTPException(409, "Protocol method provenance integrity check failed")
    return [
        {
            "method_publication_id": str(method.id),
            "title": method.title,
            "draft_id": str(draft.id),
            "draft_revision": revision.revision,
            "protocol_version_id": str(version.id),
            "protocol_version": version.version,
            "package_digest": revision.package_digest,
        }
    ]
