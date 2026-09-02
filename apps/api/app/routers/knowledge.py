"""Private Paper Library, Knowledge, and scoped research-file APIs."""

from __future__ import annotations

import hashlib
import io
import json
import secrets
from datetime import timedelta
from typing import Annotated, Any, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Text, cast, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

from app.config import config
from app.database import DBSession
from app.libs.file_storage import (
    default_storage_backend,
    default_storage_namespace,
    get_file_with_stream,
    upload_file,
)
from app.models.knowledge import (
    ImportDraftStatus,
    KnowledgeAccessGrant,
    KnowledgeFileLink,
    KnowledgeItem,
    KnowledgeKind,
    KnowledgePaperLink,
    KnowledgeRevision,
    KnowledgeState,
    OwnerScope,
    Paper,
    PaperCollection,
    PaperCollectionEntry,
    PaperFileLink,
    PaperImportDraft,
    PaperLibraryEntry,
    PaperProjectLink,
    ResearchFile,
    ResearchFileAccessAudit,
    ResearchFileAccessMode,
    ResearchFileAccessToken,
    ResearchFileBlob,
    Visibility,
)
from app.models.lab import LabRole, LabUser
from app.models.project import Project
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.knowledge import (
    ScopeContext,
    authorize_knowledge_item,
    authorize_library_entry,
    authorize_research_file,
    canonical_digest,
    extract_pdf_text_async,
    import_preview_payload,
    is_pdf,
    parse_paper_source,
    resolve_scope,
    safe_download_filename,
    scope_conditions,
    scope_payload,
    snapshot_knowledge,
    utcnow,
    validate_visibility,
)
from app.services.literature_provider import get_literature_provider

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class ScopeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_type: OwnerScope
    lab_id: UUID | None = None
    project_id: UUID | None = None
    visibility: Visibility


class PaperImportPreviewParams(ScopeParams):
    source_type: Literal["doi", "url", "bibtex", "ris", "manual"]
    source: str = Field(default="", max_length=2_000_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PaperImportConfirmParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview_digest: str = Field(min_length=64, max_length=64)
    duplicate_resolution: Literal["create_new", "use_existing"] = "create_new"
    existing_paper_id: UUID | None = None
    confirm_distinct: bool = False

    @model_validator(mode="after")
    def validate_resolution(self):
        return self


class PaperEntryUpdateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tags: list[str] | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=100_000)


class CollectionCreateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_type: OwnerScope
    lab_id: UUID | None = None
    project_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=10_000)


class CollectionAssignmentParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    library_entry_ids: list[UUID] = Field(default_factory=list, max_length=500)


class KnowledgeCreateParams(ScopeParams):
    kind: KnowledgeKind
    title: str = Field(min_length=1, max_length=512)
    body: str = Field(default="", max_length=2_000_000)
    tags: list[str] = Field(default_factory=list, max_length=100)
    paper_library_entry_ids: list[UUID] = Field(default_factory=list, max_length=100)
    research_file_ids: list[UUID] = Field(default_factory=list, max_length=100)


class KnowledgeUpdateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=512)
    body: str | None = Field(default=None, max_length=2_000_000)
    kind: KnowledgeKind | None = None
    tags: list[str] | None = Field(default=None, max_length=100)
    change_summary: str = Field(default="", max_length=10_000)


class KnowledgeReviewParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    note: str = Field(default="", max_length=10_000)


class KnowledgePublishParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_scope_type: Literal[OwnerScope.PROJECT, OwnerScope.LAB]
    target_lab_id: UUID | None = None
    target_project_id: UUID | None = None


class KnowledgePublishConfirmParams(KnowledgePublishParams):
    expected_revision: int = Field(ge=1)
    preview_digest: str = Field(min_length=64, max_length=64)


class FileTokenParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ResearchFileAccessMode = ResearchFileAccessMode.PREVIEW


class RestrictedGrantParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_type: Literal["paper_entry", "knowledge_item", "research_file"]
    resource_id: UUID
    user_id: UUID
    reason: str = Field(min_length=1, max_length=4_000)


@router.get("/literature/search")
async def search_literature(
    current_user: CurrentUser,
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(default=20, ge=1, le=100),
):
    provider = get_literature_provider()
    if provider is None:
        raise HTTPException(
            status_code=503, detail="No LiteratureProvider is configured"
        )
    try:
        items = await provider.search(q.strip(), limit)
    except Exception as error:
        raise HTTPException(
            status_code=502, detail="LiteratureProvider is unavailable"
        ) from error
    return {"provider": config.LITERATURE_PROVIDER, "items": items}


@router.get("/literature/resolve-doi")
async def resolve_literature_doi(
    current_user: CurrentUser,
    doi: str = Query(min_length=1, max_length=512),
):
    provider = get_literature_provider()
    if provider is None:
        raise HTTPException(
            status_code=503, detail="No LiteratureProvider is configured"
        )
    try:
        item = await provider.resolve_doi(doi)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=502, detail="LiteratureProvider is unavailable"
        ) from error
    if item is None:
        raise HTTPException(
            status_code=404, detail="DOI was not found by the configured provider"
        )
    return {"provider": config.LITERATURE_PROVIDER, "paper": item}


def _normalize_tags(tags: list[str]) -> list[str]:
    return sorted({tag.strip() for tag in tags if tag.strip()}, key=str.casefold)


async def _duplicate_papers(
    db_session: DBSession,
    current_user: User,
    parsed: dict[str, Any],
) -> list[Paper]:
    if parsed["doi"]:
        return list(
            (
                await db_session.scalars(
                    select(Paper).where(Paper.doi == parsed["doi"])
                )
            ).all()
        )
    candidates = list(
        (
            await db_session.scalars(
                select(Paper).where(
                    Paper.candidate_fingerprint == parsed["candidate_fingerprint"]
                )
            )
        ).all()
    )
    visible: list[Paper] = []
    for paper in candidates:
        entries = list(
            (
                await db_session.scalars(
                    select(PaperLibraryEntry).where(
                        PaperLibraryEntry.paper_id == paper.id,
                        PaperLibraryEntry.archived_at.is_(None),
                    )
                )
            ).all()
        )
        for entry in entries:
            try:
                await authorize_library_entry(db_session, current_user, entry)
            except HTTPException:
                continue
            visible.append(paper)
            break
    return visible


