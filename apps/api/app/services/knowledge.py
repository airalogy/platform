"""Deterministic Knowledge import, scope authorization, and file security."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.models.knowledge import (
    KnowledgeAccessGrant,
    KnowledgeItem,
    OwnerScope,
    PaperImportDraft,
    PaperLibraryEntry,
    ResearchFile,
    ResearchFileBlob,
    Visibility,
)
from app.models.lab import LabRole, LabUser
from app.models.project import Project
from app.models.user import User
from app.services.access_control import (
    ROLE_CAPABILITIES,
    resolve_resource_access,
    resolve_structured_access,
)

DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
DOI_URL_PREFIX = re.compile(r"^https?://(?:dx\.)?doi\.org/", re.IGNORECASE)
DOI_LABEL_PREFIX = re.compile(r"^doi:\s*", re.IGNORECASE)
WHITESPACE = re.compile(r"\s+")
logger = logging.getLogger("app")


async def assert_research_file_upload_quota(
    db_session: AsyncSession,
    user_id: UUID,
    incoming_size: int,
    *,
    incoming_count: int = 1,
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
    if count + incoming_count > config.KNOWLEDGE_USER_FILE_COUNT_LIMIT:
        raise HTTPException(status_code=413, detail="Research file count quota exceeded")
    if total + incoming_size > config.KNOWLEDGE_USER_STORAGE_QUOTA_BYTES:
        raise HTTPException(
            status_code=413, detail="Research file storage quota exceeded"
        )


@dataclass(frozen=True)
class ScopeContext:
    scope_type: OwnerScope
    owner_user_id: UUID | None
    lab_id: UUID | None
    project_id: UUID | None

    def model_values(self) -> dict[str, Any]:
        return {
            "scope_type": self.scope_type.value,
            "owner_user_id": self.owner_user_id,
            "lab_id": self.lab_id,
            "project_id": self.project_id,
        }


def utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_doi(value: str) -> str:
    """Normalize common DOI forms without guessing a malformed identifier."""

    normalized = unquote(value).strip()
    previous = None
    while previous != normalized:
        previous = normalized
        normalized = DOI_LABEL_PREFIX.sub("", normalized).strip()
        normalized = DOI_URL_PREFIX.sub("", normalized).strip()
    normalized = normalized.rstrip(".,;").lower()
    if normalized and not DOI_PATTERN.fullmatch(normalized):
        raise ValueError("Invalid DOI")
    return normalized


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = "".join(character if character.isalnum() else " " for character in value)
    return WHITESPACE.sub(" ", value).strip()


def paper_fingerprint(title: str, year: int | None, first_author: str) -> str:
    payload = {
        "title": normalize_text(title),
        "year": year,
        "first_author": normalize_text(first_author),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    authors_value = metadata.get("authors", [])
    if isinstance(authors_value, str):
        authors = [
            item.strip()
            for item in re.split(r"\s+and\s+|;", authors_value)
            if item.strip()
        ]
    else:
        authors = [str(item).strip() for item in authors_value if str(item).strip()]
    first_author = str(
        metadata.get("first_author") or (authors[0] if authors else "")
    ).strip()
    year_value = metadata.get("publication_year") or metadata.get("year")
    try:
        publication_year = int(year_value) if year_value else None
    except (TypeError, ValueError) as error:
        raise ValueError("Publication year must be a number") from error
    if publication_year is not None and not 1000 <= publication_year <= 9999:
        raise ValueError("Publication year must contain four digits")
    doi = normalize_doi(str(metadata.get("doi") or "")) or None
    title = WHITESPACE.sub(" ", str(metadata.get("title") or "")).strip()
    if not title:
        raise ValueError("Paper title is required")
    return {
        "doi": doi,
        "title": title,
        "abstract": str(metadata.get("abstract") or "").strip(),
        "publication_year": publication_year,
        "first_author": first_author,
        "authors": authors,
        "venue": str(metadata.get("venue") or metadata.get("journal") or "").strip(),
        "identifiers": dict(metadata.get("identifiers") or {}),
        # Per-import payloads belong to PaperLibraryEntry/ImportDraft. Keeping
        # them off the canonical Paper prevents one private scope from leaking
        # source-specific metadata into another scope that imports the same DOI.
        "metadata_json": {},
        "metadata_source": str(metadata.get("metadata_source") or "manual"),
        "candidate_fingerprint": paper_fingerprint(
            title, publication_year, first_author
        ),
    }


def _parse_bibtex(value: str) -> dict[str, Any]:
    fields: dict[str, str] = {}
    for match in re.finditer(
        r"(?P<key>[A-Za-z][\w-]*)\s*=\s*(?:\{(?P<braced>[^{}]*)\}|\"(?P<quoted>[^\"]*)\")",
        value,
        re.DOTALL,
    ):
        fields[match.group("key").lower()] = WHITESPACE.sub(
            " ", match.group("braced") or match.group("quoted") or ""
        ).strip()
    if not fields:
        raise ValueError("Unable to parse BibTeX")
    return {
        "title": fields.get("title", ""),
        "authors": fields.get("author", ""),
        "publication_year": fields.get("year"),
        "doi": fields.get("doi", ""),
        "abstract": fields.get("abstract", ""),
        "venue": fields.get("journal") or fields.get("booktitle", ""),
        "metadata_source": "bibtex",
    }


def _parse_ris(value: str) -> dict[str, Any]:
    fields: dict[str, list[str]] = {}
    for line in value.splitlines():
        match = re.match(r"^([A-Z0-9]{2})  - (.*)$", line.strip())
        if match:
            fields.setdefault(match.group(1), []).append(match.group(2).strip())
    if not fields:
        raise ValueError("Unable to parse RIS")
    year_match = re.search(r"\d{4}", (fields.get("PY") or fields.get("Y1") or [""])[0])
    return {
        "title": (fields.get("TI") or fields.get("T1") or [""])[0],
        "authors": fields.get("AU") or fields.get("A1") or [],
        "publication_year": year_match.group(0) if year_match else None,
        "doi": (fields.get("DO") or [""])[0],
        "abstract": (fields.get("AB") or [""])[0],
        "venue": (fields.get("JO") or fields.get("JF") or fields.get("T2") or [""])[0],
        "metadata_source": "ris",
    }


def parse_paper_source(
    source_type: str,
    source: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = dict(metadata or {})
    source = source.strip()
    if source_type == "bibtex":
        parsed = _parse_bibtex(source)
        parsed.update(
            {
                key: value
                for key, value in metadata.items()
                if value not in (None, "", [])
            }
        )
    elif source_type == "ris":
        parsed = _parse_ris(source)
        parsed.update(
            {
                key: value
                for key, value in metadata.items()
                if value not in (None, "", [])
            }
        )
    elif source_type == "doi":
        parsed = {**metadata, "doi": normalize_doi(source), "metadata_source": "doi"}
    elif source_type == "url":
        parsed = {**metadata, "metadata_source": "url"}
        parsed.setdefault("metadata_json", {})["source_url"] = source
        host = urlparse(source)
        if host.scheme not in {"http", "https"} or not host.netloc:
            raise ValueError("Paper URL must use HTTP or HTTPS")
        try:
            parsed.setdefault("doi", normalize_doi(source))
        except ValueError:
            pass
    elif source_type in {"manual", "pdf"}:
        parsed = {**metadata, "metadata_source": source_type}
    else:
        raise ValueError("Unsupported paper import source")
    return _clean_metadata(parsed)


def is_pdf(data: bytes) -> bool:
    return len(data) >= 5 and data[:5] == b"%PDF-"


def extract_pdf_text(data: bytes) -> str:
    """Extract searchable text locally; a failed extraction must not block import."""

    def convert() -> str:
        from markitdown import MarkItDown

        with tempfile.NamedTemporaryFile(suffix=".pdf") as temporary:
            temporary.write(data)
            temporary.flush()
            result = MarkItDown().convert(temporary.name)
            return (result.text_content or "").strip()

    try:
        return convert()
    except Exception:  # noqa: BLE001 - extraction failure must not block import
        logger.warning("Unable to extract searchable text from an uploaded PDF")
        return ""


async def extract_pdf_text_async(data: bytes) -> str:
    return await asyncio.to_thread(extract_pdf_text, data)


def scope_conditions(model, scope: ScopeContext):
    if scope.scope_type == OwnerScope.PERSONAL:
        return [
            model.scope_type == OwnerScope.PERSONAL.value,
            model.owner_user_id == scope.owner_user_id,
        ]
    if scope.scope_type == OwnerScope.LAB:
        return [model.scope_type == OwnerScope.LAB.value, model.lab_id == scope.lab_id]
    return [
        model.scope_type == OwnerScope.PROJECT.value,
        model.project_id == scope.project_id,
    ]


async def resolve_scope(
    db_session: AsyncSession,
    user: User,
    *,
    scope_type: OwnerScope,
    lab_id: UUID | None,
    project_id: UUID | None,
    capability: str,
) -> ScopeContext:
    if scope_type == OwnerScope.PERSONAL:
        if lab_id is not None or project_id is not None:
            raise HTTPException(
                status_code=422, detail="Personal scope cannot include Lab or Project"
            )
        return ScopeContext(scope_type, user.id, None, None)

    project = None
    if scope_type == OwnerScope.PROJECT:
        if project_id is None:
            raise HTTPException(
                status_code=422, detail="Project scope requires project_id"
            )
        project = await db_session.get(Project, project_id)
        if project is None or project.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Project not found")
        if lab_id is not None and project.lab_id != lab_id:
            raise HTTPException(
                status_code=422, detail="Project does not belong to this Lab"
            )
        lab_id = project.lab_id
    elif lab_id is None:
        raise HTTPException(status_code=422, detail="Lab scope requires lab_id")

    membership = await LabUser.find_by(
        db_session, [LabUser.lab_id == lab_id, LabUser.user_id == user.id]
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="Knowledge access denied")

    if scope_type == OwnerScope.PROJECT:
        decision = await resolve_structured_access(
            db_session, user.id, lab_id, project, include_legacy=True
        )
    else:
        decision = await resolve_resource_access(db_session, user.id, lab_id)
        if membership.role == LabRole.MEMBER and capability == "knowledge.read":
            return ScopeContext(scope_type, None, lab_id, None)
    if not decision.allows(capability):
        raise HTTPException(status_code=403, detail="Knowledge access denied")
    return ScopeContext(scope_type, None, lab_id, project_id)


def validate_visibility(scope: ScopeContext, visibility: Visibility) -> None:
    allowed = {
        OwnerScope.PERSONAL: {Visibility.PRIVATE, Visibility.RESTRICTED},
        OwnerScope.LAB: {Visibility.LAB, Visibility.RESTRICTED},
        OwnerScope.PROJECT: {Visibility.PROJECT, Visibility.RESTRICTED},
    }[scope.scope_type]
    if visibility not in allowed:
        raise HTTPException(
            status_code=422, detail="Visibility does not match the selected scope"
        )


async def has_restricted_access(
    db_session: AsyncSession,
    user: User,
    *,
    resource_type: str,
    resource_id: UUID,
    lab_id: UUID | None,
    project_id: UUID | None,
    created_by_user_id: UUID,
) -> bool:
    if user.id == created_by_user_id:
        return True
    if lab_id is not None:
        membership = await LabUser.find_by(
            db_session, [LabUser.lab_id == lab_id, LabUser.user_id == user.id]
        )
        if membership is not None and membership.role == LabRole.OWNER:
            return True
    grant = await db_session.scalar(
        select(KnowledgeAccessGrant.id).where(
            KnowledgeAccessGrant.resource_type == resource_type,
            KnowledgeAccessGrant.resource_id == resource_id,
            KnowledgeAccessGrant.user_id == user.id,
            KnowledgeAccessGrant.permission == "read",
            KnowledgeAccessGrant.revoked_at.is_(None),
        )
    )
    if grant is None or lab_id is None:
        return False
    if project_id is not None:
        project = await db_session.get(Project, project_id)
        if project is None:
            return False
        decision = await resolve_structured_access(
            db_session, user.id, lab_id, project, include_legacy=True
        )
    else:
        decision = await resolve_resource_access(db_session, user.id, lab_id)
    return decision.allows("knowledge.restricted.read")


async def authorize_library_entry(
    db_session: AsyncSession,
    user: User,
    entry: PaperLibraryEntry,
    capability: str = "knowledge.read",
) -> ScopeContext:
    scope = await resolve_scope(
        db_session,
        user,
        scope_type=OwnerScope(entry.scope_type),
        lab_id=entry.lab_id,
        project_id=entry.project_id,
        capability=capability,
    )
    if (
        entry.visibility == Visibility.RESTRICTED.value
        and not await has_restricted_access(
            db_session,
            user,
            resource_type="paper_entry",
            resource_id=entry.id,
            lab_id=entry.lab_id,
            project_id=entry.project_id,
            created_by_user_id=entry.imported_by_user_id,
        )
    ):
        raise HTTPException(status_code=404, detail="Paper not found")
    return scope


async def authorize_knowledge_item(
    db_session: AsyncSession,
    user: User,
    item: KnowledgeItem,
    capability: str = "knowledge.read",
) -> ScopeContext:
    scope = await resolve_scope(
        db_session,
        user,
        scope_type=OwnerScope(item.scope_type),
        lab_id=item.lab_id,
        project_id=item.project_id,
        capability=capability,
    )
    if (
        item.visibility == Visibility.RESTRICTED.value
        and not await has_restricted_access(
            db_session,
            user,
            resource_type="knowledge_item",
            resource_id=item.id,
            lab_id=item.lab_id,
            project_id=item.project_id,
            created_by_user_id=item.created_by_user_id,
        )
    ):
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    return scope


async def authorize_research_file(
    db_session: AsyncSession,
    user: User,
    file: ResearchFile,
) -> ScopeContext:
    scope = await resolve_scope(
        db_session,
        user,
        scope_type=OwnerScope(file.scope_type),
        lab_id=file.lab_id,
        project_id=file.project_id,
        capability="knowledge.read",
    )
    if (
        file.visibility == Visibility.RESTRICTED.value
        and not await has_restricted_access(
            db_session,
            user,
            resource_type="research_file",
            resource_id=file.id,
            lab_id=file.lab_id,
            project_id=file.project_id,
            created_by_user_id=file.uploaded_by_user_id,
        )
    ):
        raise HTTPException(status_code=404, detail="File not found")
    return scope


def scope_payload(scope: ScopeContext) -> dict[str, str | None]:
    return {
        "scope_type": scope.scope_type.value,
        "owner_user_id": str(scope.owner_user_id) if scope.owner_user_id else None,
        "lab_id": str(scope.lab_id) if scope.lab_id else None,
        "project_id": str(scope.project_id) if scope.project_id else None,
    }


def import_preview_payload(draft: PaperImportDraft) -> dict[str, Any]:
    return {
        "scope": {
            "scope_type": draft.scope_type,
            "owner_user_id": str(draft.owner_user_id) if draft.owner_user_id else None,
            "lab_id": str(draft.lab_id) if draft.lab_id else None,
            "project_id": str(draft.project_id) if draft.project_id else None,
        },
        "visibility": draft.visibility,
        "source_type": draft.source_type,
        "parsed_paper": draft.parsed_paper,
        "duplicate_candidate_ids": sorted(draft.duplicate_candidate_ids),
        "staged_research_file_id": (
            str(draft.staged_research_file_id)
            if draft.staged_research_file_id
            else None
        ),
    }


def snapshot_knowledge(item: KnowledgeItem) -> dict[str, Any]:
    return {
        "title": item.title,
        "body": item.body,
        "kind": item.kind,
        "state": item.state,
        "tags": item.tags,
        "visibility": item.visibility,
        "revision": item.revision,
    }


def role_has_capability(role_key: str, capability: str) -> bool:
    return capability in ROLE_CAPABILITIES.get(role_key, frozenset())


def safe_download_filename(filename: str) -> str:
    normalized = unicodedata.normalize("NFKC", Path(filename).name)
    normalized = re.sub(r"[\r\n\x00-\x1f\x7f]", "", normalized).strip()
    return normalized or "paper.pdf"
