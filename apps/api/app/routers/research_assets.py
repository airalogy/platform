"""Traceable DataAsset, Evidence, and Claim APIs for Research Tasks."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, select

from app.database import DBSession
from app.models.knowledge import (
    KnowledgeItem,
    OwnerScope,
    PaperLibraryEntry,
    ResearchFile,
    Visibility,
)
from app.models.lab import Lab
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.record import Record
from app.models.research import (
    ResearchAction,
    ResearchArtifactLink,
    ResearchRun,
    ResearchTask,
)
from app.models.research_asset import (
    ClaimEvidenceRelation,
    ClaimState,
    DataAsset,
    DataAssetKind,
    DataAssetStatus,
    DataAssetVersion,
    EvidenceKind,
    EvidenceQuality,
    ResearchClaim,
    ResearchClaimEvidence,
    ResearchClaimRevision,
    ResearchEvidence,
)
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.knowledge import (
    authorize_knowledge_item,
    authorize_library_entry,
    authorize_research_file,
)
from app.services.research_assets import research_asset_bundle
from app.services.research_runtime import (
    canonical_digest,
    emit_research_event,
    require_research_capability,
    utcnow,
)

router = APIRouter(prefix="/research-assets", tags=["research-assets"])

ArtifactType = Literal[
    "record", "data_asset", "knowledge", "paper_library_entry", "external"
]
ALLOWED_EXTERNAL_SCHEMES = {"https", "s3", "gs", "oss", "minio"}


@dataclass(frozen=True)
class TaskContext:
    task: ResearchTask
    project: Project
    lab: Lab


class DataAssetDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: UUID
    name: str = Field(min_length=1, max_length=512)
    description: str = Field(default="", max_length=100_000)
    kind: DataAssetKind
    research_file_id: UUID | None = None
    external_uri: str = Field(default="", max_length=4_000)
    media_type: str = Field(default="", max_length=255)
    checksum: str = Field(default="", max_length=128)
    byte_size: int | None = Field(default=None, ge=0)
    data_schema: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=dict)
    change_summary: str = Field(default="Created", max_length=4_000)

    @model_validator(mode="after")
    def normalize(self):
        self.name = self.name.strip()
        self.description = self.description.strip()
        self.external_uri = self.external_uri.strip()
        self.media_type = self.media_type.strip()
        self.checksum = self.checksum.strip()
        self.change_summary = self.change_summary.strip() or "Created"
        if bool(self.research_file_id) == bool(self.external_uri):
            raise ValueError("Select exactly one file or external URI")
        if self.external_uri:
            validate_external_uri(self.external_uri)
        return self


class DataAssetCreate(DataAssetDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class DataAssetVersionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    research_file_id: UUID | None = None
    external_uri: str = Field(default="", max_length=4_000)
    media_type: str = Field(default="", max_length=255)
    checksum: str = Field(default="", max_length=128)
    byte_size: int | None = Field(default=None, ge=0)
    data_schema: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=dict)
    change_summary: str = Field(min_length=1, max_length=4_000)

    @model_validator(mode="after")
    def normalize(self):
        self.external_uri = self.external_uri.strip()
        self.media_type = self.media_type.strip()
        self.checksum = self.checksum.strip()
        self.change_summary = self.change_summary.strip()
        if bool(self.research_file_id) == bool(self.external_uri):
            raise ValueError("Select exactly one file or external URI")
        if self.external_uri:
            validate_external_uri(self.external_uri)
        if not self.change_summary:
            raise ValueError("Version change summary is required")
        return self


class DataAssetVersionCreate(DataAssetVersionDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class DataAssetStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_status: DataAssetStatus
    status: Literal["draft", "ready", "archived"]


class EvidenceDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: UUID
    run_id: UUID | None = None
    action_id: UUID | None = None
    kind: EvidenceKind
    artifact_type: ArtifactType
    artifact_id: str = Field(min_length=1, max_length=2_000)
    artifact_version: str = Field(default="", max_length=64)
    summary: str = Field(default="", max_length=100_000)

    @model_validator(mode="after")
    def normalize(self):
        self.artifact_id = self.artifact_id.strip()
        self.artifact_version = self.artifact_version.strip()
        self.summary = self.summary.strip()
        if not self.artifact_id:
            raise ValueError("Evidence artifact is required")
        if self.artifact_type == "external":
            validate_external_uri(self.artifact_id)
        return self


class EvidenceCreate(EvidenceDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class EvidenceReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_quality_state: EvidenceQuality
    quality_state: Literal["validated", "rejected"]
    validation_report: dict[str, Any] = Field(default_factory=dict)


class ClaimEvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: UUID
    relation: ClaimEvidenceRelation = ClaimEvidenceRelation.SUPPORTS
    rationale: str = Field(default="", max_length=20_000)


class ClaimDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: UUID
    statement: str = Field(min_length=1, max_length=100_000)
    confidence: Decimal | None = Field(default=None, ge=0, le=1, decimal_places=4)
    uncertainty: str = Field(default="", max_length=100_000)
    evidence: list[ClaimEvidenceInput] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def normalize(self):
        self.statement = self.statement.strip()
        self.uncertainty = self.uncertainty.strip()
        if not self.statement:
            raise ValueError("Claim statement is required")
        ids = [item.evidence_id for item in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("Claim evidence contains duplicates")
        return self


class ClaimCreate(ClaimDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class ClaimRevisionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    statement: str = Field(min_length=1, max_length=100_000)
    confidence: Decimal | None = Field(default=None, ge=0, le=1, decimal_places=4)
    uncertainty: str = Field(default="", max_length=100_000)
    evidence: list[ClaimEvidenceInput] = Field(default_factory=list, max_length=100)
    change_summary: str = Field(min_length=1, max_length=4_000)

    @model_validator(mode="after")
    def normalize(self):
        self.statement = self.statement.strip()
        self.uncertainty = self.uncertainty.strip()
        self.change_summary = self.change_summary.strip()
        ids = [item.evidence_id for item in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("Claim evidence contains duplicates")
        if not self.statement or not self.change_summary:
            raise ValueError("Statement and change summary are required")
        return self


class ClaimRevisionCreate(ClaimRevisionDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class ClaimReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    expected_state: ClaimState
    state: Literal["reviewed", "rejected"]


def validate_external_uri(value: str) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme.lower() not in ALLOWED_EXTERNAL_SCHEMES
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("External URI must be an approved absolute URI")


async def _task_context(
    db_session: DBSession,
    current_user: User,
    task_id: UUID,
    capability: str,
) -> TaskContext:
    task = await db_session.get(ResearchTask, task_id)
    if task is None or task.archived_at is not None:
        raise HTTPException(status_code=404, detail="Research Task not found")
    project = await Project.find_by(
        db_session, [Project.id == task.project_id, Project.deleted_at.is_(None)]
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await require_research_capability(
        db_session, user=current_user, project=project, capability=capability
    )
    lab = await db_session.get(Lab, task.lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    return TaskContext(task=task, project=project, lab=lab)


async def _validate_execution_refs(
    db_session: DBSession,
    context: TaskContext,
    *,
    run_id: UUID | None,
    action_id: UUID | None,
) -> tuple[ResearchRun | None, ResearchAction | None]:
    run = await db_session.get(ResearchRun, run_id) if run_id else None
    if run_id and (run is None or run.task_id != context.task.id):
        raise HTTPException(status_code=404, detail="Research Run not found")
    action = await db_session.get(ResearchAction, action_id) if action_id else None
    if action_id and (
        action is None
        or run is None
        or action.run_id != run.id
        or run.task_id != context.task.id
    ):
        raise HTTPException(
            status_code=422,
            detail="Evidence Action requires its matching Research Run",
        )
    return run, action


async def _validate_research_file(
    db_session: DBSession,
    current_user: User,
    context: TaskContext,
    research_file_id: UUID | None,
) -> ResearchFile | None:
    if research_file_id is None:
        return None
    file = await db_session.get(ResearchFile, research_file_id)
    if file is None or file.archived_at is not None:
        raise HTTPException(status_code=404, detail="Research File not found")
    await authorize_research_file(db_session, current_user, file)
    if (
        file.scope_type == OwnerScope.PERSONAL.value
        or file.lab_id != context.lab.id
        or (file.project_id is not None and file.project_id != context.project.id)
        or file.visibility in {Visibility.PRIVATE.value, Visibility.RESTRICTED.value}
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Use a non-restricted Lab or matching Project file so creating "
                "the DataAsset cannot broaden private-file access"
            ),
        )
    return file


def _data_asset_command(params: DataAssetDraft) -> dict[str, Any]:
    return params.model_dump(mode="json")


def _data_asset_version_command(
    *,
    asset_id: UUID,
    params: DataAssetVersionDraft,
) -> dict[str, Any]:
    return {"data_asset_id": str(asset_id), **params.model_dump(mode="json")}


async def _data_asset_context(
    db_session: DBSession,
    current_user: User,
    asset_id: UUID,
    capability: str,
) -> tuple[DataAsset, TaskContext]:
    asset = await db_session.get(DataAsset, asset_id)
    if asset is None or asset.archived_at is not None:
        raise HTTPException(status_code=404, detail="DataAsset not found")
    if asset.task_id is None:
        raise HTTPException(status_code=409, detail="DataAsset has no Research Task")
    context = await _task_context(db_session, current_user, asset.task_id, capability)
    if asset.project_id != context.project.id or asset.lab_id != context.lab.id:
        raise HTTPException(status_code=404, detail="DataAsset not found")
    return asset, context


def _data_asset_payload(asset: DataAsset, version: DataAssetVersion) -> dict[str, Any]:
    return {**asset.as_dict(), "versions": [version.as_dict()]}


async def _validate_evidence_artifact(
    db_session: DBSession,
    current_user: User,
    context: TaskContext,
    *,
    artifact_type: ArtifactType,
    artifact_id: str,
    artifact_version: str,
) -> str:
    if artifact_type == "external":
        validate_external_uri(artifact_id)
        return artifact_version
    try:
        parsed_id = UUID(artifact_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="Artifact ID must be a UUID"
        ) from exc

    if artifact_type == "record":
        if not artifact_version.isdigit():
            raise HTTPException(status_code=422, detail="Record version is required")
        record = await db_session.get(Record, (parsed_id, int(artifact_version)))
        if record is None or record.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Record not found")
        protocol = await db_session.get(Protocol, record.protocol_id)
        if protocol is None or protocol.project_id != context.project.id:
            raise HTTPException(status_code=404, detail="Record not found")
        return str(record.version)

    if artifact_type == "data_asset":
        asset = await db_session.get(DataAsset, parsed_id)
        if (
            asset is None
            or asset.archived_at is not None
            or asset.project_id != context.project.id
        ):
            raise HTTPException(status_code=404, detail="DataAsset not found")
        version = (
            int(artifact_version)
            if artifact_version.isdigit()
            else asset.current_version
        )
        exists = await DataAssetVersion.exists(
            db_session,
            [
                DataAssetVersion.data_asset_id == asset.id,
                DataAssetVersion.version == version,
            ],
        )
        if not exists:
            raise HTTPException(status_code=404, detail="DataAsset version not found")
        return str(version)

    if artifact_type == "knowledge":
        item = await db_session.get(KnowledgeItem, parsed_id)
        if item is None or item.archived_at is not None:
            raise HTTPException(status_code=404, detail="Knowledge item not found")
        await authorize_knowledge_item(db_session, current_user, item)
        if (
            item.lab_id != context.lab.id
            or (item.project_id is not None and item.project_id != context.project.id)
            or item.scope_type == OwnerScope.PERSONAL.value
            or item.visibility == Visibility.RESTRICTED.value
        ):
            raise HTTPException(status_code=404, detail="Knowledge item not found")
        if artifact_version and artifact_version != str(item.revision):
            raise HTTPException(
                status_code=409, detail="Knowledge revision has changed"
            )
        return str(item.revision)

    entry = await db_session.get(PaperLibraryEntry, parsed_id)
    if entry is None or entry.archived_at is not None:
        raise HTTPException(status_code=404, detail="Paper not found")
    await authorize_library_entry(db_session, current_user, entry)
    if (
        entry.lab_id != context.lab.id
        or (entry.project_id is not None and entry.project_id != context.project.id)
        or entry.scope_type == OwnerScope.PERSONAL.value
        or entry.visibility == Visibility.RESTRICTED.value
    ):
        raise HTTPException(status_code=404, detail="Paper not found")
    return artifact_version


async def _validated_evidence_command(
    db_session: DBSession,
    current_user: User,
    params: EvidenceDraft,
) -> tuple[dict[str, Any], TaskContext]:
    context = await _task_context(
        db_session, current_user, params.task_id, "research.run"
    )
    await _validate_execution_refs(
        db_session,
        context,
        run_id=params.run_id,
        action_id=params.action_id,
    )
    version = await _validate_evidence_artifact(
        db_session,
        current_user,
        context,
        artifact_type=params.artifact_type,
        artifact_id=params.artifact_id,
        artifact_version=params.artifact_version,
    )
    return {
        **params.model_dump(mode="json"),
        "artifact_version": version,
    }, context


async def _evidence_for_task(
    db_session: DBSession,
    task_id: UUID,
    evidence_inputs: list[ClaimEvidenceInput],
) -> list[ResearchEvidence]:
    if not evidence_inputs:
        return []
    ids = [item.evidence_id for item in evidence_inputs]
    evidence = list(
        (
            await db_session.scalars(
                select(ResearchEvidence).where(
                    ResearchEvidence.id.in_(ids), ResearchEvidence.task_id == task_id
                )
            )
        ).all()
    )
    if {item.id for item in evidence} != set(ids):
        raise HTTPException(
            status_code=422, detail="Claim evidence is not in this Task"
        )
    return evidence


def _claim_command(params: ClaimDraft | ClaimRevisionDraft) -> dict[str, Any]:
    excluded = {"expected_revision", "change_summary"}
    return params.model_dump(mode="json", exclude=excluded)


def _claim_snapshot(
    claim: ResearchClaim, relations: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "statement": claim.statement,
        "confidence": float(claim.confidence) if claim.confidence is not None else None,
        "uncertainty": claim.uncertainty,
        "state": claim.state,
        "generated_by": claim.generated_by,
        "evidence": relations,
    }


async def _add_claim_relations(
    db_session: DBSession,
    current_user: User,
    claim: ResearchClaim,
    evidence_inputs: list[ClaimEvidenceInput],
) -> list[dict[str, Any]]:
    await _evidence_for_task(db_session, claim.task_id, evidence_inputs)
    payload: list[dict[str, Any]] = []
    for item in evidence_inputs:
        relation = {
            "evidence_id": str(item.evidence_id),
            "relation": item.relation.value,
            "rationale": item.rationale.strip(),
        }
        db_session.add(
            ResearchClaimEvidence(
                claim_id=claim.id,
                evidence_id=item.evidence_id,
                relation=item.relation.value,
                rationale=item.rationale.strip(),
                created_by_user_id=current_user.id,
            )
        )
        payload.append(relation)
    return payload


@router.get("/tasks/{task_id}")
async def get_task_research_assets(
    task_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _task_context(db_session, current_user, task_id, "research.read")
    return await research_asset_bundle(db_session, task_id=task_id)


@router.post("/data-assets/preview")
async def preview_data_asset(
    params: DataAssetDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    context = await _task_context(
        db_session, current_user, params.task_id, "research.run"
    )
    file = await _validate_research_file(
        db_session, current_user, context, params.research_file_id
    )
    command = _data_asset_command(params)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": {
            "task_id": str(context.task.id),
            "task_title": context.task.title,
            "project_id": str(context.project.id),
            "project_name": context.project.name,
        },
        "file": (
            {"id": str(file.id), "filename": file.filename}
            if file is not None
            else None
        ),
        "effect": "Create DataAsset version 1 as draft",
    }


@router.post("/data-assets")
async def create_data_asset(
    params: DataAssetCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    context = await _task_context(
        db_session, current_user, params.task_id, "research.run"
    )
    await _validate_research_file(
        db_session, current_user, context, params.research_file_id
    )
    draft = DataAssetDraft.model_validate(params.model_dump(exclude={"preview_digest"}))
    command = _data_asset_command(draft)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="DataAsset preview has changed")
    asset = DataAsset(
        lab_id=context.lab.id,
        project_id=context.project.id,
        task_id=context.task.id,
        name=draft.name,
        description=draft.description,
        kind=draft.kind.value,
        status=DataAssetStatus.DRAFT.value,
        current_version=1,
        created_by_user_id=current_user.id,
    )
    db_session.add(asset)
    await db_session.flush()
    version = DataAssetVersion(
        data_asset_id=asset.id,
        version=1,
        research_file_id=draft.research_file_id,
        external_uri=draft.external_uri,
        media_type=draft.media_type,
        checksum=draft.checksum,
        byte_size=draft.byte_size,
        data_schema=draft.data_schema,
        version_metadata=draft.metadata,
        source=draft.source,
        change_summary=draft.change_summary,
        created_by_user_id=current_user.id,
    )
    db_session.add(version)
    db_session.add(
        ResearchArtifactLink(
            task_id=context.task.id,
            artifact_type="data_asset",
            artifact_id=str(asset.id),
            artifact_version="1",
            relation="produced",
            link_metadata={"kind": asset.kind, "name": asset.name},
        )
    )
    await emit_research_event(
        db_session,
        task_id=context.task.id,
        kind="data_asset.created",
        actor_user_id=current_user.id,
        payload={"data_asset_id": str(asset.id), "version": 1, "name": asset.name},
        idempotency_key=f"data-asset:{asset.id}:version:1",
    )
    await db_session.commit()
    return _data_asset_payload(asset, version)


@router.post("/data-assets/{asset_id}/versions/preview")
async def preview_data_asset_version(
    asset_id: UUID,
    params: DataAssetVersionDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    asset, context = await _data_asset_context(
        db_session, current_user, asset_id, "research.run"
    )
    if asset.current_version != params.expected_version:
        raise HTTPException(status_code=409, detail="DataAsset has changed")
    await _validate_research_file(
        db_session, current_user, context, params.research_file_id
    )
    command = _data_asset_version_command(asset_id=asset.id, params=params)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "effect": {
            "current_version": asset.current_version,
            "new_version": asset.current_version + 1,
        },
    }


@router.post("/data-assets/{asset_id}/versions")
async def create_data_asset_version(
    asset_id: UUID,
    params: DataAssetVersionCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    asset, context = await _data_asset_context(
        db_session, current_user, asset_id, "research.run"
    )
    if asset.current_version != params.expected_version:
        raise HTTPException(status_code=409, detail="DataAsset has changed")
    await _validate_research_file(
        db_session, current_user, context, params.research_file_id
    )
    draft = DataAssetVersionDraft.model_validate(
        params.model_dump(exclude={"preview_digest"})
    )
    command = _data_asset_version_command(asset_id=asset.id, params=draft)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="DataAsset preview has changed")
    new_version = asset.current_version + 1
    version = DataAssetVersion(
        data_asset_id=asset.id,
        version=new_version,
        research_file_id=draft.research_file_id,
        external_uri=draft.external_uri,
        media_type=draft.media_type,
        checksum=draft.checksum,
        byte_size=draft.byte_size,
        data_schema=draft.data_schema,
        version_metadata=draft.metadata,
        source=draft.source,
        change_summary=draft.change_summary,
        created_by_user_id=current_user.id,
    )
    db_session.add(version)
    asset.current_version = new_version
    asset.status = DataAssetStatus.DRAFT.value
    db_session.add(
        ResearchArtifactLink(
            task_id=context.task.id,
            artifact_type="data_asset",
            artifact_id=str(asset.id),
            artifact_version=str(new_version),
            relation="produced",
            link_metadata={"kind": asset.kind, "name": asset.name},
        )
    )
    await emit_research_event(
        db_session,
        task_id=context.task.id,
        kind="data_asset.version_created",
        actor_user_id=current_user.id,
        payload={"data_asset_id": str(asset.id), "version": new_version},
        idempotency_key=f"data-asset:{asset.id}:version:{new_version}",
    )
    await db_session.commit()
    return _data_asset_payload(asset, version)


@router.patch("/data-assets/{asset_id}/status")
async def update_data_asset_status(
    asset_id: UUID,
    params: DataAssetStatusUpdate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    asset, context = await _data_asset_context(
        db_session, current_user, asset_id, "research.approve"
    )
    if asset.status != params.expected_status.value:
        raise HTTPException(status_code=409, detail="DataAsset status has changed")
    allowed_transitions = {
        DataAssetStatus.DRAFT.value: {
            DataAssetStatus.READY.value,
            DataAssetStatus.ARCHIVED.value,
        },
        DataAssetStatus.READY.value: {DataAssetStatus.ARCHIVED.value},
    }
    if params.status not in allowed_transitions.get(asset.status, set()):
        raise HTTPException(status_code=409, detail="Invalid DataAsset status transition")
    asset.status = params.status
    if params.status == DataAssetStatus.ARCHIVED.value:
        asset.archived_at = utcnow()
    await emit_research_event(
        db_session,
        task_id=context.task.id,
        kind="data_asset.status_changed",
        actor_user_id=current_user.id,
        payload={"data_asset_id": str(asset.id), "status": asset.status},
        idempotency_key=f"data-asset:{asset.id}:status:{asset.status}:{asset.current_version}",
    )
    await db_session.commit()
    return asset.as_dict()


@router.post("/evidence/preview")
async def preview_evidence(
    params: EvidenceDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    command, context = await _validated_evidence_command(
        db_session, current_user, params
    )
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": {
            "task_id": str(context.task.id),
            "task_title": context.task.title,
        },
        "effect": "Register pending Evidence for review",
    }


@router.post("/evidence")
async def create_evidence(
    params: EvidenceCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    draft = EvidenceDraft.model_validate(params.model_dump(exclude={"preview_digest"}))
    command, context = await _validated_evidence_command(
        db_session, current_user, draft
    )
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="Evidence preview has changed")
    existing = await ResearchEvidence.find_by(
        db_session,
        [
            ResearchEvidence.task_id == context.task.id,
            ResearchEvidence.artifact_type == draft.artifact_type,
            ResearchEvidence.artifact_id == draft.artifact_id,
            ResearchEvidence.artifact_version == command["artifact_version"],
            ResearchEvidence.kind == draft.kind.value,
        ],
    )
    if existing is not None:
        if (
            existing.run_id == draft.run_id
            and existing.action_id == draft.action_id
            and existing.summary == draft.summary
        ):
            return existing.as_dict()
        raise HTTPException(
            status_code=409,
            detail="Evidence already exists for this artifact with different content",
        )
    evidence = ResearchEvidence(
        task_id=context.task.id,
        run_id=draft.run_id,
        action_id=draft.action_id,
        kind=draft.kind.value,
        artifact_type=draft.artifact_type,
        artifact_id=draft.artifact_id,
        artifact_version=command["artifact_version"],
        summary=draft.summary,
        quality_state=EvidenceQuality.PENDING.value,
        created_by_user_id=current_user.id,
    )
    db_session.add(evidence)
    await db_session.flush()
    await emit_research_event(
        db_session,
        task_id=context.task.id,
        run_id=draft.run_id,
        action_id=draft.action_id,
        kind="evidence.registered",
        actor_user_id=current_user.id,
        payload={"evidence_id": str(evidence.id), "kind": evidence.kind},
        idempotency_key=f"evidence:{evidence.id}:registered",
    )
    await db_session.commit()
    return evidence.as_dict()


@router.post("/evidence/{evidence_id}/review")
async def review_evidence(
    evidence_id: UUID,
    params: EvidenceReview,
    current_user: CurrentUser,
    db_session: DBSession,
):
    evidence = await db_session.get(ResearchEvidence, evidence_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    context = await _task_context(
        db_session, current_user, evidence.task_id, "research.approve"
    )
    if evidence.quality_state != params.expected_quality_state.value:
        raise HTTPException(status_code=409, detail="Evidence review state has changed")
    if evidence.quality_state != EvidenceQuality.PENDING.value:
        raise HTTPException(status_code=409, detail="Evidence review is already final")
    evidence.quality_state = params.quality_state
    evidence.validation_report = params.validation_report
    evidence.reviewed_by_user_id = current_user.id
    evidence.reviewed_at = utcnow()
    await emit_research_event(
        db_session,
        task_id=context.task.id,
        run_id=evidence.run_id,
        action_id=evidence.action_id,
        kind="evidence.reviewed",
        actor_user_id=current_user.id,
        payload={
            "evidence_id": str(evidence.id),
            "quality_state": evidence.quality_state,
        },
        idempotency_key=f"evidence:{evidence.id}:review:{evidence.quality_state}",
    )
    await db_session.commit()
    return evidence.as_dict()


@router.post("/claims/preview")
async def preview_claim(
    params: ClaimDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    context = await _task_context(
        db_session, current_user, params.task_id, "research.run"
    )
    await _evidence_for_task(db_session, context.task.id, params.evidence)
    command = _claim_command(params)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": {
            "task_id": str(context.task.id),
            "task_title": context.task.title,
        },
        "effect": "Create editable draft Claim",
    }


@router.post("/claims")
async def create_claim(
    params: ClaimCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    draft = ClaimDraft.model_validate(params.model_dump(exclude={"preview_digest"}))
    context = await _task_context(
        db_session, current_user, draft.task_id, "research.run"
    )
    await _evidence_for_task(db_session, context.task.id, draft.evidence)
    command = _claim_command(draft)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="Claim preview has changed")
    claim = ResearchClaim(
        task_id=context.task.id,
        statement=draft.statement,
        state=ClaimState.DRAFT.value,
        confidence=draft.confidence,
        uncertainty=draft.uncertainty,
        generated_by="human",
        created_by_user_id=current_user.id,
    )
    db_session.add(claim)
    await db_session.flush()
    relations = await _add_claim_relations(
        db_session, current_user, claim, draft.evidence
    )
    db_session.add(
        ResearchClaimRevision(
            claim_id=claim.id,
            revision=1,
            snapshot=_claim_snapshot(claim, relations),
            change_summary="Created",
            created_by_user_id=current_user.id,
        )
    )
    await emit_research_event(
        db_session,
        task_id=context.task.id,
        kind="claim.created",
        actor_user_id=current_user.id,
        payload={"claim_id": str(claim.id), "state": claim.state},
        idempotency_key=f"claim:{claim.id}:revision:1",
    )
    await db_session.commit()
    return {
        **claim.as_dict(),
        "confidence": float(claim.confidence) if claim.confidence is not None else None,
        "evidence": relations,
    }


@router.post("/claims/{claim_id}/revisions/preview")
async def preview_claim_revision(
    claim_id: UUID,
    params: ClaimRevisionDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    claim = await db_session.get(ResearchClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    await _task_context(db_session, current_user, claim.task_id, "research.run")
    if claim.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Claim has changed")
    await _evidence_for_task(db_session, claim.task_id, params.evidence)
    command = {"claim_id": str(claim.id), **_claim_command(params)}
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "effect": {
            "current_revision": claim.revision,
            "new_revision": claim.revision + 1,
        },
    }


@router.post("/claims/{claim_id}/revisions")
async def create_claim_revision(
    claim_id: UUID,
    params: ClaimRevisionCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    claim = await db_session.get(ResearchClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    context = await _task_context(
        db_session, current_user, claim.task_id, "research.run"
    )
    if claim.revision != params.expected_revision:
        raise HTTPException(status_code=409, detail="Claim has changed")
    draft = ClaimRevisionDraft.model_validate(
        params.model_dump(exclude={"preview_digest"})
    )
    await _evidence_for_task(db_session, claim.task_id, draft.evidence)
    command = {"claim_id": str(claim.id), **_claim_command(draft)}
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="Claim preview has changed")
    await db_session.execute(
        delete(ResearchClaimEvidence).where(ResearchClaimEvidence.claim_id == claim.id)
    )
    claim.statement = draft.statement
    claim.confidence = draft.confidence
    claim.uncertainty = draft.uncertainty
    claim.state = ClaimState.DRAFT.value
    claim.reviewed_by_user_id = None
    claim.reviewed_at = None
    claim.revision += 1
    relations = await _add_claim_relations(
        db_session, current_user, claim, draft.evidence
    )
    db_session.add(
        ResearchClaimRevision(
            claim_id=claim.id,
            revision=claim.revision,
            snapshot=_claim_snapshot(claim, relations),
            change_summary=draft.change_summary,
            created_by_user_id=current_user.id,
        )
    )
    await emit_research_event(
        db_session,
        task_id=context.task.id,
        kind="claim.revised",
        actor_user_id=current_user.id,
        payload={"claim_id": str(claim.id), "revision": claim.revision},
        idempotency_key=f"claim:{claim.id}:revision:{claim.revision}",
    )
    await db_session.commit()
    return {
        **claim.as_dict(),
        "confidence": float(claim.confidence) if claim.confidence is not None else None,
        "evidence": relations,
    }


@router.post("/claims/{claim_id}/review")
async def review_claim(
    claim_id: UUID,
    params: ClaimReview,
    current_user: CurrentUser,
    db_session: DBSession,
):
    claim = await db_session.get(ResearchClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    context = await _task_context(
        db_session, current_user, claim.task_id, "research.approve"
    )
    if (
        claim.revision != params.expected_revision
        or claim.state != params.expected_state.value
    ):
        raise HTTPException(status_code=409, detail="Claim review state has changed")
    if claim.state not in {ClaimState.SUGGESTED.value, ClaimState.DRAFT.value}:
        raise HTTPException(status_code=409, detail="Claim review is already final")
    claim.state = params.state
    claim.reviewed_by_user_id = current_user.id
    claim.reviewed_at = utcnow()
    await emit_research_event(
        db_session,
        task_id=context.task.id,
        kind="claim.reviewed",
        actor_user_id=current_user.id,
        payload={"claim_id": str(claim.id), "state": claim.state},
        idempotency_key=f"claim:{claim.id}:review:{claim.state}:r{claim.revision}",
    )
    await db_session.commit()
    return {
        **claim.as_dict(),
        "confidence": float(claim.confidence) if claim.confidence is not None else None,
    }