async def _create_import_draft(
    db_session: DBSession,
    current_user: User,
    *,
    scope: ScopeContext,
    visibility: Visibility,
    source_type: str,
    source_payload: dict[str, Any],
    parsed: dict[str, Any],
    staged_research_file_id: UUID | None = None,
) -> PaperImportDraft:
    duplicates = await _duplicate_papers(db_session, current_user, parsed)
    draft = PaperImportDraft(
        **scope.model_values(),
        visibility=visibility.value,
        source_type=source_type,
        source_payload=source_payload,
        parsed_paper=parsed,
        duplicate_candidate_ids=sorted(str(item.id) for item in duplicates),
        preview_digest="0" * 64,
        staged_research_file_id=staged_research_file_id,
        created_by_user_id=current_user.id,
        expires_at=utcnow() + timedelta(minutes=30),
    )
    draft.preview_digest = canonical_digest(import_preview_payload(draft))
    db_session.add(draft)
    await db_session.commit()
    return draft


async def _draft_response(db_session: DBSession, draft: PaperImportDraft) -> dict[str, Any]:
    duplicate_ids = draft.duplicate_candidate_ids
    duplicate_kind = "none"
    if duplicate_ids:
        duplicate_kind = (
            "exact_doi" if draft.parsed_paper.get("doi") else "candidate_conflict"
        )
    public_candidate_ids = [] if duplicate_kind == "exact_doi" else duplicate_ids
    candidates: list[dict[str, Any]] = []
    if public_candidate_ids:
        rows = list(
            (
                await db_session.scalars(
                    select(Paper).where(Paper.id.in_(public_candidate_ids))
                )
            ).all()
        )
        candidates = [
            {
                "id": item.id,
                "title": item.title,
                "publication_year": item.publication_year,
                "first_author": item.first_author,
                "doi": item.doi,
            }
            for item in rows
        ]
    return {
        "id": draft.id,
        "status": draft.status,
        "expires_at": draft.expires_at,
        "preview_digest": draft.preview_digest,
        "paper": draft.parsed_paper,
        "duplicate": {
            "kind": duplicate_kind,
            "candidate_ids": public_candidate_ids,
            "candidates": candidates,
        },
        "impact": {
            "destination": scope_payload(
                ScopeContext(
                    OwnerScope(draft.scope_type),
                    draft.owner_user_id,
                    draft.lab_id,
                    draft.project_id,
                )
            ),
            "visibility": draft.visibility,
            "file_id": draft.staged_research_file_id,
            "requires_explicit_duplicate_decision": duplicate_kind
            == "candidate_conflict",
        },
    }


@router.post("/papers/import/preview")
async def preview_paper_import(
    params: PaperImportPreviewParams,
    db_session: DBSession,
    current_user: CurrentUser,
):
    scope = await resolve_scope(
        db_session,
        current_user,
        scope_type=params.scope_type,
        lab_id=params.lab_id,
        project_id=params.project_id,
        capability="knowledge.import",
    )
    validate_visibility(scope, params.visibility)
    metadata = params.metadata
    if params.source_type == "doi" and not str(metadata.get("title") or "").strip():
        provider = get_literature_provider()
        if provider is None:
            raise HTTPException(
                status_code=422,
                detail="DOI import requires metadata when no LiteratureProvider is configured",
            )
        try:
            metadata = await provider.resolve_doi(params.source) or {}
        except Exception as error:
            raise HTTPException(
                status_code=502, detail="LiteratureProvider is unavailable"
            ) from error
        if not metadata:
            raise HTTPException(status_code=404, detail="DOI metadata was not found")
    try:
        parsed = parse_paper_source(params.source_type, params.source, metadata)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    draft = await _create_import_draft(
        db_session,
        current_user,
        scope=scope,
        visibility=params.visibility,
        source_type=params.source_type,
        source_payload={"source": params.source, "metadata": metadata},
        parsed=parsed,
    )
    return await _draft_response(db_session, draft)


async def _assert_upload_quota(
    db_session: DBSession, user_id: UUID, incoming_size: int
) -> None:
    count, total = (
        await db_session.execute(
            select(
                func.count(ResearchFile.id),
                func.coalesce(func.sum(ResearchFileBlob.size_bytes), 0),
            )
            .select_from(ResearchFile)
            .join(ResearchFileBlob, ResearchFileBlob.id == ResearchFile.blob_id)
            .where(
                ResearchFile.uploaded_by_user_id == user_id,
                ResearchFile.archived_at.is_(None),
            )
        )
    ).one()
    if count >= config.KNOWLEDGE_USER_FILE_COUNT_LIMIT:
        raise HTTPException(
            status_code=413, detail="Research file count quota exceeded"
        )
    if total + incoming_size > config.KNOWLEDGE_USER_STORAGE_QUOTA_BYTES:
        raise HTTPException(
            status_code=413, detail="Research file storage quota exceeded"
        )


