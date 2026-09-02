"""Knowledge, private paper-library, and scoped research-file models.

Canonical Paper rows intentionally carry no visibility semantics. Access is
always mediated by a scoped PaperLibraryEntry so the existence of a private
paper cannot be inferred through a global Paper endpoint.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.libs.file_storage import default_storage_backend

from .base import Base


class OwnerScope(StrEnum):
    PERSONAL = "personal"
    LAB = "lab"
    PROJECT = "project"


class Visibility(StrEnum):
    PRIVATE = "private"
    LAB = "lab"
    PROJECT = "project"
    RESTRICTED = "restricted"


class KnowledgeKind(StrEnum):
    REFERENCE = "reference"
    NOTE = "note"
    METHOD = "method"
    DECISION = "decision"
    FINDING = "finding"


class KnowledgeState(StrEnum):
    SUGGESTED = "suggested"
    DRAFT = "draft"
    REVIEWED = "reviewed"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class ImportDraftStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ResearchFileAccessMode(StrEnum):
    PREVIEW = "preview"
    DOWNLOAD = "download"


SCOPE_CHECK = (
    "(scope_type = 'personal' AND owner_user_id IS NOT NULL "
    "AND lab_id IS NULL AND project_id IS NULL) OR "
    "(scope_type = 'lab' AND owner_user_id IS NULL "
    "AND lab_id IS NOT NULL AND project_id IS NULL) OR "
    "(scope_type = 'project' AND owner_user_id IS NULL "
    "AND lab_id IS NOT NULL AND project_id IS NOT NULL)"
)


class Paper(Base):
    __tablename__ = "papers"
    __table_args__ = (
        UniqueConstraint("doi", name="uq_papers_doi"),
        Index("ix_papers_fingerprint", "candidate_fingerprint"),
        Index("ix_papers_title_year", "title", "publication_year"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    doi: Mapped[str | None] = mapped_column(String(512), unique=True, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str] = mapped_column(Text, nullable=False, default="")
    publication_year: Mapped[int | None]
    first_author: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    authors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    venue: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    identifiers: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    candidate_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metadata_source: Mapped[str] = mapped_column(
        String(64), nullable=False, default="manual"
    )
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PaperLibraryEntry(Base):
    __tablename__ = "paper_library_entries"
    __table_args__ = (
        CheckConstraint(SCOPE_CHECK, name="ck_paper_library_entries_scope"),
        UniqueConstraint(
            "paper_id",
            "scope_type",
            "owner_user_id",
            "lab_id",
            "project_id",
            name="uq_paper_library_entry_scope",
        ),
        Index("ix_paper_library_entries_personal", "owner_user_id", "archived_at"),
        Index("ix_paper_library_entries_lab", "lab_id", "archived_at"),
        Index("ix_paper_library_entries_project", "project_id", "archived_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    paper_id: Mapped[UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    lab_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    visibility: Mapped[str] = mapped_column(String(16), nullable=False)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048))
    imported_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaperCollection(Base):
    __tablename__ = "paper_collections"
    __table_args__ = (
        CheckConstraint(SCOPE_CHECK, name="ck_paper_collections_scope"),
        Index("ix_paper_collections_owner", "scope_type", "owner_user_id", "lab_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    lab_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PaperCollectionEntry(Base):
    __tablename__ = "paper_collection_entries"
    __table_args__ = (
        UniqueConstraint(
            "collection_id", "library_entry_id", name="uq_paper_collection_entry"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    collection_id: Mapped[UUID] = mapped_column(
        ForeignKey("paper_collections.id", ondelete="CASCADE"), nullable=False
    )
    library_entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("paper_library_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PaperProjectLink(Base):
    __tablename__ = "paper_project_links"
    __table_args__ = (
        UniqueConstraint(
            "library_entry_id", "project_id", name="uq_paper_project_link"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    library_entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("paper_library_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchFileBlob(Base):
    __tablename__ = "research_file_blobs"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    checksum_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_backend: Mapped[str] = mapped_column(
        String(32), nullable=False, default=default_storage_backend
    )
    storage_namespace: Mapped[str | None] = mapped_column(String(256))
    storage_object_key: Mapped[str] = mapped_column(
        String(1024), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchFile(Base):
    __tablename__ = "research_files"
    __table_args__ = (
        CheckConstraint(SCOPE_CHECK, name="ck_research_files_scope"),
        Index("ix_research_files_scope", "scope_type", "owner_user_id", "lab_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    blob_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_file_blobs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    lab_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    visibility: Mapped[str] = mapped_column(String(16), nullable=False)
    uploaded_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaperFileLink(Base):
    __tablename__ = "paper_file_links"
    __table_args__ = (
        UniqueConstraint(
            "library_entry_id", "research_file_id", name="uq_paper_file_link"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    library_entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("paper_library_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    research_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_files.id", ondelete="RESTRICT"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="full_text"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"
    __table_args__ = (
        CheckConstraint(SCOPE_CHECK, name="ck_knowledge_items_scope"),
        Index("ix_knowledge_items_scope_state", "scope_type", "lab_id", "state"),
        Index("ix_knowledge_items_project_state", "project_id", "state"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    lab_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    visibility: Mapped[str] = mapped_column(String(16), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    derived_from_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("knowledge_items.id", ondelete="SET NULL"), index=True
    )
    generated_by: Mapped[str] = mapped_column(
        String(32), nullable=False, default="human"
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("knowledge_items.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class KnowledgeRevision(Base):
    __tablename__ = "knowledge_revisions"
    __table_args__ = (
        UniqueConstraint("knowledge_item_id", "revision", name="uq_knowledge_revision"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    knowledge_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    change_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KnowledgePaperLink(Base):
    __tablename__ = "knowledge_paper_links"
    __table_args__ = (
        UniqueConstraint(
            "knowledge_item_id", "library_entry_id", name="uq_knowledge_paper_link"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    knowledge_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_items.id", ondelete="CASCADE"), nullable=False
    )
    library_entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("paper_library_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class KnowledgeFileLink(Base):
    __tablename__ = "knowledge_file_links"
    __table_args__ = (
        UniqueConstraint(
            "knowledge_item_id", "research_file_id", name="uq_knowledge_file_link"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    knowledge_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_items.id", ondelete="CASCADE"), nullable=False
    )
    research_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_files.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )


class KnowledgeAccessGrant(Base):
    __tablename__ = "knowledge_access_grants"
    __table_args__ = (
        UniqueConstraint(
            "resource_type",
            "resource_id",
            "user_id",
            "permission",
            name="uq_knowledge_access_grant",
        ),
        Index("ix_knowledge_access_grants_user", "user_id", "revoked_at"),
        CheckConstraint(
            "resource_type IN ('paper_entry', 'knowledge_item', 'research_file')",
            name="ck_knowledge_access_grants_resource_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    permission: Mapped[str] = mapped_column(
        String(16), nullable=False, default="read"
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaperImportDraft(Base):
    __tablename__ = "paper_import_drafts"
    __table_args__ = (
        CheckConstraint(SCOPE_CHECK, name="ck_paper_import_drafts_scope"),
        Index("ix_paper_import_drafts_owner_status", "created_by_user_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    lab_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    visibility: Mapped[str] = mapped_column(String(16), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    parsed_paper: Mapped[dict] = mapped_column(JSON, nullable=False)
    duplicate_candidate_ids: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    preview_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ImportDraftStatus.PENDING.value
    )
    staged_research_file_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_files.id", ondelete="SET NULL")
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchFileAccessToken(Base):
    __tablename__ = "research_file_access_tokens"
    __table_args__ = (
        Index("ix_research_file_access_tokens_expiry", "expires_at", "revoked_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    research_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_files.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchFileAccessAudit(Base):
    __tablename__ = "research_file_access_audits"
    __table_args__ = (
        Index("ix_research_file_access_audits_file_created", "research_file_id", "created_at"),
        Index("ix_research_file_access_audits_lab_created", "lab_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    research_file_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    lab_id: Mapped[UUID | None] = mapped_column(index=True)
    actor_user_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64))
    client_ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
