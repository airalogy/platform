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
from sqlalchemy import Text, and_, cast, exists, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import IntegrityError

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
from app.models.research_asset import KnowledgeEvidenceLink
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.knowledge import (
    ScopeContext,
    assert_research_file_upload_quota,
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
from app.services.knowledge_drafts import (
    AiraKnowledgeGeneration,
    create_knowledge_generation,
    generate_knowledge_draft,
    sign_knowledge_generation_receipt,
    verify_knowledge_generation_receipt,
)
from app.services.literature_provider import get_literature_provider
from app.services.model_usage import create_usage_context

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


class KnowledgeDraftParams(ScopeParams):
    kind: KnowledgeKind
    title: str = Field(min_length=1, max_length=512)
    body: str = Field(default="", max_length=2_000_000)
    tags: list[str] = Field(default_factory=list, max_length=100)
    paper_library_entry_ids: list[UUID] = Field(default_factory=list, max_length=100)
    research_file_ids: list[UUID] = Field(default_factory=list, max_length=100)
    aira_generation: AiraKnowledgeGeneration | None = None
    aira_receipt: str | None = Field(default=None, min_length=1, max_length=8_000)

    @model_validator(mode="after")
    def validate_aira_provenance(self):
        if bool(self.aira_generation) != bool(self.aira_receipt):
            raise ValueError(
                "Aira Knowledge generation and receipt must be supplied together"
            )
        return self


class KnowledgeCreateParams(KnowledgeDraftParams):
    preview_digest: str | None = Field(default=None, min_length=64, max_length=64)


class AiraPaperKnowledgeDraftParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(default="", max_length=4_000)
    confirm_restricted_processing: bool = False


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


def _require_restricted_ai_confirmation(
    restricted_source: bool,
    *,
    confirmed: bool,
) -> None:
    if restricted_source and not confirmed:
        raise HTTPException(
            status_code=422,
            detail=(
                "Confirm that processing this Restricted Paper source with the "
                "configured AI provider is permitted by the applicable research data policy"
            ),
        )


def _has_restricted_source(
    entry_visibility: str,
    source_files: list[dict[str, Any]],
) -> bool:
    return (
        entry_visibility == Visibility.RESTRICTED.value
        or any(
            source_file.get("visibility") == Visibility.RESTRICTED.value
            for source_file in source_files
        )
    )


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


async def _draft_response(
    db_session: DBSession, draft: PaperImportDraft
) -> dict[str, Any]:
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

    await assert_research_file_upload_quota(db_session, current_user.id, len(data))
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
        return await _entry_payload(db_session, current_user, entry)
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
    return await _entry_payload(db_session, current_user, entry)


async def _entry_payload(
    db_session: DBSession,
    current_user: User,
    entry: PaperLibraryEntry,
    *,
    include_relations: bool = True,
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
        authorized_files = []
        for link, research_file, blob in file_rows:
            try:
                await authorize_research_file(
                    db_session,
                    current_user,
                    research_file,
                )
            except HTTPException as error:
                if error.status_code in {403, 404}:
                    continue
                raise
            authorized_files.append(
                {
                    "id": research_file.id,
                    "filename": research_file.filename,
                    "content_type": blob.content_type,
                    "size_bytes": blob.size_bytes,
                    "relationship_type": link.relationship_type,
                    "visibility": research_file.visibility,
                }
            )
        payload["files"] = authorized_files
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


async def _research_file_search_access(
    db_session: DBSession,
    current_user: User,
    scope: ScopeContext,
):
    """Mirror object authorization inside full-text Paper search.

    A visible Paper entry must not become a side channel for a linked
    Restricted file. Uploaders and Lab Owners can read the object directly;
    other readers need both the scoped capability and an explicit active
    object grant, matching ``authorize_research_file``.
    """

    restricted_access = [
        ResearchFile.visibility != Visibility.RESTRICTED.value,
        ResearchFile.uploaded_by_user_id == current_user.id,
    ]
    if scope.lab_id is not None:
        membership = await LabUser.find_by(
            db_session,
            [
                LabUser.lab_id == scope.lab_id,
                LabUser.user_id == current_user.id,
            ],
        )
        if membership is not None and membership.role == LabRole.OWNER:
            restricted_access.append(ResearchFile.lab_id == scope.lab_id)
        else:
            try:
                await resolve_scope(
                    db_session,
                    current_user,
                    scope_type=scope.scope_type,
                    lab_id=scope.lab_id,
                    project_id=scope.project_id,
                    capability="knowledge.restricted.read",
                )
            except HTTPException as error:
                if error.status_code != 403:
                    raise
            else:
                restricted_access.append(
                    exists(
                        select(KnowledgeAccessGrant.id).where(
                            KnowledgeAccessGrant.resource_type == "research_file",
                            KnowledgeAccessGrant.resource_id == ResearchFile.id,
                            KnowledgeAccessGrant.user_id == current_user.id,
                            KnowledgeAccessGrant.permission == "read",
                            KnowledgeAccessGrant.revoked_at.is_(None),
                        )
                    )
                )
    return and_(
        *scope_conditions(ResearchFile, scope),
        or_(*restricted_access),
    )


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
        file_access = await _research_file_search_access(
            db_session,
            current_user,
            scope,
        )
        full_text_match = exists(
            select(PaperFileLink.id)
            .join(ResearchFile, ResearchFile.id == PaperFileLink.research_file_id)
            .join(ResearchFileBlob, ResearchFileBlob.id == ResearchFile.blob_id)
            .where(
                PaperFileLink.library_entry_id == PaperLibraryEntry.id,
                ResearchFile.archived_at.is_(None),
                file_access,
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
    return await _entry_payload(db_session, current_user, entry)


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
    return await _entry_payload(db_session, current_user, entry)


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
        raise HTTPException(
            status_code=422, detail="Paper and Collection must share a scope"
        )
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
    evidence_links = list(
        (
            await db_session.scalars(
                select(KnowledgeEvidenceLink)
                .where(KnowledgeEvidenceLink.knowledge_item_id == item.id)
                .order_by(
                    KnowledgeEvidenceLink.knowledge_revision,
                    KnowledgeEvidenceLink.created_at,
                )
            )
        ).all()
    )
    return item.as_dict(
        paper_library_entry_ids=paper_ids,
        research_file_ids=file_ids,
        evidence_sources=[
            {
                "knowledge_revision": link.knowledge_revision,
                "evidence_id": link.evidence_id,
                "source_snapshot": link.source_snapshot,
            }
            for link in evidence_links
        ],
    )


async def _validate_knowledge_links(
    db_session: DBSession,
    current_user: User,
    scope: ScopeContext,
    paper_ids: list[UUID],
    file_ids: list[UUID],
    *,
    target_visibility: Visibility,
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
    _require_restricted_source_visibility(
        [item.visibility for item in [*papers, *files]],
        target_visibility=target_visibility,
    )


def _require_restricted_source_visibility(
    source_visibilities: list[str],
    *,
    target_visibility: Visibility,
) -> None:
    if (
        target_visibility != Visibility.RESTRICTED
        and Visibility.RESTRICTED.value in source_visibilities
    ):
        raise HTTPException(
            status_code=422,
            detail="Knowledge linked to a Restricted source must remain Restricted",
        )


def _bounded_full_text(text: str, limit: int = 60_000) -> tuple[str, bool]:
    normalized = text.strip()
    if limit <= 0:
        return "", bool(normalized)
    if len(normalized) <= limit:
        return normalized, False
    marker = "\n\n[... full text truncated ...]\n\n"
    if limit <= len(marker):
        return normalized[:limit], True
    content_limit = limit - len(marker)
    head = int(content_limit * 0.75)
    tail = content_limit - head
    return (
        f"{normalized[:head]}{marker}{normalized[-tail:]}",
        True,
    )


def _bounded_context_text(text: str, limit: int) -> tuple[str, bool]:
    normalized = text.strip()
    if len(normalized) <= limit:
        return normalized, False
    return normalized[:limit], True


def _bounded_context_json(value: Any, limit: int = 10_000) -> Any:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    if len(encoded) <= limit:
        return value
    return {
        "truncated": True,
        "digest": canonical_digest(value),
        "preview": encoded[:limit],
    }


async def _paper_knowledge_context(
    db_session: DBSession,
    current_user: User,
    entry_id: UUID,
    *,
    with_for_update: bool = False,
) -> tuple[PaperLibraryEntry, ScopeContext, dict[str, Any], dict[str, Any]]:
    entry = await db_session.get(
        PaperLibraryEntry,
        entry_id,
        with_for_update=with_for_update,
    )
    if entry is None or entry.archived_at is not None:
        raise HTTPException(status_code=404, detail="Paper not found")
    scope = await authorize_library_entry(
        db_session,
        current_user,
        entry,
        "knowledge.create",
    )
    paper = await db_session.get(
        Paper,
        entry.paper_id,
        with_for_update=with_for_update,
    )
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")

    file_statement = (
        select(PaperFileLink, ResearchFile, ResearchFileBlob)
        .join(
            ResearchFile,
            ResearchFile.id == PaperFileLink.research_file_id,
        )
        .join(ResearchFileBlob, ResearchFileBlob.id == ResearchFile.blob_id)
        .where(
            PaperFileLink.library_entry_id == entry.id,
            ResearchFile.archived_at.is_(None),
        )
        .order_by(PaperFileLink.id)
    )
    if with_for_update:
        file_statement = file_statement.with_for_update()
    file_rows = (await db_session.execute(file_statement)).all()
    full_text_sources: list[dict[str, Any]] = []
    source_files: list[dict[str, Any]] = []
    remaining_full_text = 40_000
    for link, research_file, blob in file_rows:
        try:
            await authorize_research_file(db_session, current_user, research_file)
        except HTTPException as error:
            if error.status_code in {403, 404}:
                continue
            raise
        extracted_text, truncated = _bounded_full_text(
            blob.extracted_text,
            remaining_full_text,
        )
        remaining_full_text -= len(extracted_text)
        source_files.append(
            {
                "research_file_id": str(research_file.id),
                "relationship_type": link.relationship_type,
                "visibility": research_file.visibility,
                "checksum_sha256": blob.checksum_sha256,
                "extracted_text_digest": canonical_digest(blob.extracted_text),
            }
        )
        if extracted_text:
            full_text_sources.append(
                {
                    "research_file_id": str(research_file.id),
                    "relationship_type": link.relationship_type,
                    "excerpt": extracted_text,
                    "truncated": truncated,
                }
            )

    paper_source = {
        "id": str(paper.id),
        "doi": paper.doi,
        "title": paper.title,
        "abstract": paper.abstract,
        "publication_year": paper.publication_year,
        "authors": paper.authors,
        "venue": paper.venue,
        "identifiers": paper.identifiers,
        "metadata_source": paper.metadata_source,
        "updated_at": paper.updated_at.isoformat(),
    }
    entry_source = {
        "library_entry_id": str(entry.id),
        "scope": scope_payload(scope),
        "visibility": entry.visibility,
        "tags": entry.tags,
        "notes": entry.notes,
        "updated_at": entry.updated_at.isoformat(),
    }
    abstract, abstract_truncated = _bounded_context_text(paper.abstract, 20_000)
    notes, notes_truncated = _bounded_context_text(entry.notes, 5_000)
    paper_context = {
        **paper_source,
        "title": _bounded_context_text(paper.title, 2_000)[0],
        "abstract": abstract,
        "abstract_truncated": abstract_truncated,
        "authors": _bounded_context_json(paper.authors),
        "identifiers": _bounded_context_json(paper.identifiers),
    }
    entry_context = {
        **entry_source,
        "tags": _bounded_context_json(entry.tags),
        "notes": notes,
        "notes_truncated": notes_truncated,
    }
    source_snapshot = {
        "library_entry_id": str(entry.id),
        "entry_digest": canonical_digest(entry_source),
        "paper_digest": canonical_digest(paper_source),
        "files": source_files,
    }
    ai_context = {
        "entry": entry_context,
        "paper": paper_context,
        "authorized_full_text": full_text_sources,
        "source_snapshot": source_snapshot,
    }
    return entry, scope, ai_context, source_snapshot


async def _verified_knowledge_generation(
    db_session: DBSession,
    current_user: User,
    params: KnowledgeDraftParams,
    *,
    with_for_update: bool = False,
) -> AiraKnowledgeGeneration | None:
    generation = params.aira_generation
    if generation is None or params.aira_receipt is None:
        return None
    try:
        entry_id = UUID(str(generation.source_snapshot["library_entry_id"]))
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=422,
            detail="Aira Knowledge source is invalid",
        ) from error
    if (
        len(params.paper_library_entry_ids) != 1
        or params.paper_library_entry_ids[0] != entry_id
    ):
        raise HTTPException(
            status_code=422,
            detail="Aira Knowledge must retain its exact source Paper",
        )
    source_entry, scope, ai_context, source_snapshot = await _paper_knowledge_context(
        db_session,
        current_user,
        entry_id,
        with_for_update=with_for_update,
    )
    if scope.model_values() != {
        "scope_type": params.scope_type.value,
        "owner_user_id": (
            current_user.id if params.scope_type == OwnerScope.PERSONAL else None
        ),
        "lab_id": params.lab_id,
        "project_id": params.project_id,
    }:
        raise HTTPException(
            status_code=422,
            detail="Aira Knowledge must be saved in its source Paper scope",
        )
    context_digest = canonical_digest(ai_context)
    if (
        context_digest != generation.context_digest
        or canonical_digest(source_snapshot)
        != canonical_digest(generation.source_snapshot)
    ):
        raise HTTPException(
            status_code=409,
            detail="Paper context changed while the Aira Knowledge draft was reviewed",
        )
    _require_restricted_source_visibility(
        [
            source_entry.visibility,
            *(source_file["visibility"] for source_file in source_snapshot["files"]),
        ],
        target_visibility=params.visibility,
    )
    try:
        verify_knowledge_generation_receipt(
            params.aira_receipt,
            generation,
            user_id=current_user.id,
            library_entry_id=entry_id,
            context_digest=context_digest,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return generation


def _knowledge_create_command(
    params: KnowledgeDraftParams,
    *,
    generated_by: str,
) -> dict[str, Any]:
    return {
        "scope_type": params.scope_type.value,
        "lab_id": str(params.lab_id) if params.lab_id else None,
        "project_id": str(params.project_id) if params.project_id else None,
        "visibility": params.visibility.value,
        "kind": params.kind.value,
        "title": params.title.strip(),
        "body": params.body.strip(),
        "tags": _normalize_tags(params.tags),
        "paper_library_entry_ids": sorted(
            str(value) for value in set(params.paper_library_entry_ids)
        ),
        "research_file_ids": sorted(
            str(value) for value in set(params.research_file_ids)
        ),
        "generated_by": generated_by,
        "generation_id": (
            str(params.aira_generation.id) if params.aira_generation else None
        ),
    }


def _initial_knowledge_state(
    params: KnowledgeDraftParams,
    generation: AiraKnowledgeGeneration | None,
) -> str:
    if generation is not None and params.scope_type != OwnerScope.PERSONAL:
        return KnowledgeState.SUGGESTED.value
    return KnowledgeState.DRAFT.value


@router.post("/papers/{entry_id}/knowledge-draft-with-aira")
async def draft_paper_knowledge_with_aira(
    entry_id: UUID,
    params: AiraPaperKnowledgeDraftParams,
    request: Request,
    db_session: DBSession,
    current_user: CurrentUser,
):
    if not config.effective_ai_enabled:
        raise HTTPException(
            status_code=409,
            detail=(
                "Aira is unavailable. Create Knowledge from this Paper manually "
                "with the deterministic editor."
            ),
        )
    entry, _, ai_context, source_snapshot = await _paper_knowledge_context(
        db_session,
        current_user,
        entry_id,
    )
    restricted_source = _has_restricted_source(
        entry.visibility,
        source_snapshot["files"],
    )
    _require_restricted_ai_confirmation(
        restricted_source,
        confirmed=params.confirm_restricted_processing,
    )
    context_digest = canonical_digest(ai_context)
    model_name = config.CHAT_MODEL_ACCURATE
    usage_context = create_usage_context(
        feature="knowledge.paper.draft",
        user_id=current_user.id,
        lab_id=entry.lab_id,
        project_id=entry.project_id,
        attributes={
            "library_entry_id": str(entry.id),
            "scope_type": entry.scope_type,
        },
    )
    for source_file in source_snapshot["files"]:
        db_session.add(
            ResearchFileAccessAudit(
                research_file_id=UUID(source_file["research_file_id"]),
                lab_id=entry.lab_id,
                actor_user_id=current_user.id,
                action="aira_draft",
                request_id=getattr(request.state, "request_id", None),
                client_ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent", "")[:512],
                outcome="authorized",
            )
        )
    # Never keep an authorization transaction open across model latency.
    await db_session.commit()
    output = await generate_knowledge_draft(
        paper_context=ai_context,
        instruction=params.instruction.strip(),
        model_name=model_name,
        usage_context=usage_context,
    )
    db_session.expire_all()
    current_entry, _, current_context, current_source_snapshot = (
        await _paper_knowledge_context(db_session, current_user, entry_id)
    )
    if canonical_digest(current_context) != context_digest:
        raise HTTPException(
            status_code=409,
            detail="Paper context changed while Aira prepared the Knowledge draft",
        )
    generation = create_knowledge_generation(
        output=output,
        model_name=model_name,
        context_digest=context_digest,
        instruction=params.instruction.strip(),
        source_snapshot=current_source_snapshot,
    )
    receipt = sign_knowledge_generation_receipt(
        generation,
        user_id=current_user.id,
        library_entry_id=current_entry.id,
    )
    await db_session.commit()
    return {
        "draft": {
            "title": output.title,
            "kind": output.kind,
            "body": output.body,
            "tags": output.tags,
        },
        "rationale": output.rationale,
        "assumptions": output.assumptions,
        "warnings": output.warnings,
        "source": current_source_snapshot,
        "aira_generation": generation.model_dump(mode="json"),
        "aira_receipt": receipt,
    }


@router.post("/items/preview")
async def preview_knowledge_item(
    params: KnowledgeDraftParams,
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
        target_visibility=params.visibility,
    )
    generation = await _verified_knowledge_generation(
        db_session,
        current_user,
        params,
    )
    command = _knowledge_create_command(
        params,
        generated_by="aira_assisted" if generation else "human",
    )
    initial_state = _initial_knowledge_state(params, generation)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "effect": {
            "state": initial_state,
            "generated_by": "aira_assisted" if generation else "human",
            "requires_human_review": True,
        },
    }


@router.post("/items")
async def create_knowledge_item(
    params: KnowledgeCreateParams,
    db_session: DBSession,
    current_user: CurrentUser,
):
    draft = KnowledgeDraftParams.model_validate(
        params.model_dump(exclude={"preview_digest"})
    )
    scope = await resolve_scope(
        db_session,
        current_user,
        scope_type=draft.scope_type,
        lab_id=draft.lab_id,
        project_id=draft.project_id,
        capability="knowledge.create",
    )
    validate_visibility(scope, draft.visibility)
    await _validate_knowledge_links(
        db_session,
        current_user,
        scope,
        draft.paper_library_entry_ids,
        draft.research_file_ids,
        target_visibility=draft.visibility,
    )
    generation = await _verified_knowledge_generation(
        db_session,
        current_user,
        draft,
        with_for_update=True,
    )
    generated_by = "aira_assisted" if generation else "human"
    command = _knowledge_create_command(draft, generated_by=generated_by)
    if generation and params.preview_digest is None:
        raise HTTPException(
            status_code=422,
            detail="Preview the Aira Knowledge draft before creating it",
        )
    if (
        params.preview_digest is not None
        and canonical_digest(command) != params.preview_digest
    ):
        raise HTTPException(status_code=409, detail="Knowledge preview has changed")
    if generation is not None and await db_session.scalar(
        select(KnowledgeItem.id).where(
            KnowledgeItem.generation_id == generation.id
        )
    ):
        raise HTTPException(
            status_code=409,
            detail="This Aira Knowledge generation has already been used",
        )
    generation_snapshot = (
        generation.model_dump(mode="json") if generation is not None else None
    )
    initial_state = _initial_knowledge_state(draft, generation)
    item = KnowledgeItem(
        **scope.model_values(),
        visibility=draft.visibility.value,
        kind=draft.kind.value,
        state=initial_state,
        title=draft.title.strip(),
        body=draft.body.strip(),
        tags=_normalize_tags(draft.tags),
        generated_by=generated_by,
        generation_id=generation.id if generation else None,
        generation_model=generation.model if generation else None,
        generation_snapshot=generation_snapshot,
        generation_receipt_digest=(
            hashlib.sha256(params.aira_receipt.encode()).hexdigest()
            if generation is not None and params.aira_receipt is not None
            else None
        ),
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
    for entry_id in set(draft.paper_library_entry_ids):
        db_session.add(
            KnowledgePaperLink(knowledge_item_id=item.id, library_entry_id=entry_id)
        )
    for file_id in set(draft.research_file_ids):
        db_session.add(
            KnowledgeFileLink(knowledge_item_id=item.id, research_file_id=file_id)
        )
    try:
        await db_session.commit()
    except IntegrityError as error:
        await db_session.rollback()
        if generation is not None and "uq_knowledge_items_generation_id" in str(
            error.orig
        ):
            raise HTTPException(
                status_code=409,
                detail="This Aira Knowledge generation has already been used",
            ) from error
        raise
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
        # Publishing is a new, human-confirmed scoped asset. Its derived_from
        # lineage retains access to the source asset's Aira provenance without
        # reusing a single-use generation receipt in a wider scope.
        generated_by="human",
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