@router.post("/papers/import/pdf/preview")
async def preview_pdf_import(
    db_session: DBSession,
    current_user: CurrentUser,
    file: Annotated[UploadFile, File()],
    scope_type: Annotated[OwnerScope, Form()],
    visibility: Annotated[Visibility, Form()],
    title: Annotated[str, Form(min_length=1, max_length=512)],
    lab_id: Annotated[UUID | None, Form()] = None,
    project_id: Annotated[UUID | None, Form()] = None,
    doi: Annotated[str, Form(max_length=512)] = "",
    authors_json: Annotated[str, Form(max_length=100_000)] = "[]",
    publication_year: Annotated[int | None, Form(ge=1000, le=9999)] = None,
    abstract: Annotated[str, Form(max_length=500_000)] = "",
    venue: Annotated[str, Form(max_length=512)] = "",
):
    scope = await resolve_scope(
        db_session,
        current_user,
        scope_type=scope_type,
        lab_id=lab_id,
        project_id=project_id,
        capability="knowledge.import",
    )
    validate_visibility(scope, visibility)
    data = await file.read(config.KNOWLEDGE_PDF_MAX_BYTES + 1)
    if not data:
        raise HTTPException(status_code=422, detail="Uploaded PDF is empty")
    if len(data) > config.KNOWLEDGE_PDF_MAX_BYTES:
        raise HTTPException(
            status_code=413, detail="PDF exceeds the configured size limit"
        )
    if file.content_type != "application/pdf" or not is_pdf(data):
        raise HTTPException(status_code=415, detail="Upload must be a valid PDF file")
    try:
        authors = json.loads(authors_json)
        if not isinstance(authors, list):
            raise TypeError
    except (json.JSONDecodeError, TypeError) as error:
        raise HTTPException(
            status_code=422, detail="authors_json must be a JSON array"
        ) from error
    try:
        parsed = parse_paper_source(
            "pdf",
            "",
            {
                "title": title,
                "doi": doi,
                "authors": authors,
                "publication_year": publication_year,
                "abstract": abstract,
                "venue": venue,
            },
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    await _assert_upload_quota(db_session, current_user.id, len(data))
    checksum = hashlib.sha256(data).hexdigest()
    blob = await db_session.scalar(
        select(ResearchFileBlob).where(ResearchFileBlob.checksum_sha256 == checksum)
    )
    if blob is None:
        object_key = f"knowledge/blobs/{checksum[:2]}/{checksum}.pdf"
        extracted_text = await extract_pdf_text_async(data)
        await upload_file(
            object_key,
            io.BytesIO(data),
            content_type="application/pdf",
            length=len(data),
        )
        blob = ResearchFileBlob(
            checksum_sha256=checksum,
            content_type="application/pdf",
            size_bytes=len(data),
            storage_backend=default_storage_backend(),
            storage_namespace=default_storage_namespace(),
            storage_object_key=object_key,
            extracted_text=extracted_text,
        )
        db_session.add(blob)
        await db_session.flush()
    research_file = ResearchFile(
        **scope.model_values(),
        blob_id=blob.id,
        filename=safe_download_filename(file.filename or "paper.pdf"),
        visibility=visibility.value,
        uploaded_by_user_id=current_user.id,
    )
    db_session.add(research_file)
    await db_session.flush()
    draft = await _create_import_draft(
        db_session,
        current_user,
        scope=scope,
        visibility=visibility,
        source_type="pdf",
        source_payload={
            "filename": research_file.filename,
            "checksum_sha256": checksum,
        },
        parsed=parsed,
        staged_research_file_id=research_file.id,
    )
    return await _draft_response(db_session, draft)


async def _paper_from_draft(
    db_session: DBSession,
    draft: PaperImportDraft,
    params: PaperImportConfirmParams,
    candidates: list[Paper],
) -> Paper:
    candidate_ids = {item.id for item in candidates}
    if params.duplicate_resolution == "use_existing":
        if (
            params.existing_paper_id is None
            and draft.parsed_paper.get("doi")
            and candidates
        ):
            return candidates[0]
        if params.existing_paper_id not in candidate_ids:
            raise HTTPException(
                status_code=409,
                detail="Selected Paper is not a current duplicate candidate",
            )
        return next(item for item in candidates if item.id == params.existing_paper_id)
    if candidates:
        if draft.parsed_paper.get("doi"):
            raise HTTPException(
                status_code=409,
                detail="A Paper with this DOI already exists; use it instead",
            )
        if not params.confirm_distinct:
            raise HTTPException(
                status_code=409, detail="Confirm that this no-DOI Paper is distinct"
            )

    values = dict(draft.parsed_paper)
    if values.get("doi"):
        statement = (
            postgresql_insert(Paper)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["doi"])
            .returning(Paper.id)
        )
        paper_id = await db_session.scalar(statement)
        if paper_id is None:
            paper = await db_session.scalar(
                select(Paper).where(Paper.doi == values["doi"])
            )
            if paper is None:
                raise HTTPException(
                    status_code=409, detail="Paper changed during import; preview again"
                )
            return paper
        paper = await db_session.get(Paper, paper_id)
        assert paper is not None
        return paper
    paper = Paper(**values)
    db_session.add(paper)
    await db_session.flush()
    return paper


@router.post("/papers/import/{draft_id}/confirm")
async def confirm_paper_import(
    draft_id: UUID,
    params: PaperImportConfirmParams,
    db_session: DBSession,
    current_user: CurrentUser,
):
    draft = await db_session.get(PaperImportDraft, draft_id, with_for_update=True)
    if draft is None or draft.created_by_user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Import preview not found")
    if (
        draft.status == ImportDraftStatus.CONFIRMED.value
        and draft.result_library_entry_id
    ):
        entry = await db_session.get(PaperLibraryEntry, draft.result_library_entry_id)
        if entry is None:
            raise HTTPException(
                status_code=409, detail="Imported entry is no longer available"
            )
        return await _entry_payload(db_session, entry)
    if draft.status != ImportDraftStatus.PENDING.value or draft.expires_at <= utcnow():
        raise HTTPException(status_code=409, detail="Import preview has expired")
    await resolve_scope(
        db_session,
        current_user,
        scope_type=OwnerScope(draft.scope_type),
        lab_id=draft.lab_id,
        project_id=draft.project_id,
        capability="knowledge.import",
    )
    candidates = await _duplicate_papers(db_session, current_user, draft.parsed_paper)
    current_candidate_ids = sorted(str(item.id) for item in candidates)
    preview = import_preview_payload(draft)
    preview["duplicate_candidate_ids"] = current_candidate_ids
    current_digest = canonical_digest(preview)
    if (
        params.preview_digest != draft.preview_digest
        or current_digest != draft.preview_digest
    ):
        raise HTTPException(
            status_code=409, detail="Import preview is stale; generate a new preview"
        )

    paper = await _paper_from_draft(db_session, draft, params, candidates)
    scope = ScopeContext(
        OwnerScope(draft.scope_type),
        draft.owner_user_id,
        draft.lab_id,
        draft.project_id,
    )
    entry = await db_session.scalar(
        select(PaperLibraryEntry).where(
            PaperLibraryEntry.paper_id == paper.id,
            PaperLibraryEntry.archived_at.is_(None),
            *scope_conditions(PaperLibraryEntry, scope),
        )
    )
    if entry is None:
        entry = PaperLibraryEntry(
            **scope.model_values(),
            paper_id=paper.id,
            visibility=draft.visibility,
            source_type=draft.source_type,
            source_url=draft.source_payload.get("source")
            if draft.source_type == "url"
            else None,
            source_metadata=draft.source_payload,
            imported_by_user_id=current_user.id,
        )
        db_session.add(entry)
        await db_session.flush()
    if draft.staged_research_file_id:
        link_exists = await db_session.scalar(
            select(PaperFileLink.id).where(
                PaperFileLink.library_entry_id == entry.id,
                PaperFileLink.research_file_id == draft.staged_research_file_id,
            )
        )
        if link_exists is None:
            db_session.add(
                PaperFileLink(
                    library_entry_id=entry.id,
                    research_file_id=draft.staged_research_file_id,
                    relationship_type="full_text",
                )
            )
    draft.status = ImportDraftStatus.CONFIRMED.value
    draft.confirmed_at = utcnow()
    draft.result_library_entry_id = entry.id
    await db_session.commit()
    return await _entry_payload(db_session, entry)


