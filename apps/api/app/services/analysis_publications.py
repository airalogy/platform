"""Publish selected real statistics without sharing an owner's private report.

The publication, its Pending Evidence and event are one transaction. Source
authorization is live; publication bytes and their exact source identities are
immutable. No Action, Run, Record, DataAsset or computation is synthesized here.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select, tuple_

from app.config import config
from app.models.analysis import AnalysisInterpretationRevision, AnalysisRun
from app.models.analysis_publication import AnalysisEvidencePublication
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.research import ResearchTask
from app.models.research_asset import ResearchEvidence
from app.services.analysis_engine import ENGINE_VERSION, canonical_digest
from app.services.project_analyses import (
    ProjectInterpretationContent,
    interpretation_digest,
    interpretation_evidence,
)
from app.services.project_analysis_engine import (
    ENGINE_VERSION as PROJECT_ENGINE_VERSION,
)
from app.services.record_analyses import (
    AnalysisSelection,
    authorize_analysis_sources,
    authorize_snapshot,
    capture_sources,
    verify_run_integrity,
)
from app.services.research_runtime import (
    emit_research_event,
    require_research_capability,
)
from app.services.workflow_definitions import request_lock

PUBLICATION_SCHEMA = "airalogy.analysis-evidence-publication.v1"
PREVIEW_AUDIENCE = "airalogy.analysis-evidence-publication-preview"
PREVIEW_TTL = timedelta(minutes=15)
MAX_PUBLICATION_BYTES = 2 * 1024 * 1024


class PublicationSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section_id: str = Field(pattern=r"^(protocol|join|source:[a-z][a-z0-9_]{0,23})$")
    fields: list[str] = Field(min_length=1, max_length=20)

    @field_validator("fields")
    @classmethod
    def exact_fields(cls, values):
        if len(set(values)) != len(values) or any(
            not value.strip() or len(value) > 255 for value in values
        ):
            raise ValueError("Select distinct, nonblank computed fields")
        return sorted(values)


class AnalysisPublicationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: UUID
    title: str = Field(min_length=1, max_length=255)
    summary: str = Field(default="", max_length=8000)
    sections: list[PublicationSection] = Field(min_length=1, max_length=10)
    interpretation_revision_id: UUID | None = None

    @field_validator("title", "summary")
    @classmethod
    def trim_text(cls, value):
        return value.strip()

    @model_validator(mode="after")
    def distinct_sections(self):
        if not self.title:
            raise ValueError("Publication title is required")
        if len({item.section_id for item in self.sections}) != len(self.sections):
            raise ValueError("Select each result section only once")
        self.sections.sort(key=lambda item: item.section_id)
        return self


class AnalysisPublicationConfirm(AnalysisPublicationDraft):
    preview_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    preview_token: str = Field(min_length=1, max_length=8000)
    client_idempotency_key: UUID


def _bounded(value):
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
    except (ValueError, TypeError, RecursionError) as exc:
        raise HTTPException(409, "Analysis publication content is invalid") from exc
    if len(encoded) > MAX_PUBLICATION_BYTES:
        raise HTTPException(
            422, "Selected publication exceeds 2 MiB; select fewer fields"
        )
    return value


def _supported_run(run):
    if run.status != "succeeded" or (
        (run.source_scope, run.engine_version)
        not in {("protocol", ENGINE_VERSION), ("project", PROJECT_ENGINE_VERSION)}
    ):
        raise HTTPException(
            409,
            "Publication requires a completed built-in Protocol or Project analysis",
        )
    verify_run_integrity(run)


def _source_slots(run):
    if run.source_scope == "protocol":
        return [("protocol", run.source_snapshot)]
    return [
        (item["slot_id"], item["snapshot"]) for item in run.source_snapshot["inputs"]
    ]


def _report_catalog(run):
    _supported_run(run)
    if run.source_scope == "protocol":
        return {"protocol": {"label": "Protocol", "report": run.result}}
    result = {
        f"source:{item['slot_id']}": {"label": item["label"], "report": item["report"]}
        for item in run.result["local_results"]
    }
    if run.result.get("join") is not None:
        result["join"] = {
            "label": "Joined statistics",
            "report": run.result["join"]["report"],
        }
    return result


def _field_descriptor(field):
    return {
        key: deepcopy(field[key])
        for key in ("key", "title", "type", "unit")
        if key in field
    }


def _selected_report(report, selected):
    fields = {item["key"]: item for item in report["fields"]}
    if not set(selected) <= set(fields):
        raise HTTPException(422, "Select fields from the actual computed result")
    return {
        "counts": deepcopy(report["counts"]),
        "fields": [_field_descriptor(fields[key]) for key in selected],
        "group_by": [_field_descriptor(item) for item in report["group_by"]],
        "groups": [
            {
                "key": deepcopy(group["key"]),
                "row_count": group["row_count"],
                "fields": {key: deepcopy(group["fields"][key]) for key in selected},
            }
            for group in report["groups"]
        ],
        "warnings": [
            deepcopy(item)
            for item in report.get("warnings", [])
            if "field" not in item or item["field"] in selected
        ],
    }


def _source_manifest(run):
    return [
        {
            "slot_id": slot,
            "protocol_id": source["protocol_id"],
            "source_digest": canonical_digest(source),
            "records": [
                {
                    key: record[key]
                    for key in (
                        "record_id",
                        "record_version",
                        "protocol_version",
                        "record_hash",
                    )
                }
                for record in source["records"]
            ],
            "schemas": [
                {
                    "id": schema["id"],
                    "version": schema["version"],
                    "schema_digest": canonical_digest(
                        {
                            "json_schema": schema["json_schema"],
                            "fields": schema["fields"],
                        }
                    ),
                }
                for schema in source["schemas"]
            ],
        }
        for slot, source in _source_slots(run)
    ]


def build_publication_snapshot(run, draft, interpretation=None):
    """Only server-resolved aggregates; never accept submitted result values."""
    try:
        catalog = _report_catalog(run)
        sections = []
        for selection in draft.sections:
            entry = catalog.get(selection.section_id)
            if entry is None:
                raise HTTPException(422, "Selected result section does not exist")
            sections.append(
                {
                    "section_id": selection.section_id,
                    "label": entry["label"],
                    "report": _selected_report(entry["report"], selection.fields),
                }
            )
        interpreted = None
        if interpretation is not None:
            if (
                run.source_scope != "project"
                or interpretation.id != draft.interpretation_revision_id
                or interpretation.analysis_run_id != run.id
                or interpretation.result_digest != run.result_digest
                or interpretation.content_digest
                != interpretation_digest(interpretation)
            ):
                raise HTTPException(
                    409, "Interpretation revision does not match this result"
                )
            content = ProjectInterpretationContent.model_validate(
                interpretation.content
            )
            resolved = interpretation_evidence(run.result, content)
            if resolved != interpretation.resolved_evidence:
                raise HTTPException(
                    409, "Interpretation evidence integrity check failed"
                )
            selected = {
                (item.section_id, field)
                for item in draft.sections
                for field in item.fields
            }
            if any(
                (f"source:{item.slot_id}", item.field) not in selected
                for item in content.findings
            ):
                raise HTTPException(
                    422, "Publish all fields cited by the selected interpretation"
                )
            interpreted = {
                "id": str(interpretation.id),
                "revision": interpretation.revision,
                "content": deepcopy(interpretation.content),
                "resolved_evidence": deepcopy(resolved),
                "content_digest": interpretation.content_digest,
            }
        elif draft.interpretation_revision_id is not None:
            raise HTTPException(404, "Interpretation revision not found")
        return _bounded(
            {
                "schema": PUBLICATION_SCHEMA,
                "analysis": {
                    "id": str(run.id),
                    "source_scope": run.source_scope,
                    "engine_version": run.engine_version,
                    "source_digest": run.source_digest,
                    "recipe_digest": run.recipe_digest,
                    "result_digest": run.result_digest,
                },
                "title": draft.title,
                "summary": draft.summary,
                "warnings": deepcopy(run.result.get("warnings", []))
                if run.source_scope == "project"
                else [],
                "sources": _source_manifest(run),
                "sections": sections,
                "join_audit": deepcopy(run.result["join"]["audit"])
                if run.source_scope == "project" and run.result.get("join") is not None
                else None,
                "interpretation": interpreted,
            }
        )
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(
            409, "Computed analysis publication contract is invalid"
        ) from exc


def analysis_publication_digest(row):
    return canonical_digest(
        {
            "id": str(row.id),
            "project_id": str(row.project_id),
            "task_id": str(row.task_id),
            "analysis_run_id": str(row.analysis_run_id),
            "evidence_id": str(row.evidence_id),
            "created_by_user_id": str(row.created_by_user_id),
            "title": row.title,
            "summary": row.summary,
            "selection": row.selection,
            "snapshot": row.snapshot,
            "source_digest": row.source_digest,
            "recipe_digest": row.recipe_digest,
            "result_digest": row.result_digest,
            "interpretation_revision_id": str(row.interpretation_revision_id)
            if row.interpretation_revision_id
            else None,
            "interpretation_digest": row.interpretation_digest,
            "idempotency_key": str(row.idempotency_key),
            "request_digest": row.request_digest,
        }
    )


def verify_analysis_publication(row):
    try:
        _bounded(row.snapshot)
        draft = AnalysisPublicationDraft.model_validate(row.selection)
        source = row.snapshot["analysis"]
        interpreted = row.snapshot.get("interpretation")
        if (
            row.digest != analysis_publication_digest(row)
            or row.snapshot["schema"] != PUBLICATION_SCHEMA
            or draft.task_id != row.task_id
            or draft.title != row.title
            or draft.summary != row.summary
            or row.snapshot["title"] != row.title
            or row.snapshot["summary"] != row.summary
            or source["id"] != str(row.analysis_run_id)
            or any(
                source[key] != getattr(row, key)
                for key in ("source_digest", "recipe_digest", "result_digest")
            )
            or draft.interpretation_revision_id != row.interpretation_revision_id
            or (interpreted is None) != (row.interpretation_revision_id is None)
            or (
                interpreted is not None
                and (
                    interpreted["id"] != str(row.interpretation_revision_id)
                    or interpreted["content_digest"] != row.interpretation_digest
                )
            )
        ):
            raise ValueError("Publication seal does not match")
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise HTTPException(409, "Analysis publication integrity check failed") from exc


def publication_payload(row):
    verify_analysis_publication(row)
    return {
        key: value
        for key, value in row.as_dict().items()
        if key
        in {
            "id",
            "task_id",
            "project_id",
            "analysis_run_id",
            "title",
            "summary",
            "snapshot",
            "digest",
            "created_by_user_id",
            "created_at",
            "evidence_id",
        }
    }


async def _task(db, task_id, user, capability, *, lock=False):
    statement = (
        select(ResearchTask)
        .where(ResearchTask.id == task_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        statement = statement.with_for_update(read=True)
    task = await db.scalar(statement)
    project = (
        await db.get(Project, task.project_id, populate_existing=True) if task else None
    )
    if (
        task is None
        or task.archived_at is not None
        or project is None
        or project.deleted_at is not None
        or task.lab_id != project.lab_id
    ):
        raise HTTPException(404, "Research Task not found")
    await require_research_capability(
        db, user=user, project=project, capability=capability
    )
    return task, project


async def _run(db, analysis_id, user, *, private, lock=False):
    statement = (
        select(AnalysisRun)
        .where(AnalysisRun.id == analysis_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        statement = statement.with_for_update(read=True)
    run = await db.scalar(statement)
    if run is None or (private and run.created_by_user_id != user.id):
        raise HTTPException(404, "Analysis not found")
    _supported_run(run)
    if private:
        await authorize_snapshot(db, run, user)
    else:
        await authorize_analysis_sources(db, run, user)
    return run


async def _exact_sources(db, run, user, *, lock=False):
    """Check accurate historic bytes and Schema, not merely membership/counts."""
    try:
        sources = sorted(_source_slots(run), key=lambda item: item[1]["protocol_id"])
        if lock:
            for _, source in sources:
                protocol_id = UUID(source["protocol_id"])
                locked = await db.scalars(
                    select(Protocol)
                    .where(Protocol.id == protocol_id)
                    .with_for_update(read=True)
                    .execution_options(populate_existing=True)
                )
                locked.all()
                locked = await db.scalars(
                    select(ProtocolVersion)
                    .where(
                        ProtocolVersion.protocol_id == protocol_id,
                        ProtocolVersion.id.in_(
                            [UUID(schema["id"]) for schema in source["schemas"]]
                        ),
                    )
                    .order_by(ProtocolVersion.id)
                    .with_for_update(read=True)
                    .execution_options(populate_existing=True)
                )
                locked.all()
                locked = await db.scalars(
                    select(Record)
                    .where(
                        Record.protocol_id == protocol_id,
                        tuple_(Record.id, Record.version).in_(
                            [
                                (UUID(record["record_id"]), record["record_version"])
                                for record in source["records"]
                            ]
                        ),
                    )
                    .order_by(Record.id, Record.version)
                    .with_for_update(read=True)
                    .execution_options(populate_existing=True)
                )
                locked.all()
        for _, source in sources:
            exact = AnalysisSelection(
                mode="selected",
                records=[
                    {"id": record["record_id"], "version": record["record_version"]}
                    for record in source["records"]
                ],
            )
            current, _, project = await capture_sources(
                db, protocol_id=UUID(source["protocol_id"]), user=user, selection=exact
            )
            if project.id != run.project_id or canonical_digest(
                current
            ) != canonical_digest(source):
                raise HTTPException(
                    409, "Analysis exact Record or Schema source changed"
                )
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise HTTPException(409, "Analysis exact sources are unavailable") from exc


async def _interpretation(db, run, identity):
    if identity is None:
        return None
    row = await db.get(AnalysisInterpretationRevision, identity, populate_existing=True)
    if row is None or row.analysis_run_id != run.id:
        raise HTTPException(404, "Interpretation revision not found")
    return row


async def publication_context(db, analysis_id, user, *, task_limit=50, task_offset=0):
    run = await _run(db, analysis_id, user, private=True)
    await _exact_sources(db, run, user)
    catalog = _report_catalog(run)
    rows = list(
        (
            await db.scalars(
                select(ResearchTask)
                .where(
                    ResearchTask.project_id == run.project_id,
                    ResearchTask.archived_at.is_(None),
                )
                .order_by(ResearchTask.created_at.desc(), ResearchTask.id)
                .offset(task_offset)
                .limit(task_limit + 1)
            )
        ).all()
    )
    tasks = []
    for row in rows[:task_limit]:
        try:
            await _task(db, row.id, user, "research.run")
        except HTTPException as exc:
            if exc.status_code in {403, 404}:
                continue
            raise
        tasks.append({"id": str(row.id), "title": row.title})
    interpretations = list(
        (
            await db.scalars(
                select(AnalysisInterpretationRevision)
                .where(AnalysisInterpretationRevision.analysis_run_id == run.id)
                .order_by(AnalysisInterpretationRevision.revision.desc())
                .limit(100)
            )
        ).all()
    )
    return {
        "analysis_id": str(run.id),
        "project_id": str(run.project_id),
        "source_scope": run.source_scope,
        "engine_version": run.engine_version,
        "result_digest": run.result_digest,
        "sections": [
            {
                "section_id": key,
                "label": item["label"],
                "fields": [
                    _field_descriptor(field) for field in item["report"]["fields"]
                ],
            }
            for key, item in catalog.items()
        ],
        "interpretations": [
            {
                "id": str(row.id),
                "revision": row.revision,
                "summary": row.content["summary"],
                "result_digest": row.result_digest,
            }
            for row in interpretations
        ],
        "tasks": tasks,
        "next_task_offset": task_offset + task_limit
        if len(rows) > task_limit
        else None,
    }


async def _preview_command(db, analysis_id, user, draft, *, lock=False):
    task, project = await _task(db, draft.task_id, user, "research.run", lock=lock)
    run = await _run(db, analysis_id, user, private=True, lock=lock)
    if run.project_id != task.project_id:
        raise HTTPException(404, "Analysis does not belong to the target Task Project")
    await _exact_sources(db, run, user, lock=lock)
    interpretation = await _interpretation(db, run, draft.interpretation_revision_id)
    snapshot = build_publication_snapshot(run, draft, interpretation)
    latest_interpretation = await db.scalar(
        select(func.max(AnalysisInterpretationRevision.revision)).where(
            AnalysisInterpretationRevision.analysis_run_id == run.id
        )
    )
    command = {
        "user_id": str(user.id),
        "analysis_id": str(run.id),
        "draft": draft.model_dump(mode="json"),
        "publication": snapshot,
        "destination": {
            "task_id": str(task.id),
            "task_title": task.title,
            "project_id": str(project.id),
            "project_name": project.name,
        },
        "task_revision": task.revision,
        "latest_interpretation_revision": latest_interpretation or 0,
    }
    return command, run, task, project, interpretation


def sign_preview(*, user_id, analysis_id, digest, now=None):
    now = now or datetime.now(UTC)
    expires = now + PREVIEW_TTL
    token = jwt.encode(
        {
            "aud": PREVIEW_AUDIENCE,
            "sub": str(user_id),
            "analysis_id": str(analysis_id),
            "digest": digest,
            "iat": now,
            "exp": expires,
        },
        config.SECRET_KEY,
        algorithm="HS256",
    )
    return token, expires.isoformat()


def verify_preview(token, *, user_id, analysis_id, digest):
    try:
        claims = jwt.decode(
            token, config.SECRET_KEY, algorithms=["HS256"], audience=PREVIEW_AUDIENCE
        )
        if (
            any(
                claims.get(key) != value
                for key, value in {
                    "sub": str(user_id),
                    "analysis_id": str(analysis_id),
                    "digest": digest,
                }.items()
            )
            or "exp" not in claims
            or "iat" not in claims
        ):
            raise ValueError("Preview context differs")
    except (JWTError, ValueError, TypeError) as exc:
        raise HTTPException(
            409, "Analysis publication preview is invalid or expired; preview again"
        ) from exc


async def preview_analysis_publication(db, analysis_id, user, draft):
    command, _, _, _, _ = await _preview_command(db, analysis_id, user, draft)
    digest = canonical_digest(command)
    token, expires = sign_preview(
        user_id=user.id, analysis_id=analysis_id, digest=digest
    )
    return {
        "preview_digest": digest,
        "preview_token": token,
        "expires_at": expires,
        "destination": command["destination"],
        "publication": command["publication"],
        "effect": {
            "quality_state": "pending",
            "requires_review": True,
            "audience": "task_members_with_all_source_access",
            "original_report_remains_private": True,
            "raw_records_shared": False,
        },
    }


async def require_analysis_publication_readable(
    db, publication_id, user, *, task_id=None
):
    row = await db.get(
        AnalysisEvidencePublication, publication_id, populate_existing=True
    )
    if row is None or (task_id is not None and row.task_id != task_id):
        raise HTTPException(404, "Analysis publication not found")
    verify_analysis_publication(row)
    task, project = await _task(db, row.task_id, user, "research.read")
    run = await _run(db, row.analysis_run_id, user, private=False)
    if (
        row.project_id != project.id
        or run.project_id != project.id
        or row.created_by_user_id != run.created_by_user_id
    ):
        raise HTTPException(409, "Analysis publication source scope changed")
    await _exact_sources(db, run, user)
    interpretation = await _interpretation(db, run, row.interpretation_revision_id)
    expected = build_publication_snapshot(
        run, AnalysisPublicationDraft.model_validate(row.selection), interpretation
    )
    evidence = await db.get(ResearchEvidence, row.evidence_id, populate_existing=True)
    if (
        expected != row.snapshot
        or evidence is None
        or (
            evidence.task_id != task.id
            or evidence.created_by_user_id != row.created_by_user_id
            or evidence.summary != row.summary
            or evidence.artifact_type != "analysis_publication"
            or evidence.artifact_id != str(row.id)
            or evidence.artifact_version != row.digest
            or evidence.kind != "analysis"
            or evidence.run_id is not None
            or evidence.action_id is not None
        )
    ):
        raise HTTPException(409, "Analysis publication or Evidence linkage changed")
    return row


async def confirm_analysis_publication(db, analysis_id, user, params):
    draft = AnalysisPublicationDraft.model_validate(
        params.model_dump(
            exclude={"preview_digest", "preview_token", "client_idempotency_key"}
        )
    )
    await request_lock(db, user.id, params.client_idempotency_key)
    existing = await db.scalar(
        select(AnalysisEvidencePublication).where(
            AnalysisEvidencePublication.created_by_user_id == user.id,
            AnalysisEvidencePublication.idempotency_key
            == params.client_idempotency_key,
        )
    )
    if existing is not None:
        if (
            existing.analysis_run_id != analysis_id
            or existing.request_digest != params.preview_digest
            or existing.selection != draft.model_dump(mode="json")
        ):
            raise HTTPException(
                409, "Publication idempotency key belongs to another request"
            )
        # A successful request remains recoverable after its preview expires.
        # Recovery still requires original ownership and live source authorization.
        await _run(db, analysis_id, user, private=True)
        await _task(db, existing.task_id, user, "research.run")
        row = await require_analysis_publication_readable(db, existing.id, user)
        return {
            "publication": publication_payload(row),
            "evidence": (await db.get(ResearchEvidence, row.evidence_id)).as_dict(),
        }
    verify_preview(
        params.preview_token,
        user_id=user.id,
        analysis_id=analysis_id,
        digest=params.preview_digest,
    )
    command, run, task, _, interpretation = await _preview_command(
        db, analysis_id, user, draft, lock=True
    )
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(409, "Analysis publication preview changed; preview again")
    publication_id, evidence_id = uuid4(), uuid4()
    row = AnalysisEvidencePublication(
        id=publication_id,
        project_id=task.project_id,
        task_id=task.id,
        analysis_run_id=run.id,
        interpretation_revision_id=interpretation.id if interpretation else None,
        evidence_id=evidence_id,
        created_by_user_id=user.id,
        title=draft.title,
        summary=draft.summary,
        selection=draft.model_dump(mode="json"),
        snapshot=command["publication"],
        source_digest=run.source_digest,
        recipe_digest=run.recipe_digest,
        result_digest=run.result_digest,
        interpretation_digest=interpretation.content_digest if interpretation else None,
        idempotency_key=params.client_idempotency_key,
        request_digest=params.preview_digest,
    )
    row.digest = analysis_publication_digest(row)
    evidence = ResearchEvidence(
        id=evidence_id,
        task_id=task.id,
        run_id=None,
        action_id=None,
        kind="analysis",
        artifact_type="analysis_publication",
        artifact_id=str(row.id),
        artifact_version=row.digest,
        summary=draft.summary,
        quality_state="pending",
        created_by_user_id=user.id,
    )
    db.add(evidence)
    await db.flush()
    db.add(row)
    await db.flush()
    await emit_research_event(
        db,
        task_id=task.id,
        kind="analysis.evidence_published",
        actor_user_id=user.id,
        payload={
            "publication_id": str(row.id),
            "evidence_id": str(evidence.id),
            "digest": row.digest,
        },
        idempotency_key=f"analysis-publication:{row.id}:published",
    )
    await emit_research_event(
        db,
        task_id=task.id,
        kind="evidence.registered",
        actor_user_id=user.id,
        payload={"evidence_id": str(evidence.id), "kind": "analysis"},
        idempotency_key=f"evidence:{evidence.id}:registered",
    )
    return {"publication": publication_payload(row), "evidence": evidence.as_dict()}
