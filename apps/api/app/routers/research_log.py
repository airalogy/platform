"""Research Log entries and an access-controlled aggregate activity timeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import String, case, cast, func, literal, select, union_all

from app.database import DBSession
from app.models.knowledge import KnowledgeItem
from app.models.lab import Lab, LabRole, LabUser
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.research import ResearchEvent, ResearchTask
from app.models.research_log import (
    ResearchLogEntry,
    ResearchLogEntryKind,
    ResearchLogRevision,
    ResearchLogScope,
)
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.access_control import resolve_structured_access

router = APIRouter(prefix="/research-log", tags=["research-log"])


@dataclass(frozen=True)
class LogScopeContext:
    scope_type: ResearchLogScope
    owner_user_id: UUID | None
    lab: Lab | None
    project: Project | None

    @property
    def lab_id(self) -> UUID | None:
        return self.lab.id if self.lab else None

    @property
    def project_id(self) -> UUID | None:
        return self.project.id if self.project else None

    def model_values(self) -> dict[str, Any]:
        return {
            "scope_type": self.scope_type.value,
            "owner_user_id": self.owner_user_id,
            "lab_id": self.lab_id,
            "project_id": self.project_id,
        }


class LogAssetLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_type: Literal[
        "paper",
        "protocol",
        "record",
        "knowledge",
        "research_task",
        "data_asset",
        "external",
    ]
    asset_id: str = Field(min_length=1, max_length=512)
    version: str = Field(default="", max_length=128)
    label: str = Field(default="", max_length=512)
    url: str = Field(default="", max_length=2_000)


class ResearchLogEntryDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_type: ResearchLogScope
    lab_id: UUID | None = None
    project_id: UUID | None = None
    kind: ResearchLogEntryKind
    title: str = Field(min_length=1, max_length=512)
    body: str = Field(default="", max_length=200_000)
    goal: str = Field(default="", max_length=50_000)
    completed_items: list[str] = Field(default_factory=list, max_length=100)
    evidence: list[str] = Field(default_factory=list, max_length=100)
    risks: list[str] = Field(default_factory=list, max_length=100)
    next_steps: list[str] = Field(default_factory=list, max_length=100)
    asset_links: list[LogAssetLink] = Field(default_factory=list, max_length=100)
    occurred_at: datetime | None = None

    @model_validator(mode="after")
    def normalize(self):
        self.title = self.title.strip()
        self.body = self.body.strip()
        self.goal = self.goal.strip()
        for field_name in ("completed_items", "evidence", "risks", "next_steps"):
            values = getattr(self, field_name)
            setattr(self, field_name, [value.strip() for value in values if value.strip()])
        if not self.title:
            raise ValueError("Log title is required")
        return self


class ResearchLogEntryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    kind: ResearchLogEntryKind | None = None
    title: str | None = Field(default=None, min_length=1, max_length=512)
    body: str | None = Field(default=None, max_length=200_000)
    goal: str | None = Field(default=None, max_length=50_000)
    completed_items: list[str] | None = Field(default=None, max_length=100)
    evidence: list[str] | None = Field(default=None, max_length=100)
    risks: list[str] | None = Field(default=None, max_length=100)
    next_steps: list[str] | None = Field(default=None, max_length=100)
    asset_links: list[LogAssetLink] | None = Field(default=None, max_length=100)
    occurred_at: datetime | None = None
    change_summary: str = Field(min_length=1, max_length=10_000)


async def _scope_context(
    db_session: DBSession,
    current_user: User,
    *,
    scope_type: ResearchLogScope,
    lab_id: UUID | None,
    project_id: UUID | None,
    capability: Literal["log.read", "log.write"],
) -> LogScopeContext:
    if scope_type == ResearchLogScope.PERSONAL:
        if lab_id is not None or project_id is not None:
            raise HTTPException(status_code=422, detail="Personal Log has no Lab or Project")
        return LogScopeContext(scope_type, current_user.id, None, None)

    project = None
    if scope_type == ResearchLogScope.PROJECT:
        if project_id is None:
            raise HTTPException(status_code=422, detail="Project Log requires project_id")
        project = await db_session.get(Project, project_id)
        if project is None or project.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Project not found")
        if lab_id is not None and project.lab_id != lab_id:
            raise HTTPException(status_code=422, detail="Project does not belong to Lab")
        lab_id = project.lab_id
    if lab_id is None:
        raise HTTPException(status_code=422, detail="Lab Log requires lab_id")
    lab = await db_session.get(Lab, lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    membership = await LabUser.find_by(
        db_session, [LabUser.lab_id == lab.id, LabUser.user_id == current_user.id]
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="Research Log access denied")

    if scope_type == ResearchLogScope.LAB and capability == "log.read":
        return LogScopeContext(scope_type, None, lab, None)
    if membership.role <= LabRole.MANAGER:
        return LogScopeContext(scope_type, None, lab, project)
    decision = await resolve_structured_access(
        db_session,
        current_user.id,
        lab.id,
        project,
        include_legacy=True,
    )
    if not decision.allows(capability):
        raise HTTPException(status_code=403, detail="Research Log access denied")
    return LogScopeContext(scope_type, None, lab, project)


def _scope_conditions(model, scope: LogScopeContext):
    if scope.scope_type == ResearchLogScope.PERSONAL:
        return [
            model.scope_type == ResearchLogScope.PERSONAL.value,
            model.owner_user_id == scope.owner_user_id,
        ]
    if scope.scope_type == ResearchLogScope.LAB:
        return [
            model.scope_type == ResearchLogScope.LAB.value,
            model.lab_id == scope.lab_id,
        ]
    return [
        model.scope_type == ResearchLogScope.PROJECT.value,
        model.project_id == scope.project_id,
    ]


def _snapshot(entry: ResearchLogEntry) -> dict[str, Any]:
    return {
        "kind": entry.kind,
        "title": entry.title,
        "body": entry.body,
        "goal": entry.goal,
        "completed_items": entry.completed_items,
        "evidence": entry.evidence,
        "risks": entry.risks,
        "next_steps": entry.next_steps,
        "asset_links": entry.asset_links,
        "occurred_at": entry.occurred_at.isoformat(),
        "revision": entry.revision,
    }


def _user_payload(user: User | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {"id": str(user.id), "username": user.username, "name": user.name}


async def _entry_payload(
    db_session: DBSession,
    entry: ResearchLogEntry,
    current_user: User,
) -> dict[str, Any]:
    author = await db_session.get(User, entry.created_by_user_id)
    return {
        **entry.as_dict(),
        "entry_type": "manual",
        "event_type": f"log.{entry.kind}",
        "immutable": False,
        "author": _user_payload(author),
        "can_edit": entry.created_by_user_id == current_user.id,
    }


@router.post("/entries")
async def create_research_log_entry(
    params: ResearchLogEntryDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    scope = await _scope_context(
        db_session,
        current_user,
        scope_type=params.scope_type,
        lab_id=params.lab_id,
        project_id=params.project_id,
        capability="log.write",
    )
    entry = ResearchLogEntry(
        **scope.model_values(),
        kind=params.kind.value,
        title=params.title,
        body=params.body,
        goal=params.goal,
        completed_items=params.completed_items,
        evidence=params.evidence,
        risks=params.risks,
        next_steps=params.next_steps,
        asset_links=[item.model_dump() for item in params.asset_links],
        created_by_user_id=current_user.id,
        occurred_at=params.occurred_at or datetime.now(UTC),
    )
    db_session.add(entry)
    await db_session.flush()
    db_session.add(
        ResearchLogRevision(
            log_entry_id=entry.id,
            revision=1,
            snapshot=_snapshot(entry),
            change_summary="Created",
            created_by_user_id=current_user.id,
        )
    )
    await db_session.commit()
    return await _entry_payload(db_session, entry, current_user)


async def _entry_context(
    db_session: DBSession,
    current_user: User,
    entry_id: UUID,
    capability: Literal["log.read", "log.write"],
) -> ResearchLogEntry:
    entry = await db_session.get(ResearchLogEntry, entry_id)
    if entry is None or entry.archived_at is not None:
        raise HTTPException(status_code=404, detail="Research Log entry not found")
    await _scope_context(
        db_session,
        current_user,
        scope_type=ResearchLogScope(entry.scope_type),
        lab_id=entry.lab_id,
        project_id=entry.project_id,
        capability=capability,
    )
    return entry


@router.get("/entries/{entry_id}")
async def get_research_log_entry(
    entry_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    entry = await _entry_context(db_session, current_user, entry_id, "log.read")
    return await _entry_payload(db_session, entry, current_user)


@router.patch("/entries/{entry_id}")
async def update_research_log_entry(
    entry_id: UUID,
    params: ResearchLogEntryUpdate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    entry = await _entry_context(db_session, current_user, entry_id, "log.write")
    if entry.created_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the author can revise this Log")
    if entry.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Research Log entry has changed")
    values = params.model_dump(exclude={"expected_revision", "change_summary"})
    for field_name, value in values.items():
        if value is None:
            continue
        if field_name == "kind":
            value = value.value
        elif field_name == "asset_links":
            value = [item.model_dump() for item in value]
        elif isinstance(value, str):
            value = value.strip()
        setattr(entry, field_name, value)
    if not entry.title.strip():
        raise HTTPException(status_code=422, detail="Log title is required")
    entry.revision += 1
    db_session.add(
        ResearchLogRevision(
            log_entry_id=entry.id,
            revision=entry.revision,
            snapshot=_snapshot(entry),
            change_summary=params.change_summary.strip(),
            created_by_user_id=current_user.id,
        )
    )
    await db_session.commit()
    return await _entry_payload(db_session, entry, current_user)


@router.get("/entries/{entry_id}/revisions")
async def list_research_log_revisions(
    entry_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _entry_context(db_session, current_user, entry_id, "log.read")
    revisions = list(
        (
            await db_session.scalars(
                select(ResearchLogRevision)
                .where(ResearchLogRevision.log_entry_id == entry_id)
                .order_by(ResearchLogRevision.revision.desc())
            )
        ).all()
    )
    return {"revisions": [item.as_dict() for item in revisions]}


def _event_selects(scope: LogScopeContext):
    columns = (
        "source_id",
        "source_type",
        "event_type",
        "occurred_at",
        "actor_user_id",
        "source_version",
        "lab_id",
        "project_id",
    )

    manual = select(
        cast(ResearchLogEntry.id, String).label(columns[0]),
        literal("manual").label(columns[1]),
        ResearchLogEntry.kind.label(columns[2]),
        ResearchLogEntry.occurred_at.label(columns[3]),
        ResearchLogEntry.created_by_user_id.label(columns[4]),
        cast(ResearchLogEntry.revision, String).label(columns[5]),
        ResearchLogEntry.lab_id.label(columns[6]),
        ResearchLogEntry.project_id.label(columns[7]),
    ).where(
        ResearchLogEntry.archived_at.is_(None),
        *_scope_conditions(ResearchLogEntry, scope),
    )

    record = (
        select(
            cast(Record.id, String),
            literal("record"),
            case((Record.version > 1, "record.revised"), else_="record.submitted"),
            Record.created_at,
            Record.user_id,
            cast(Record.version, String),
            Project.lab_id,
            Project.id,
        )
        .join(Protocol, Protocol.id == Record.protocol_id)
        .join(Project, Project.id == Protocol.project_id)
        .where(Record.deleted_at.is_(None), Project.deleted_at.is_(None))
    )

    if scope.scope_type == ResearchLogScope.PERSONAL:
        return [manual, record.where(Record.user_id == scope.owner_user_id)]

    scope_condition = (
        Project.id == scope.project_id
        if scope.scope_type == ResearchLogScope.PROJECT
        else Project.lab_id == scope.lab_id
    )
    record = record.where(scope_condition)
    protocol = (
        select(
            cast(ProtocolVersion.id, String),
            literal("protocol"),
            literal("protocol.version_created"),
            ProtocolVersion.created_at,
            Protocol.user_id,
            ProtocolVersion.version,
            Project.lab_id,
            Project.id,
        )
        .join(Protocol, Protocol.id == ProtocolVersion.protocol_id)
        .join(Project, Project.id == Protocol.project_id)
        .where(
            Protocol.deleted_at.is_(None),
            Project.deleted_at.is_(None),
            scope_condition,
        )
    )
    knowledge_scope_condition = (
        KnowledgeItem.project_id == scope.project_id
        if scope.scope_type == ResearchLogScope.PROJECT
        else KnowledgeItem.lab_id == scope.lab_id
    )
    knowledge_created = select(
        cast(KnowledgeItem.id, String),
        literal("knowledge"),
        literal("knowledge.created"),
        KnowledgeItem.created_at,
        KnowledgeItem.created_by_user_id,
        cast(KnowledgeItem.revision, String),
        KnowledgeItem.lab_id,
        KnowledgeItem.project_id,
    ).where(knowledge_scope_condition)
    knowledge_reviewed = select(
        cast(KnowledgeItem.id, String),
        literal("knowledge"),
        literal("knowledge.reviewed"),
        KnowledgeItem.reviewed_at,
        KnowledgeItem.reviewed_by_user_id,
        cast(KnowledgeItem.revision, String),
        KnowledgeItem.lab_id,
        KnowledgeItem.project_id,
    ).where(knowledge_scope_condition, KnowledgeItem.reviewed_at.is_not(None))
    research_scope_condition = (
        ResearchTask.project_id == scope.project_id
        if scope.scope_type == ResearchLogScope.PROJECT
        else ResearchTask.lab_id == scope.lab_id
    )
    research = (
        select(
            cast(ResearchEvent.id, String),
            literal("research"),
            ResearchEvent.kind,
            ResearchEvent.created_at,
            ResearchEvent.actor_user_id,
            literal(""),
            ResearchTask.lab_id,
            ResearchTask.project_id,
        )
        .join(ResearchTask, ResearchTask.id == ResearchEvent.task_id)
        .where(research_scope_condition)
    )
    return [manual, record, protocol, knowledge_created, knowledge_reviewed, research]


async def _system_event_payload(
    db_session: DBSession,
    row: Any,
) -> dict[str, Any] | None:
    actor = await db_session.get(User, row.actor_user_id) if row.actor_user_id else None
    lab = await db_session.get(Lab, row.lab_id) if row.lab_id else None
    project = await db_session.get(Project, row.project_id) if row.project_id else None
    base = {
        "id": f"{row.source_type}:{row.source_id}:{row.source_version}:{row.event_type}",
        "entry_type": "system",
        "event_type": row.event_type,
        "kind": "system",
        "occurred_at": row.occurred_at,
        "author": _user_payload(actor),
        "immutable": True,
        "can_edit": False,
        "lab": (
            {"id": str(lab.id), "uid": lab.uid, "name": lab.name} if lab else None
        ),
        "project": (
            {"id": str(project.id), "uid": project.uid, "name": project.name}
            if project
            else None
        ),
    }
    source_id = UUID(row.source_id)
    if row.source_type == "record":
        record = await db_session.get(Record, (source_id, int(row.source_version)))
        if record is None:
            return None
        protocol = await db_session.get(Protocol, record.protocol_id)
        if protocol is None:
            return None
        return {
            **base,
            "title": protocol.name,
            "summary": f"Record #{record.number} · v{record.version}",
            "asset": {
                "type": "record",
                "id": str(record.id),
                "version": str(record.version),
                "protocol_id": str(protocol.id),
                "protocol_uid": protocol.uid,
                "protocol_version": record.protocol_version,
            },
        }
    if row.source_type == "protocol":
        version = await db_session.get(ProtocolVersion, source_id)
        if version is None:
            return None
        protocol = await db_session.get(Protocol, version.protocol_id)
        if protocol is None:
            return None
        return {
            **base,
            "title": protocol.name,
            "summary": f"Protocol v{version.version}",
            "asset": {
                "type": "protocol",
                "id": str(protocol.id),
                "uid": protocol.uid,
                "version": version.version,
            },
        }
    if row.source_type == "knowledge":
        item = await db_session.get(KnowledgeItem, source_id)
        if item is None:
            return None
        return {
            **base,
            "title": item.title,
            "summary": f"{item.kind} · r{row.source_version}",
            "asset": {
                "type": "knowledge",
                "id": str(item.id),
                "version": row.source_version,
            },
        }
    if row.source_type == "research":
        event = await db_session.get(ResearchEvent, source_id)
        if event is None:
            return None
        task = await db_session.get(ResearchTask, event.task_id)
        if task is None:
            return None
        return {
            **base,
            "title": task.title,
            "summary": event.kind.replace(".", " "),
            "payload": event.payload,
            "asset": {"type": "research_task", "id": str(task.id), "version": ""},
        }
    return None


@router.get("/timeline")
async def get_research_log_timeline(
    current_user: CurrentUser,
    db_session: DBSession,
    scope_type: ResearchLogScope,
    lab_id: UUID | None = None,
    project_id: UUID | None = None,
    source: Literal[
        "all", "manual", "record", "protocol", "knowledge", "research"
    ] = "all",
    actor_user_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    scope = await _scope_context(
        db_session,
        current_user,
        scope_type=scope_type,
        lab_id=lab_id,
        project_id=project_id,
        capability="log.read",
    )
    event_union = union_all(*_event_selects(scope)).subquery("research_log_events")
    conditions = []
    if source != "all":
        conditions.append(event_union.c.source_type == source)
    if actor_user_id is not None:
        conditions.append(event_union.c.actor_user_id == actor_user_id)
    if date_from is not None:
        conditions.append(
            event_union.c.occurred_at >= datetime.combine(date_from, time.min, UTC)
        )
    if date_to is not None:
        conditions.append(
            event_union.c.occurred_at <= datetime.combine(date_to, time.max, UTC)
        )
    total_count = await db_session.scalar(
        select(func.count()).select_from(event_union).where(*conditions)
    )
    rows = list(
        (
            await db_session.execute(
                select(event_union)
                .where(*conditions)
                .order_by(event_union.c.occurred_at.desc(), event_union.c.source_id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        if row.source_type == "manual":
            entry = await db_session.get(ResearchLogEntry, UUID(row.source_id))
            if entry is not None:
                items.append(await _entry_payload(db_session, entry, current_user))
            continue
        payload = await _system_event_payload(db_session, row)
        if payload is not None:
            items.append(payload)
    try:
        await _scope_context(
            db_session,
            current_user,
            scope_type=scope_type,
            lab_id=lab_id,
            project_id=project_id,
            capability="log.write",
        )
        can_write = True
    except HTTPException as error:
        if error.status_code != 403:
            raise
        can_write = False
    return {
        "items": items,
        "total_count": total_count or 0,
        "page": page,
        "page_size": page_size,
        "can_write": can_write,
        "scope": {
            "scope_type": scope.scope_type,
            "owner_user_id": scope.owner_user_id,
            "lab_id": scope.lab_id,
            "project_id": scope.project_id,
        },
    }