async def _entry_payload(
    db_session: DBSession, entry: PaperLibraryEntry, *, include_relations: bool = True
) -> dict[str, Any]:
    paper = await db_session.get(Paper, entry.paper_id)
    assert paper is not None
    payload = {
        "id": entry.id,
        "scope_type": entry.scope_type,
        "owner_user_id": entry.owner_user_id,
        "lab_id": entry.lab_id,
        "project_id": entry.project_id,
        "visibility": entry.visibility,
        "tags": entry.tags,
        "notes": entry.notes,
        "source_type": entry.source_type,
        "source_url": entry.source_url,
        "source_metadata": entry.source_metadata,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
        "paper": paper.as_dict(),
    }
    if include_relations:
        file_rows = (
            await db_session.execute(
                select(PaperFileLink, ResearchFile, ResearchFileBlob)
                .join(ResearchFile, ResearchFile.id == PaperFileLink.research_file_id)
                .join(ResearchFileBlob, ResearchFileBlob.id == ResearchFile.blob_id)
                .where(PaperFileLink.library_entry_id == entry.id)
            )
        ).all()
        payload["files"] = [
            {
                "id": research_file.id,
                "filename": research_file.filename,
                "content_type": blob.content_type,
                "size_bytes": blob.size_bytes,
                "relationship_type": link.relationship_type,
            }
            for link, research_file, blob in file_rows
        ]
        payload["project_ids"] = list(
            (
                await db_session.scalars(
                    select(PaperProjectLink.project_id).where(
                        PaperProjectLink.library_entry_id == entry.id
                    )
                )
            ).all()
        )
        payload["collection_ids"] = list(
            (
                await db_session.scalars(
                    select(PaperCollectionEntry.collection_id).where(
                        PaperCollectionEntry.library_entry_id == entry.id
                    )
                )
            ).all()
        )
    return payload


@router.get("/papers")
async def list_papers(
    db_session: DBSession,
    current_user: CurrentUser,
    scope_type: Annotated[OwnerScope, Query()],
    lab_id: Annotated[UUID | None, Query()] = None,
    project_id: Annotated[UUID | None, Query()] = None,
    q: str = Query(default="", max_length=500),
    tag: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    scope = await resolve_scope(
        db_session,
        current_user,
        scope_type=scope_type,
        lab_id=lab_id,
        project_id=project_id,
        capability="knowledge.read",
    )
    filters = [
        PaperLibraryEntry.archived_at.is_(None),
        *scope_conditions(PaperLibraryEntry, scope),
    ]
    if q.strip():
        pattern = f"%{q.strip()}%"
        full_text_match = exists(
            select(PaperFileLink.id)
            .join(ResearchFile, ResearchFile.id == PaperFileLink.research_file_id)
            .join(ResearchFileBlob, ResearchFileBlob.id == ResearchFile.blob_id)
            .where(
                PaperFileLink.library_entry_id == PaperLibraryEntry.id,
                ResearchFileBlob.extracted_text.ilike(pattern),
            )
        )
        filters.append(
            or_(
                Paper.title.ilike(pattern),
                Paper.abstract.ilike(pattern),
                PaperLibraryEntry.notes.ilike(pattern),
                full_text_match,
            )
        )
    if tag.strip():
        filters.append(cast(PaperLibraryEntry.tags, Text).contains(f'"{tag.strip()}"'))
    rows = (
        await db_session.execute(
            select(PaperLibraryEntry, Paper)
            .join(Paper, Paper.id == PaperLibraryEntry.paper_id)
            .where(*filters)
            .order_by(PaperLibraryEntry.updated_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).all()
    items = []
    for entry, paper in rows:
        try:
            await authorize_library_entry(db_session, current_user, entry)
        except HTTPException:
            continue
        items.append(
            {
                "id": entry.id,
                "scope_type": entry.scope_type,
                "visibility": entry.visibility,
                "tags": entry.tags,
                "notes": entry.notes,
                "created_at": entry.created_at,
                "paper": paper.as_dict(),
            }
        )
    return {"items": items, "page": page, "page_size": page_size}


@router.get("/papers/{entry_id}")
async def get_paper_entry(
    entry_id: UUID, db_session: DBSession, current_user: CurrentUser
):
    entry = await db_session.get(PaperLibraryEntry, entry_id)
    if entry is None or entry.archived_at is not None:
        raise HTTPException(status_code=404, detail="Paper not found")
    await authorize_library_entry(db_session, current_user, entry)
    return await _entry_payload(db_session, entry)


@router.patch("/papers/{entry_id}")
async def update_paper_entry(
    entry_id: UUID,
    params: PaperEntryUpdateParams,
    db_session: DBSession,
    current_user: CurrentUser,
):
    entry = await db_session.get(PaperLibraryEntry, entry_id)
    if entry is None or entry.archived_at is not None:
        raise HTTPException(status_code=404, detail="Paper not found")
    await authorize_library_entry(db_session, current_user, entry, "knowledge.create")
    if params.tags is not None:
        entry.tags = _normalize_tags(params.tags)
    if params.notes is not None:
        entry.notes = params.notes.strip()
    await db_session.commit()
    return await _entry_payload(db_session, entry)


def _bibtex(paper: Paper) -> str:
    citation_key = (
        f"{(paper.first_author or 'paper').split()[-1]}{paper.publication_year or ''}"
    )
    fields = [f"  title = {{{paper.title}}}"]
    if paper.authors:
        fields.append(f"  author = {{{' and '.join(paper.authors)}}}")
    if paper.publication_year:
        fields.append(f"  year = {{{paper.publication_year}}}")
    if paper.venue:
        fields.append(f"  journal = {{{paper.venue}}}")
    if paper.doi:
        fields.append(f"  doi = {{{paper.doi}}}")
    return f"@article{{{citation_key},\n" + ",\n".join(fields) + "\n}\n"


def _ris(paper: Paper) -> str:
    lines = ["TY  - JOUR", f"TI  - {paper.title}"]
    lines.extend(f"AU  - {author}" for author in paper.authors)
    if paper.publication_year:
        lines.append(f"PY  - {paper.publication_year}")
    if paper.venue:
        lines.append(f"JO  - {paper.venue}")
    if paper.doi:
        lines.append(f"DO  - {paper.doi}")
    lines.append("ER  -")
    return "\n".join(lines) + "\n"


@router.get("/papers/{entry_id}/export", response_class=PlainTextResponse)
async def export_paper_entry(
    entry_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    format: Literal["bibtex", "ris"] = Query(default="bibtex"),
):
    entry = await db_session.get(PaperLibraryEntry, entry_id)
    if entry is None or entry.archived_at is not None:
        raise HTTPException(status_code=404, detail="Paper not found")
    await authorize_library_entry(db_session, current_user, entry, "knowledge.export")
    paper = await db_session.get(Paper, entry.paper_id)
    assert paper is not None
    content = _bibtex(paper) if format == "bibtex" else _ris(paper)
    return PlainTextResponse(
        content,
        media_type="application/x-bibtex"
        if format == "bibtex"
        else "application/x-research-info-systems",
        headers={
            "Content-Disposition": f'attachment; filename="paper.{"bib" if format == "bibtex" else "ris"}"'
        },
    )


@router.post("/papers/{entry_id}/projects/{project_id}")
async def link_paper_to_project(
    entry_id: UUID,
    project_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
):
    entry = await db_session.get(PaperLibraryEntry, entry_id)
    if entry is None or entry.archived_at is not None:
        raise HTTPException(status_code=404, detail="Paper not found")
    await authorize_library_entry(db_session, current_user, entry, "knowledge.manage")
    project = await db_session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Project not found")
    await resolve_scope(
        db_session,
        current_user,
        scope_type=OwnerScope.PROJECT,
        lab_id=project.lab_id,
        project_id=project.id,
        capability="knowledge.create",
    )
    if entry.lab_id is not None and entry.lab_id != project.lab_id:
        raise HTTPException(
            status_code=422, detail="Paper and Project must belong to the same Lab"
        )
    link = await db_session.scalar(
        select(PaperProjectLink).where(
            PaperProjectLink.library_entry_id == entry.id,
            PaperProjectLink.project_id == project.id,
        )
    )
    if link is None:
        link = PaperProjectLink(
            library_entry_id=entry.id,
            project_id=project.id,
            created_by_user_id=current_user.id,
        )
        db_session.add(link)
        await db_session.commit()
    return {"library_entry_id": entry.id, "project_id": project.id}


@router.get("/collections")
async def list_collections(
    db_session: DBSession,
    current_user: CurrentUser,
    scope_type: Annotated[OwnerScope, Query()],
    lab_id: Annotated[UUID | None, Query()] = None,
    project_id: Annotated[UUID | None, Query()] = None,
):
    scope = await resolve_scope(
        db_session,
        current_user,
        scope_type=scope_type,
        lab_id=lab_id,
        project_id=project_id,
        capability="knowledge.read",
    )
    items = list(
        (
            await db_session.scalars(
                select(PaperCollection)
                .where(*scope_conditions(PaperCollection, scope))
                .order_by(PaperCollection.name)
            )
        ).all()
    )
    return {"items": [item.as_dict() for item in items]}


@router.post("/collections")
async def create_collection(
    params: CollectionCreateParams,
    db_session: DBSession,
    current_user: CurrentUser,
):
    scope = await resolve_scope(
        db_session,
        current_user,
        scope_type=params.scope_type,
        lab_id=params.lab_id,
        project_id=params.project_id,
        capability="knowledge.manage",
    )
    collection = PaperCollection(
        **scope.model_values(),
        name=params.name.strip(),
        description=params.description.strip(),
        created_by_user_id=current_user.id,
    )
    db_session.add(collection)
    await db_session.commit()
    return collection


@router.put("/collections/{collection_id}/entries")
async def assign_collection_entries(
    collection_id: UUID,
    params: CollectionAssignmentParams,
    db_session: DBSession,
    current_user: CurrentUser,
):
    collection = await db_session.get(PaperCollection, collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    scope = await resolve_scope(
        db_session,
        current_user,
        scope_type=OwnerScope(collection.scope_type),
        lab_id=collection.lab_id,
        project_id=collection.project_id,
        capability="knowledge.manage",
    )
    entries = list(
        (
            await db_session.scalars(
                select(PaperLibraryEntry).where(
                    PaperLibraryEntry.id.in_(params.library_entry_ids),
                    PaperLibraryEntry.archived_at.is_(None),
                    *scope_conditions(PaperLibraryEntry, scope),
                )
            )
        ).all()
    )
    if len(entries) != len(set(params.library_entry_ids)):
        raise HTTPException(
            status_code=422, detail="Every Paper must belong to the Collection scope"
        )
    existing = list(
        (
            await db_session.scalars(
                select(PaperCollectionEntry).where(
                    PaperCollectionEntry.collection_id == collection.id
                )
            )
        ).all()
    )
    desired = set(params.library_entry_ids)
    for item in existing:
        if item.library_entry_id not in desired:
            await db_session.delete(item)
    existing_ids = {item.library_entry_id for item in existing}
    for entry_id in desired - existing_ids:
        db_session.add(
            PaperCollectionEntry(collection_id=collection.id, library_entry_id=entry_id)
        )
    await db_session.commit()
    return {
        "collection_id": collection.id,
        "library_entry_ids": sorted(str(item) for item in desired),
    }


async def _collection_and_entry(
    collection_id: UUID,
    entry_id: UUID,
    db_session: DBSession,
    current_user: User,
) -> tuple[PaperCollection, PaperLibraryEntry]:
    collection = await db_session.get(PaperCollection, collection_id)
    entry = await db_session.get(PaperLibraryEntry, entry_id)
    if collection is None or entry is None or entry.archived_at is not None:
        raise HTTPException(status_code=404, detail="Collection or Paper not found")
    scope = await resolve_scope(
        db_session,
        current_user,
        scope_type=OwnerScope(collection.scope_type),
        lab_id=collection.lab_id,
        project_id=collection.project_id,
        capability="knowledge.manage",
    )
    matches_scope = await db_session.scalar(
        select(PaperLibraryEntry.id).where(
            PaperLibraryEntry.id == entry.id,
            *scope_conditions(PaperLibraryEntry, scope),
        )
    )
    if matches_scope is None:
        raise HTTPException(status_code=422, detail="Paper and Collection must share a scope")
    await authorize_library_entry(db_session, current_user, entry)
    return collection, entry


@router.post("/collections/{collection_id}/entries/{entry_id}")
async def add_collection_entry(
    collection_id: UUID,
    entry_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
):
    collection, entry = await _collection_and_entry(
        collection_id, entry_id, db_session, current_user
    )
    link = await db_session.scalar(
        select(PaperCollectionEntry).where(
            PaperCollectionEntry.collection_id == collection.id,
            PaperCollectionEntry.library_entry_id == entry.id,
        )
    )
    if link is None:
        db_session.add(
            PaperCollectionEntry(
                collection_id=collection.id,
                library_entry_id=entry.id,
            )
        )
        await db_session.commit()
    return {"collection_id": collection.id, "library_entry_id": entry.id}


@router.delete("/collections/{collection_id}/entries/{entry_id}")
async def remove_collection_entry(
    collection_id: UUID,
    entry_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
):
    collection, entry = await _collection_and_entry(
        collection_id, entry_id, db_session, current_user
    )
    link = await db_session.scalar(
        select(PaperCollectionEntry).where(
            PaperCollectionEntry.collection_id == collection.id,
            PaperCollectionEntry.library_entry_id == entry.id,
        )
    )
    if link is not None:
        await db_session.delete(link)
        await db_session.commit()
    return {"collection_id": collection.id, "library_entry_id": entry.id}


async def _knowledge_payload(
    db_session: DBSession, item: KnowledgeItem
) -> dict[str, Any]:
    paper_ids = list(
        (
            await db_session.scalars(
                select(KnowledgePaperLink.library_entry_id).where(
                    KnowledgePaperLink.knowledge_item_id == item.id
                )
            )
        ).all()
    )
    file_ids = list(
        (
            await db_session.scalars(
                select(KnowledgeFileLink.research_file_id).where(
                    KnowledgeFileLink.knowledge_item_id == item.id
                )
            )
        ).all()
    )
    return item.as_dict(
        paper_library_entry_ids=paper_ids,
        research_file_ids=file_ids,
    )


async def _validate_knowledge_links(
    db_session: DBSession,
    current_user: User,
    scope: ScopeContext,
    paper_ids: list[UUID],
    file_ids: list[UUID],
) -> None:
    papers = list(
        (
            await db_session.scalars(
                select(PaperLibraryEntry).where(
                    PaperLibraryEntry.id.in_(paper_ids),
                    PaperLibraryEntry.archived_at.is_(None),
                    *scope_conditions(PaperLibraryEntry, scope),
                )
            )
        ).all()
    )
    files = list(
        (
            await db_session.scalars(
                select(ResearchFile).where(
                    ResearchFile.id.in_(file_ids),
                    ResearchFile.archived_at.is_(None),
                    *scope_conditions(ResearchFile, scope),
                )
            )
        ).all()
    )
    if len(papers) != len(set(paper_ids)) or len(files) != len(set(file_ids)):
        raise HTTPException(
            status_code=422, detail="Knowledge links must belong to the same scope"
        )
    for paper in papers:
        await authorize_library_entry(db_session, current_user, paper)
    for research_file in files:
        await authorize_research_file(db_session, current_user, research_file)


@router.post("/items")
async def create_knowledge_item(
    params: KnowledgeCreateParams,
    db_session: DBSession,
    current_user: CurrentUser,
):
    scope = await resolve_scope(
        db_session,
        current_user,
        scope_type=params.scope_type,
        lab_id=params.lab_id,
        project_id=params.project_id,
        capability="knowledge.create",
    )
    validate_visibility(scope, params.visibility)
    await _validate_knowledge_links(
        db_session,
        current_user,
        scope,
        params.paper_library_entry_ids,
        params.research_file_ids,
    )
    item = KnowledgeItem(
        **scope.model_values(),
        visibility=params.visibility.value,
        kind=params.kind.value,
        state=KnowledgeState.DRAFT.value,
        title=params.title.strip(),
        body=params.body.strip(),
        tags=_normalize_tags(params.tags),
        generated_by="human",
        created_by_user_id=current_user.id,
    )
    db_session.add(item)
    await db_session.flush()
    db_session.add(
        KnowledgeRevision(
            knowledge_item_id=item.id,
            revision=1,
            snapshot=snapshot_knowledge(item),
            change_summary="Created",
            created_by_user_id=current_user.id,
        )
    )
    for entry_id in set(params.paper_library_entry_ids):
        db_session.add(
            KnowledgePaperLink(knowledge_item_id=item.id, library_entry_id=entry_id)
        )
    for file_id in set(params.research_file_ids):
        db_session.add(
            KnowledgeFileLink(knowledge_item_id=item.id, research_file_id=file_id)
        )
    await db_session.commit()
    return await _knowledge_payload(db_session, item)


@router.get("/items")
async def list_knowledge_items(
    db_session: DBSession,
    current_user: CurrentUser,
    scope_type: Annotated[OwnerScope, Query()],
    lab_id: Annotated[UUID | None, Query()] = None,
    project_id: Annotated[UUID | None, Query()] = None,
    q: str = Query(default="", max_length=500),
    kind: Annotated[KnowledgeKind | None, Query()] = None,
    state: Annotated[KnowledgeState | None, Query()] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    scope = await resolve_scope(
        db_session,
        current_user,
        scope_type=scope_type,
        lab_id=lab_id,
        project_id=project_id,
        capability="knowledge.read",
    )
    filters = [*scope_conditions(KnowledgeItem, scope)]
    if q.strip():
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(KnowledgeItem.title.ilike(pattern), KnowledgeItem.body.ilike(pattern))
        )
    if kind:
        filters.append(KnowledgeItem.kind == kind.value)
    if state:
        filters.append(KnowledgeItem.state == state.value)
    items = list(
        (
            await db_session.scalars(
                select(KnowledgeItem)
                .where(*filters)
                .order_by(KnowledgeItem.updated_at.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        ).all()
    )
    visible = []
    for item in items:
        try:
            await authorize_knowledge_item(db_session, current_user, item)
        except HTTPException:
            continue
        visible.append(await _knowledge_payload(db_session, item))
    return {"items": visible, "page": page, "page_size": page_size}


@router.get("/items/{item_id}")
async def get_knowledge_item(
    item_id: UUID, db_session: DBSession, current_user: CurrentUser
):
    item = await db_session.get(KnowledgeItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    await authorize_knowledge_item(db_session, current_user, item)
    return await _knowledge_payload(db_session, item)


@router.patch("/items/{item_id}")
async def update_knowledge_item(
    item_id: UUID,
    params: KnowledgeUpdateParams,
    db_session: DBSession,
    current_user: CurrentUser,
):
    item = await db_session.get(KnowledgeItem, item_id, with_for_update=True)
    if item is None:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    await authorize_knowledge_item(db_session, current_user, item, "knowledge.create")
    if item.revision != params.expected_revision:
        raise HTTPException(
            status_code=409, detail="Knowledge item changed; reload before saving"
        )
    if item.state in {KnowledgeState.ARCHIVED.value, KnowledgeState.SUPERSEDED.value}:
        raise HTTPException(
            status_code=409, detail="Archived or superseded Knowledge is immutable"
        )
    if params.title is not None:
        item.title = params.title.strip()
    if params.body is not None:
        item.body = params.body.strip()
    if params.kind is not None:
        item.kind = params.kind.value
    if params.tags is not None:
        item.tags = _normalize_tags(params.tags)
    item.state = KnowledgeState.DRAFT.value
    item.reviewed_by_user_id = None
    item.reviewed_at = None
    item.revision += 1
    db_session.add(
        KnowledgeRevision(
            knowledge_item_id=item.id,
            revision=item.revision,
            snapshot=snapshot_knowledge(item),
            change_summary=params.change_summary.strip(),
            created_by_user_id=current_user.id,
        )
    )
    await db_session.commit()
    return await _knowledge_payload(db_session, item)


@router.post("/items/{item_id}/review")
async def review_knowledge_item(
    item_id: UUID,
    params: KnowledgeReviewParams,
    db_session: DBSession,
    current_user: CurrentUser,
):
    item = await db_session.get(KnowledgeItem, item_id, with_for_update=True)
    if item is None:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    await authorize_knowledge_item(db_session, current_user, item, "knowledge.review")
    if item.scope_type == OwnerScope.PERSONAL.value:
        raise HTTPException(
            status_code=422,
            detail="Reviewed status is reserved for Project or Lab Knowledge",
        )
    if item.revision != params.expected_revision:
        raise HTTPException(
            status_code=409, detail="Knowledge item changed; reload before reviewing"
        )
    if item.state not in {KnowledgeState.DRAFT.value, KnowledgeState.SUGGESTED.value}:
        raise HTTPException(
            status_code=409, detail="Only draft or suggested Knowledge can be reviewed"
        )
    item.state = KnowledgeState.REVIEWED.value
    item.reviewed_by_user_id = current_user.id
    item.reviewed_at = utcnow()
    item.revision += 1
    db_session.add(
        KnowledgeRevision(
            knowledge_item_id=item.id,
            revision=item.revision,
            snapshot=snapshot_knowledge(item),
            change_summary=params.note.strip() or "Reviewed",
            created_by_user_id=current_user.id,
        )
    )
    await db_session.commit()
    return await _knowledge_payload(db_session, item)


async def _publish_command(
    db_session: DBSession,
    current_user: User,
    item: KnowledgeItem,
    params: KnowledgePublishParams,
) -> tuple[ScopeContext, dict[str, Any]]:
    await authorize_knowledge_item(db_session, current_user, item)
    source_scope = OwnerScope(item.scope_type)
    if (
        source_scope == OwnerScope.PERSONAL
        and params.target_scope_type != OwnerScope.PROJECT
    ):
        raise HTTPException(
            status_code=422, detail="Personal Knowledge can only publish to a Project"
        )
    if (
        source_scope == OwnerScope.PROJECT
        and params.target_scope_type != OwnerScope.LAB
    ):
        raise HTTPException(
            status_code=422, detail="Project Knowledge can only publish to its Lab"
        )
    if source_scope == OwnerScope.LAB:
        raise HTTPException(
            status_code=422, detail="Lab Knowledge is already at the organization scope"
        )
    target = await resolve_scope(
        db_session,
        current_user,
        scope_type=OwnerScope(params.target_scope_type),
        lab_id=params.target_lab_id,
        project_id=params.target_project_id,
        capability="knowledge.publish",
    )
    if source_scope == OwnerScope.PROJECT and target.lab_id != item.lab_id:
        raise HTTPException(
            status_code=422, detail="Project Knowledge can only publish to its own Lab"
        )
    source_papers = list(
        (
            await db_session.scalars(
                select(KnowledgePaperLink.library_entry_id).where(
                    KnowledgePaperLink.knowledge_item_id == item.id
                )
            )
        ).all()
    )
    source_files = list(
        (
            await db_session.scalars(
                select(KnowledgeFileLink.research_file_id).where(
                    KnowledgeFileLink.knowledge_item_id == item.id
                )
            )
        ).all()
    )
    command = {
        "source_item_id": str(item.id),
        "source_revision": item.revision,
        "target": scope_payload(target),
        "paper_metadata_entries_to_publish": sorted(
            str(value) for value in source_papers
        ),
        "private_files_omitted": sorted(str(value) for value in source_files),
        "new_state": KnowledgeState.DRAFT.value,
    }
    return target, command


@router.post("/items/{item_id}/publish/preview")
async def preview_knowledge_publish(
    item_id: UUID,
    params: KnowledgePublishParams,
    db_session: DBSession,
    current_user: CurrentUser,
):
    item = await db_session.get(KnowledgeItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    _, command = await _publish_command(db_session, current_user, item, params)
    return {"preview_digest": canonical_digest(command), "impact": command}


@router.post("/items/{item_id}/publish/confirm")
async def confirm_knowledge_publish(
    item_id: UUID,
    params: KnowledgePublishConfirmParams,
    db_session: DBSession,
    current_user: CurrentUser,
):
    item = await db_session.get(KnowledgeItem, item_id, with_for_update=True)
    if item is None:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    if item.revision != params.expected_revision:
        raise HTTPException(
            status_code=409, detail="Knowledge item changed; preview again"
        )
    target, command = await _publish_command(db_session, current_user, item, params)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="Publish preview is stale")
    existing = await db_session.scalar(
        select(KnowledgeItem.id).where(
            KnowledgeItem.derived_from_id == item.id,
            *scope_conditions(KnowledgeItem, target),
            KnowledgeItem.state != KnowledgeState.ARCHIVED.value,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="This revision is already published to the target scope",
        )
    published = KnowledgeItem(
        **target.model_values(),
        visibility=(
            Visibility.LAB.value
            if target.scope_type == OwnerScope.LAB
            else Visibility.PROJECT.value
        ),
        kind=item.kind,
        state=KnowledgeState.DRAFT.value,
        title=item.title,
        body=item.body,
        tags=item.tags,
        derived_from_id=item.id,
        generated_by=item.generated_by,
        created_by_user_id=current_user.id,
    )
    db_session.add(published)
    await db_session.flush()
    db_session.add(
        KnowledgeRevision(
            knowledge_item_id=published.id,
            revision=1,
            snapshot=snapshot_knowledge(published),
            change_summary=f"Published from {item.id} revision {item.revision}",
            created_by_user_id=current_user.id,
        )
    )
    source_links = list(
        (
            await db_session.scalars(
                select(KnowledgePaperLink).where(
                    KnowledgePaperLink.knowledge_item_id == item.id
                )
            )
        ).all()
    )
    for source_link in source_links:
        source_entry = await db_session.get(
            PaperLibraryEntry, source_link.library_entry_id
        )
        if source_entry is None:
            continue
        target_entry = await db_session.scalar(
            select(PaperLibraryEntry).where(
                PaperLibraryEntry.paper_id == source_entry.paper_id,
                PaperLibraryEntry.archived_at.is_(None),
                *scope_conditions(PaperLibraryEntry, target),
            )
        )
        if target_entry is None:
            target_entry = PaperLibraryEntry(
                **target.model_values(),
                paper_id=source_entry.paper_id,
                visibility=(
                    Visibility.LAB.value
                    if target.scope_type == OwnerScope.LAB
                    else Visibility.PROJECT.value
                ),
                tags=source_entry.tags,
                source_type="published",
                source_metadata={
                    "derived_from_library_entry_id": str(source_entry.id),
                    "files_copied": False,
                },
                imported_by_user_id=current_user.id,
            )
            db_session.add(target_entry)
            await db_session.flush()
        db_session.add(
            KnowledgePaperLink(
                knowledge_item_id=published.id,
                library_entry_id=target_entry.id,
            )
        )
    await db_session.commit()
    return await _knowledge_payload(db_session, published)


@router.post("/files/{file_id}/token")
async def create_file_token(
    file_id: UUID,
    params: FileTokenParams,
    db_session: DBSession,
    current_user: CurrentUser,
):
    research_file = await db_session.get(ResearchFile, file_id)
    if research_file is None or research_file.archived_at is not None:
        raise HTTPException(status_code=404, detail="File not found")
    await authorize_research_file(db_session, current_user, research_file)
    secret = secrets.token_urlsafe(32)
    token = ResearchFileAccessToken(
        token_hash=hashlib.sha256(secret.encode()).hexdigest(),
        research_file_id=research_file.id,
        user_id=current_user.id,
        mode=params.mode.value,
        expires_at=utcnow()
        + timedelta(seconds=config.KNOWLEDGE_PREVIEW_TOKEN_TTL_SECONDS),
    )
    db_session.add(token)
    await db_session.commit()
    return {
        "url": f"/knowledge/files/{research_file.id}/content?token={secret}",
        "mode": params.mode,
        "expires_at": token.expires_at,
    }


@router.get("/files/{file_id}/content")
async def access_research_file(
    file_id: UUID,
    request: Request,
    db_session: DBSession,
    current_user: CurrentUser,
    token: str = Query(min_length=32, max_length=256),
):
    token_row = await db_session.scalar(
        select(ResearchFileAccessToken).where(
            ResearchFileAccessToken.token_hash
            == hashlib.sha256(token.encode()).hexdigest(),
            ResearchFileAccessToken.research_file_id == file_id,
            ResearchFileAccessToken.user_id == current_user.id,
            ResearchFileAccessToken.revoked_at.is_(None),
            ResearchFileAccessToken.expires_at > utcnow(),
        )
    )
    research_file = await db_session.get(ResearchFile, file_id)
    if research_file is None or research_file.archived_at is not None:
        raise HTTPException(status_code=404, detail="File access not found or expired")
    if token_row is None:
        db_session.add(
            ResearchFileAccessAudit(
                research_file_id=file_id,
                lab_id=research_file.lab_id,
                actor_user_id=current_user.id,
                action="access",
                request_id=getattr(request.state, "request_id", None),
                client_ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent", "")[:512],
                outcome="denied",
            )
        )
        await db_session.commit()
        raise HTTPException(status_code=404, detail="File access not found or expired")
    try:
        await authorize_research_file(db_session, current_user, research_file)
    except HTTPException:
        db_session.add(
            ResearchFileAccessAudit(
                research_file_id=file_id,
                lab_id=research_file.lab_id,
                actor_user_id=current_user.id,
                action=token_row.mode,
                request_id=getattr(request.state, "request_id", None),
                client_ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent", "")[:512],
                outcome="denied",
            )
        )
        await db_session.commit()
        raise
    blob = await db_session.get(ResearchFileBlob, research_file.blob_id)
    if blob is None:
        raise HTTPException(status_code=404, detail="File content not found")
    db_session.add(
        ResearchFileAccessAudit(
            research_file_id=file_id,
            lab_id=research_file.lab_id,
            actor_user_id=current_user.id,
            action=token_row.mode,
            request_id=getattr(request.state, "request_id", None),
            client_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent", "")[:512],
            outcome="authorized",
        )
    )
    await db_session.commit()
    disposition = (
        "inline"
        if token_row.mode == ResearchFileAccessMode.PREVIEW.value
        else "attachment"
    )
    filename = safe_download_filename(research_file.filename)
    ascii_filename = (
        filename.encode("ascii", "ignore").decode().replace('"', "_") or "paper.pdf"
    )
    return StreamingResponse(
        get_file_with_stream(blob.storage_object_key, backend=blob.storage_backend),
        media_type=blob.content_type,
        headers={
            "Content-Disposition": (
                f'{disposition}; filename="{ascii_filename}"; '
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )


@router.post("/restricted-access")
async def grant_restricted_access(
    params: RestrictedGrantParams,
    db_session: DBSession,
    current_user: CurrentUser,
):
    resource: PaperLibraryEntry | KnowledgeItem | ResearchFile | None
    if params.resource_type == "paper_entry":
        resource = await db_session.get(PaperLibraryEntry, params.resource_id)
        creator_id = resource.imported_by_user_id if resource else None
    elif params.resource_type == "knowledge_item":
        resource = await db_session.get(KnowledgeItem, params.resource_id)
        creator_id = resource.created_by_user_id if resource else None
    else:
        resource = await db_session.get(ResearchFile, params.resource_id)
        creator_id = resource.uploaded_by_user_id if resource else None
    if resource is None or resource.visibility != Visibility.RESTRICTED.value:
        raise HTTPException(status_code=404, detail="Restricted resource not found")
    lab_id = resource.lab_id
    if creator_id != current_user.id:
        membership = await LabUser.find_by(
            db_session, [LabUser.lab_id == lab_id, LabUser.user_id == current_user.id]
        )
        if membership is None or membership.role != LabRole.OWNER:
            raise HTTPException(
                status_code=403,
                detail="Only the uploader or Lab Owner can grant access",
            )
    target_membership = await LabUser.find_by(
        db_session, [LabUser.lab_id == lab_id, LabUser.user_id == params.user_id]
    )
    if lab_id is not None and target_membership is None:
        raise HTTPException(
            status_code=422, detail="Restricted reader must be a Lab member"
        )
    if lab_id is not None:
        target_user = await db_session.get(User, params.user_id)
        if target_user is None:
            raise HTTPException(status_code=422, detail="Restricted reader not found")
        if resource.project_id is not None:
            target_scope = await resolve_scope(
                db_session,
                target_user,
                scope_type=OwnerScope.PROJECT,
                lab_id=lab_id,
                project_id=resource.project_id,
                capability="knowledge.restricted.read",
            )
        else:
            target_scope = await resolve_scope(
                db_session,
                target_user,
                scope_type=OwnerScope.LAB,
                lab_id=lab_id,
                project_id=None,
                capability="knowledge.restricted.read",
            )
        assert target_scope.lab_id == lab_id
    grant = await db_session.scalar(
        select(KnowledgeAccessGrant).where(
            KnowledgeAccessGrant.resource_type == params.resource_type,
            KnowledgeAccessGrant.resource_id == params.resource_id,
            KnowledgeAccessGrant.user_id == params.user_id,
            KnowledgeAccessGrant.permission == "read",
            KnowledgeAccessGrant.revoked_at.is_(None),
        )
    )
    if grant is None:
        grant = KnowledgeAccessGrant(
            resource_type=params.resource_type,
            resource_id=params.resource_id,
            user_id=params.user_id,
            permission="read",
            reason=params.reason.strip(),
            created_by_user_id=current_user.id,
        )
        db_session.add(grant)
        await db_session.commit()
    return grant
