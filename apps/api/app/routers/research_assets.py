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
from sqlalchemy.exc import IntegrityError

from app.config import config
from app.database import DBSession
from app.models.knowledge import (
    KnowledgeItem,
    KnowledgeKind,
    KnowledgeRevision,
    KnowledgeState,
    OwnerScope,
    PaperLibraryEntry,
    ResearchFile,
    Visibility,
)
from app.models.lab import Lab
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.research import (
    ResearchAction,
    ResearchArtifactLink,
    ResearchRun,
    ResearchTask,
    ResearchTaskProtocol,
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
    KnowledgeEvidenceLink,
    ProtocolImprovementEvidence,
    ProtocolImprovementProposal,
    ProtocolImprovementState,
    ResearchActionOutputSnapshot,
    ResearchClaim,
    ResearchClaimEvidence,
    ResearchClaimRevision,
    ResearchEvidence,
)
from app.models.user import User
from app.routers.depends import CurrentUser
from app.routers.permission import check_user_permission
from app.services.knowledge import (
    authorize_knowledge_item,
    authorize_library_entry,
    authorize_research_file,
    resolve_scope,
    snapshot_knowledge,
)
from app.services.model_usage import create_usage_context
from app.services.research_action_outputs import (
    ResearchActionOutputError,
    action_output_digest,
    action_output_payload,
    verify_action_output_snapshot,
)
from app.services.research_assets import research_asset_bundle
from app.services.research_claims import (
    AiraClaimGeneration,
    create_claim_generation,
    generate_claim,
    sign_claim_generation_receipt,
    verify_claim_generation_receipt,
)
from app.services.research_protocol_improvements import (
    AiraProtocolImprovementGeneration,
    create_generation,
    generate_protocol_improvement,
    sign_generation_receipt,
    verify_generation_receipt,
)
from app.services.research_runtime import (
    canonical_digest,
    emit_research_event,
    require_research_capability,
    utcnow,
)

router = APIRouter(prefix="/research-assets", tags=["research-assets"])

ArtifactType = Literal[
    "record",
    "data_asset",
    "knowledge",
    "paper_library_entry",
    "action_output",
    "external",
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
    aira_generation: AiraClaimGeneration | None = None
    aira_receipt: str | None = Field(default=None, min_length=1, max_length=20_000)

    @model_validator(mode="after")
    def normalize(self):
        self.statement = self.statement.strip()
        self.uncertainty = self.uncertainty.strip()
        if not self.statement:
            raise ValueError("Claim statement is required")
        ids = [item.evidence_id for item in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("Claim evidence contains duplicates")
        if bool(self.aira_generation) != bool(self.aira_receipt):
            raise ValueError("Aira generation and receipt must be provided together")
        return self


class ClaimCreate(ClaimDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class AiraClaimDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: UUID
    evidence_ids: list[UUID] = Field(min_length=1, max_length=100)
    instruction: str = Field(default="", max_length=4_000)

    @model_validator(mode="after")
    def normalize(self):
        self.instruction = self.instruction.strip()
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("Claim Evidence contains duplicates")
        return self


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


class KnowledgeSuggestionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: UUID
    title: str = Field(min_length=1, max_length=512)
    body: str = Field(min_length=1, max_length=2_000_000)
    kind: Literal[
        KnowledgeKind.NOTE,
        KnowledgeKind.METHOD,
        KnowledgeKind.DECISION,
        KnowledgeKind.FINDING,
    ] = KnowledgeKind.FINDING
    tags: list[str] = Field(default_factory=list, max_length=100)
    evidence_ids: list[UUID] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def normalize(self):
        self.title = self.title.strip()
        self.body = self.body.strip()
        self.tags = sorted(
            {tag.strip() for tag in self.tags if tag.strip()}, key=str.casefold
        )
        if not self.title or not self.body:
            raise ValueError("Knowledge title and body are required")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("Knowledge evidence contains duplicates")
        return self


class KnowledgeSuggestionCreate(KnowledgeSuggestionDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class ProtocolImprovementDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: UUID
    protocol_id: UUID
    title: str = Field(min_length=1, max_length=512)
    rationale: str = Field(min_length=1, max_length=100_000)
    proposed_changes: str = Field(min_length=1, max_length=200_000)
    evidence_ids: list[UUID] = Field(min_length=1, max_length=100)
    aira_generation: AiraProtocolImprovementGeneration | None = None
    aira_receipt: str | None = Field(default=None, min_length=1, max_length=20_000)

    @model_validator(mode="after")
    def normalize(self):
        self.title = self.title.strip()
        self.rationale = self.rationale.strip()
        self.proposed_changes = self.proposed_changes.strip()
        if not self.title or not self.rationale or not self.proposed_changes:
            raise ValueError("Improvement title, rationale, and changes are required")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("Protocol improvement Evidence contains duplicates")
        if bool(self.aira_generation) != bool(self.aira_receipt):
            raise ValueError("Aira generation and receipt must be provided together")
        return self


class ProtocolImprovementCreate(ProtocolImprovementDraft):
    preview_digest: str = Field(min_length=64, max_length=64)


class AiraProtocolImprovementDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: UUID
    protocol_id: UUID
    evidence_ids: list[UUID] = Field(min_length=1, max_length=100)
    instruction: str = Field(default="", max_length=4_000)

    @model_validator(mode="after")
    def normalize(self):
        self.instruction = self.instruction.strip()
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("Protocol improvement Evidence contains duplicates")
        return self


class ProtocolImprovementReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    expected_state: ProtocolImprovementState
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
    lock_action: bool = False,
) -> tuple[ResearchRun | None, ResearchAction | None]:
    run = await db_session.get(ResearchRun, run_id) if run_id else None
    if run_id and (run is None or run.task_id != context.task.id):
        raise HTTPException(status_code=404, detail="Research Run not found")
    action = None
    if action_id:
        statement = select(ResearchAction).where(ResearchAction.id == action_id)
        if lock_action:
            statement = statement.with_for_update().execution_options(
                populate_existing=True
            )
        action = (await db_session.scalars(statement)).first()
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
    action: ResearchAction | None = None,
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

    if artifact_type == "action_output":
        if action is None:
            action = await db_session.get(ResearchAction, parsed_id)
        if action is None or action.id != parsed_id:
            raise HTTPException(
                status_code=422,
                detail="Action output Evidence requires its matching Research Action",
            )
        run = await db_session.get(ResearchRun, action.run_id)
        if run is None or run.task_id != context.task.id:
            raise HTTPException(status_code=404, detail="Research Action not found")
        from app.services.research_action_outputs import (
            require_evidence_eligible_action,
        )

        try:
            require_evidence_eligible_action(action)
        except ResearchActionOutputError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        snapshot = await ResearchActionOutputSnapshot.find_by(
            db_session,
            [ResearchActionOutputSnapshot.action_id == action.id],
        )
        try:
            if snapshot is not None:
                verify_action_output_snapshot(snapshot)
                digest = snapshot.digest
            else:
                digest = action_output_digest(
                    action_output_payload(action, task_id=context.task.id)
                )
        except ResearchActionOutputError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if artifact_version and artifact_version != digest:
            raise HTTPException(
                status_code=409,
                detail="Research Action output has changed since preview",
            )
        return digest

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
    *,
    lock_action_output: bool = False,
) -> tuple[dict[str, Any], TaskContext, ResearchAction | None]:
    context = await _task_context(
        db_session, current_user, params.task_id, "research.run"
    )
    _run, action = await _validate_execution_refs(
        db_session,
        context,
        run_id=params.run_id,
        action_id=params.action_id,
        lock_action=(lock_action_output and params.artifact_type == "action_output"),
    )
    version = await _validate_evidence_artifact(
        db_session,
        current_user,
        context,
        artifact_type=params.artifact_type,
        artifact_id=params.artifact_id,
        artifact_version=params.artifact_version,
        action=action,
    )
    return (
        {
            **params.model_dump(mode="json"),
            "artifact_version": version,
        },
        context,
        action,
    )


async def _materialize_action_output_snapshot(
    db_session: DBSession,
    *,
    context: TaskContext,
    action: ResearchAction,
    expected_digest: str,
    current_user: User,
) -> ResearchActionOutputSnapshot:
    existing = await ResearchActionOutputSnapshot.find_by(
        db_session,
        [ResearchActionOutputSnapshot.action_id == action.id],
    )
    if existing is not None:
        try:
            verify_action_output_snapshot(existing)
        except ResearchActionOutputError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if existing.digest != expected_digest:
            raise HTTPException(
                status_code=409,
                detail="Research Action output snapshot does not match the preview",
            )
        return existing
    try:
        payload = action_output_payload(action, task_id=context.task.id)
    except ResearchActionOutputError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    digest = action_output_digest(payload)
    if digest != expected_digest:
        raise HTTPException(
            status_code=409,
            detail="Research Action output has changed since preview",
        )
    snapshot = ResearchActionOutputSnapshot(
        task_id=context.task.id,
        run_id=action.run_id,
        action_id=action.id,
        action_revision=action.revision,
        action_kind=action.kind,
        output_data=payload["output_data"],
        digest=digest,
        created_by_user_id=current_user.id,
    )
    db_session.add(snapshot)
    await db_session.flush()
    return snapshot


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


async def _validated_claim_evidence(
    db_session: DBSession,
    current_user: User,
    context: TaskContext,
    evidence_ids: list[UUID],
    *,
    with_for_update: bool = False,
) -> list[ResearchEvidence]:
    statement = select(ResearchEvidence).where(
        ResearchEvidence.id.in_(evidence_ids),
        ResearchEvidence.task_id == context.task.id,
    )
    if with_for_update:
        statement = statement.with_for_update()
    found = list((await db_session.scalars(statement)).all())
    by_id = {item.id: item for item in found}
    if set(by_id) != set(evidence_ids):
        raise HTTPException(
            status_code=422, detail="Claim Evidence is not in this Task"
        )
    evidence = [by_id[item_id] for item_id in evidence_ids]
    for item in evidence:
        if item.quality_state != EvidenceQuality.VALIDATED.value:
            raise HTTPException(
                status_code=409,
                detail="Aira can draft Claims only from validated Evidence",
            )
        version = await _validate_evidence_artifact(
            db_session,
            current_user,
            context,
            artifact_type=item.artifact_type,
            artifact_id=item.artifact_id,
            artifact_version=item.artifact_version,
        )
        if version != item.artifact_version:
            raise HTTPException(status_code=409, detail="Evidence source has changed")
    return evidence


def _evidence_snapshot(evidence: ResearchEvidence) -> dict[str, Any]:
    return {
        "id": str(evidence.id),
        "task_id": str(evidence.task_id),
        "run_id": str(evidence.run_id) if evidence.run_id else None,
        "action_id": str(evidence.action_id) if evidence.action_id else None,
        "kind": evidence.kind,
        "artifact_type": evidence.artifact_type,
        "artifact_id": evidence.artifact_id,
        "artifact_version": evidence.artifact_version,
        "summary": evidence.summary,
        "quality_state": evidence.quality_state,
        "validation_report": evidence.validation_report,
        "reviewed_by_user_id": (
            str(evidence.reviewed_by_user_id) if evidence.reviewed_by_user_id else None
        ),
        "reviewed_at": evidence.reviewed_at.isoformat()
        if evidence.reviewed_at
        else None,
    }


async def _knowledge_suggestion_evidence(
    db_session: DBSession,
    current_user: User,
    context: TaskContext,
    evidence_ids: list[UUID],
    *,
    with_for_update: bool = False,
) -> list[ResearchEvidence]:
    statement = select(ResearchEvidence).where(
        ResearchEvidence.id.in_(evidence_ids),
        ResearchEvidence.task_id == context.task.id,
    )
    if with_for_update:
        statement = statement.with_for_update()
    found = list((await db_session.scalars(statement)).all())
    by_id = {item.id: item for item in found}
    if set(by_id) != set(evidence_ids):
        raise HTTPException(
            status_code=422, detail="Knowledge evidence is not in this Task"
        )
    evidence = [by_id[item_id] for item_id in evidence_ids]
    for item in evidence:
        if item.quality_state != EvidenceQuality.VALIDATED.value:
            raise HTTPException(
                status_code=409,
                detail="Only validated Evidence can become Suggested Knowledge",
            )
        if item.artifact_type not in {"record", "data_asset", "action_output"}:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Suggested Knowledge requires Record, DataAsset, or immutable "
                    "Action output Evidence"
                ),
            )
        version = await _validate_evidence_artifact(
            db_session,
            current_user,
            context,
            artifact_type=item.artifact_type,
            artifact_id=item.artifact_id,
            artifact_version=item.artifact_version,
        )
        if version != item.artifact_version:
            raise HTTPException(status_code=409, detail="Evidence source has changed")
    return evidence


def _knowledge_suggestion_command(
    params: KnowledgeSuggestionDraft,
    evidence: list[ResearchEvidence],
) -> dict[str, Any]:
    return {
        **params.model_dump(mode="json"),
        "evidence": [_evidence_snapshot(item) for item in evidence],
    }


async def _protocol_improvement_context(
    db_session: DBSession,
    current_user: User,
    task_id: UUID,
    protocol_id: UUID,
) -> tuple[TaskContext, Protocol, ProtocolVersion]:
    context = await _task_context(db_session, current_user, task_id, "research.run")
    row = (
        await db_session.execute(
            select(Protocol, ProtocolVersion)
            .join(
                ResearchTaskProtocol,
                ResearchTaskProtocol.protocol_id == Protocol.id,
            )
            .join(
                ProtocolVersion,
                ProtocolVersion.id == ResearchTaskProtocol.protocol_version_id,
            )
            .where(
                ResearchTaskProtocol.task_id == context.task.id,
                ResearchTaskProtocol.protocol_id == protocol_id,
                ProtocolVersion.protocol_id == Protocol.id,
                ProtocolVersion.version == ResearchTaskProtocol.protocol_version,
                Protocol.deleted_at.is_(None),
            )
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=422,
            detail="Protocol improvement must target a version pinned to this Task",
        )
    protocol, version = row
    await check_user_permission(
        db_session,
        project=context.project,
        user=current_user,
        action="update_protocol",
        protocol=protocol,
    )
    return context, protocol, version


def _protocol_improvement_snapshot(
    protocol: Protocol,
    version: ProtocolVersion,
) -> dict[str, Any]:
    return {
        "id": str(protocol.id),
        "uid": protocol.uid,
        "name": protocol.name,
        "base_protocol_version_id": str(version.id),
        "base_protocol_version": version.version,
    }


def _protocol_improvement_command(
    params: ProtocolImprovementDraft,
    protocol_snapshot: dict[str, Any],
    evidence: list[ResearchEvidence],
) -> dict[str, Any]:
    return {
        **params.model_dump(mode="json"),
        "protocol": protocol_snapshot,
        "evidence": [_evidence_snapshot(item) for item in evidence],
    }


def _protocol_improvement_ai_context(
    *,
    context: TaskContext,
    protocol: Protocol,
    version: ProtocolVersion,
    evidence: list[ResearchEvidence],
    instruction: str,
) -> dict[str, Any]:
    return {
        "task": {
            "id": str(context.task.id),
            "goal": context.task.goal,
            "success_criteria": context.task.success_criteria,
            "stop_conditions": context.task.stop_conditions,
        },
        "protocol": {
            **_protocol_improvement_snapshot(protocol, version),
            "metadata": version.meta_data,
            "aimd": version.aimd,
            "json_schema": version.json_schema,
        },
        "evidence": [_evidence_snapshot(item) for item in evidence],
        "instruction": instruction,
    }


def _verify_protocol_improvement_generation(
    params: ProtocolImprovementDraft,
    *,
    current_user: User,
    context_digest: str,
) -> AiraProtocolImprovementGeneration | None:
    generation = params.aira_generation
    receipt = params.aira_receipt
    if generation is None or receipt is None:
        return None
    try:
        verify_generation_receipt(
            receipt,
            generation,
            user_id=current_user.id,
            task_id=params.task_id,
            protocol_id=params.protocol_id,
            context_digest=context_digest,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return generation


async def _protocol_improvement_payload(
    db_session: DBSession,
    proposal: ProtocolImprovementProposal,
) -> dict[str, Any]:
    protocol = await db_session.get(Protocol, proposal.protocol_id)
    links = list(
        (
            await db_session.scalars(
                select(ProtocolImprovementEvidence)
                .where(ProtocolImprovementEvidence.proposal_id == proposal.id)
                .order_by(ProtocolImprovementEvidence.created_at)
            )
        ).all()
    )
    return {
        **proposal.as_dict(),
        "protocol": (
            {
                "id": str(protocol.id),
                "uid": protocol.uid,
                "name": protocol.name,
                "base_protocol_version": proposal.base_protocol_version,
            }
            if protocol is not None
            else None
        ),
        "evidence": [link.as_dict() for link in links],
    }


def _claim_command(params: ClaimDraft | ClaimRevisionDraft) -> dict[str, Any]:
    excluded = {"expected_revision", "change_summary"}
    return params.model_dump(mode="json", exclude=excluded)


def _claim_ai_context(
    *,
    context: TaskContext,
    evidence: list[ResearchEvidence],
    instruction: str,
) -> dict[str, Any]:
    return {
        "task": {
            "id": str(context.task.id),
            "title": context.task.title,
            "goal": context.task.goal,
            "success_criteria": context.task.success_criteria,
            "stop_conditions": context.task.stop_conditions,
        },
        "evidence": [_evidence_snapshot(item) for item in evidence],
        "instruction": instruction,
    }


def _verify_claim_generation(
    params: ClaimDraft,
    *,
    current_user: User,
    context_digest: str,
) -> AiraClaimGeneration | None:
    generation = params.aira_generation
    receipt = params.aira_receipt
    if generation is None or receipt is None:
        return None
    try:
        verify_claim_generation_receipt(
            receipt,
            generation,
            user_id=current_user.id,
            task_id=params.task_id,
            context_digest=context_digest,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return generation


def _claim_snapshot(
    claim: ResearchClaim, relations: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "statement": claim.statement,
        "confidence": float(claim.confidence) if claim.confidence is not None else None,
        "uncertainty": claim.uncertainty,
        "state": claim.state,
        "generated_by": claim.generated_by,
        "generation_id": str(claim.generation_id) if claim.generation_id else None,
        "generation_model": claim.generation_model,
        "generation_snapshot": claim.generation_snapshot,
        "generation_receipt_digest": claim.generation_receipt_digest,
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
        raise HTTPException(
            status_code=409, detail="Invalid DataAsset status transition"
        )
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
    command, context, _action = await _validated_evidence_command(
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
    command, context, action = await _validated_evidence_command(
        db_session,
        current_user,
        draft,
        lock_action_output=True,
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
    action_output_snapshot = None
    if draft.artifact_type == "action_output":
        if action is None:
            raise HTTPException(status_code=404, detail="Research Action not found")
        action_output_snapshot = await _materialize_action_output_snapshot(
            db_session,
            context=context,
            action=action,
            expected_digest=command["artifact_version"],
            current_user=current_user,
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
    if action_output_snapshot is not None:
        await emit_research_event(
            db_session,
            task_id=context.task.id,
            run_id=draft.run_id,
            action_id=action.id,
            kind="action_output.snapshotted",
            actor_user_id=current_user.id,
            payload={
                "snapshot_id": str(action_output_snapshot.id),
                "digest": action_output_snapshot.digest,
            },
            idempotency_key=(f"action-output:{action_output_snapshot.id}:snapshotted"),
        )
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
    if (
        evidence.artifact_type == "action_output"
        and params.quality_state == EvidenceQuality.VALIDATED.value
    ):
        await _validate_evidence_artifact(
            db_session,
            current_user,
            context,
            artifact_type="action_output",
            artifact_id=evidence.artifact_id,
            artifact_version=evidence.artifact_version,
        )
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


@router.post("/claims/aira-draft")
async def draft_claim_with_aira(
    params: AiraClaimDraftRequest,
    current_user: CurrentUser,
    db_session: DBSession,
):
    if not config.effective_ai_enabled:
        raise HTTPException(status_code=503, detail="Aira is not available")
    context = await _task_context(
        db_session, current_user, params.task_id, "research.run"
    )
    evidence = await _validated_claim_evidence(
        db_session, current_user, context, params.evidence_ids
    )
    ai_context = _claim_ai_context(
        context=context,
        evidence=evidence,
        instruction=params.instruction,
    )
    context_digest = canonical_digest(ai_context)
    model_name = context.task.ai_model or config.CHAT_MODEL_ACCURATE
    usage_context = create_usage_context(
        feature="research.claim.draft",
        user_id=current_user.id,
        lab_id=context.lab.id,
        project_id=context.project.id,
        attributes={
            "task_id": str(context.task.id),
            "evidence_count": len(evidence),
        },
    )
    # Model latency must not hold database locks or an open transaction.
    await db_session.commit()
    output = await generate_claim(
        context=ai_context,
        instruction=params.instruction,
        evidence_ids=params.evidence_ids,
        model_name=model_name,
        usage_context=usage_context,
    )

    current_context = await _task_context(
        db_session, current_user, params.task_id, "research.run"
    )
    current_evidence = await _validated_claim_evidence(
        db_session,
        current_user,
        current_context,
        params.evidence_ids,
        with_for_update=True,
    )
    current_ai_context = _claim_ai_context(
        context=current_context,
        evidence=current_evidence,
        instruction=params.instruction,
    )
    if canonical_digest(current_ai_context) != context_digest:
        raise HTTPException(
            status_code=409,
            detail="Research context changed while Aira prepared the Claim",
        )
    generation = create_claim_generation(
        output=output,
        model_name=model_name,
        context_digest=context_digest,
        instruction=params.instruction,
        source_snapshot={
            "task": ai_context["task"],
            "evidence": [
                {
                    "id": str(item.id),
                    "snapshot_digest": canonical_digest(_evidence_snapshot(item)),
                }
                for item in current_evidence
            ],
        },
    )
    receipt = sign_claim_generation_receipt(
        generation,
        user_id=current_user.id,
        task_id=params.task_id,
    )
    await db_session.commit()
    return {
        "task_id": str(params.task_id),
        "statement": output.statement,
        "confidence": output.confidence,
        "uncertainty": output.uncertainty,
        "evidence": [item.model_dump(mode="json") for item in output.evidence],
        "aira_generation": generation.model_dump(mode="json"),
        "aira_receipt": receipt,
    }


@router.post("/claims/preview")
async def preview_claim(
    params: ClaimDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    context = await _task_context(
        db_session, current_user, params.task_id, "research.run"
    )
    evidence_ids = [item.evidence_id for item in params.evidence]
    if params.aira_generation:
        evidence = await _validated_claim_evidence(
            db_session, current_user, context, evidence_ids
        )
        generation = _verify_claim_generation(
            params,
            current_user=current_user,
            context_digest=canonical_digest(
                _claim_ai_context(
                    context=context,
                    evidence=evidence,
                    instruction=params.aira_generation.instruction,
                )
            ),
        )
    else:
        await _evidence_for_task(db_session, context.task.id, params.evidence)
        generation = None
    command = _claim_command(params)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": {
            "task_id": str(context.task.id),
            "task_title": context.task.title,
        },
        "effect": {
            "state": (
                ClaimState.SUGGESTED.value if generation else ClaimState.DRAFT.value
            ),
            "generated_by": "aira_assisted" if generation else "human",
            "evidence_count": len(params.evidence),
            "requires_human_review": True,
        },
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
    evidence_ids = [item.evidence_id for item in draft.evidence]
    if draft.aira_generation:
        evidence = await _validated_claim_evidence(
            db_session,
            current_user,
            context,
            evidence_ids,
            with_for_update=True,
        )
        generation = _verify_claim_generation(
            draft,
            current_user=current_user,
            context_digest=canonical_digest(
                _claim_ai_context(
                    context=context,
                    evidence=evidence,
                    instruction=draft.aira_generation.instruction,
                )
            ),
        )
    else:
        await _evidence_for_task(db_session, context.task.id, draft.evidence)
        generation = None
    command = _claim_command(draft)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(status_code=409, detail="Claim preview has changed")
    claim = ResearchClaim(
        task_id=context.task.id,
        statement=draft.statement,
        state=(ClaimState.SUGGESTED.value if generation else ClaimState.DRAFT.value),
        confidence=draft.confidence,
        uncertainty=draft.uncertainty,
        generated_by="aira_assisted" if generation else "human",
        generation_id=generation.id if generation else None,
        generation_model=generation.model if generation else None,
        generation_snapshot=generation.model_dump(mode="json") if generation else None,
        generation_receipt_digest=(
            canonical_digest(draft.aira_receipt) if generation else None
        ),
        created_by_user_id=current_user.id,
    )
    db_session.add(claim)
    try:
        await db_session.flush()
    except IntegrityError as error:
        await db_session.rollback()
        if generation is None:
            raise
        raise HTTPException(
            status_code=409,
            detail="This Aira Claim draft has already been confirmed",
        ) from error
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


@router.post("/knowledge-suggestions/preview")
async def preview_knowledge_suggestion(
    params: KnowledgeSuggestionDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    context = await _task_context(
        db_session, current_user, params.task_id, "research.read"
    )
    await resolve_scope(
        db_session,
        current_user,
        scope_type=OwnerScope.PROJECT,
        lab_id=context.lab.id,
        project_id=context.project.id,
        capability="knowledge.create",
    )
    evidence = await _knowledge_suggestion_evidence(
        db_session, current_user, context, params.evidence_ids
    )
    command = _knowledge_suggestion_command(params, evidence)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": {
            "task_id": str(context.task.id),
            "task_title": context.task.title,
            "project_id": str(context.project.id),
            "project_name": context.project.name,
        },
        "effect": {
            "state": KnowledgeState.SUGGESTED.value,
            "visibility": Visibility.PROJECT.value,
            "evidence_count": len(evidence),
            "requires_review": True,
        },
    }


@router.post("/knowledge-suggestions")
async def create_knowledge_suggestion(
    params: KnowledgeSuggestionCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    draft = KnowledgeSuggestionDraft.model_validate(
        params.model_dump(exclude={"preview_digest"})
    )
    context = await _task_context(
        db_session, current_user, draft.task_id, "research.read"
    )
    scope = await resolve_scope(
        db_session,
        current_user,
        scope_type=OwnerScope.PROJECT,
        lab_id=context.lab.id,
        project_id=context.project.id,
        capability="knowledge.create",
    )
    evidence = await _knowledge_suggestion_evidence(
        db_session,
        current_user,
        context,
        draft.evidence_ids,
        with_for_update=True,
    )
    command = _knowledge_suggestion_command(draft, evidence)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(
            status_code=409, detail="Knowledge suggestion preview has changed"
        )
    item = KnowledgeItem(
        **scope.model_values(),
        visibility=Visibility.PROJECT.value,
        kind=draft.kind.value,
        state=KnowledgeState.SUGGESTED.value,
        title=draft.title,
        body=draft.body,
        tags=draft.tags,
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
            change_summary="Suggested from validated Research Evidence",
            created_by_user_id=current_user.id,
        )
    )
    links: list[dict[str, Any]] = []
    for source in evidence:
        snapshot = _evidence_snapshot(source)
        db_session.add(
            KnowledgeEvidenceLink(
                knowledge_item_id=item.id,
                knowledge_revision=1,
                evidence_id=source.id,
                source_snapshot=snapshot,
                created_by_user_id=current_user.id,
            )
        )
        links.append({"evidence_id": str(source.id), "source_snapshot": snapshot})
    db_session.add(
        ResearchArtifactLink(
            task_id=context.task.id,
            artifact_type="knowledge",
            artifact_id=str(item.id),
            artifact_version="1",
            relation="derived",
            link_metadata={"kind": item.kind, "title": item.title},
        )
    )
    await emit_research_event(
        db_session,
        task_id=context.task.id,
        kind="knowledge.suggested",
        actor_user_id=current_user.id,
        payload={
            "knowledge_item_id": str(item.id),
            "revision": 1,
            "evidence_ids": [str(source.id) for source in evidence],
        },
        idempotency_key=f"knowledge:{item.id}:suggested:r1",
    )
    await db_session.commit()
    return {**item.as_dict(), "evidence": links}


@router.post("/protocol-improvements/aira-draft")
async def draft_protocol_improvement_with_aira(
    params: AiraProtocolImprovementDraftRequest,
    current_user: CurrentUser,
    db_session: DBSession,
):
    if not config.effective_ai_enabled:
        raise HTTPException(status_code=503, detail="Aira is not available")
    context, protocol, version = await _protocol_improvement_context(
        db_session,
        current_user,
        params.task_id,
        params.protocol_id,
    )
    evidence = await _knowledge_suggestion_evidence(
        db_session, current_user, context, params.evidence_ids
    )
    ai_context = _protocol_improvement_ai_context(
        context=context,
        protocol=protocol,
        version=version,
        evidence=evidence,
        instruction=params.instruction,
    )
    context_digest = canonical_digest(ai_context)
    model_name = context.task.ai_model or config.CHAT_MODEL_ACCURATE
    usage_context = create_usage_context(
        feature="research.protocol_improvement.draft",
        user_id=current_user.id,
        lab_id=context.lab.id,
        project_id=context.project.id,
        attributes={
            "task_id": str(context.task.id),
            "protocol_id": str(protocol.id),
            "base_protocol_version": version.version,
        },
    )
    # Never hold a database transaction open while waiting for a model provider.
    await db_session.commit()
    output = await generate_protocol_improvement(
        context=ai_context,
        instruction=params.instruction,
        model_name=model_name,
        usage_context=usage_context,
    )

    (
        current_context,
        current_protocol,
        current_version,
    ) = await _protocol_improvement_context(
        db_session,
        current_user,
        params.task_id,
        params.protocol_id,
    )
    current_evidence = await _knowledge_suggestion_evidence(
        db_session,
        current_user,
        current_context,
        params.evidence_ids,
        with_for_update=True,
    )
    current_ai_context = _protocol_improvement_ai_context(
        context=current_context,
        protocol=current_protocol,
        version=current_version,
        evidence=current_evidence,
        instruction=params.instruction,
    )
    if canonical_digest(current_ai_context) != context_digest:
        raise HTTPException(
            status_code=409,
            detail="Research context changed while Aira prepared the draft",
        )
    generation = create_generation(
        output=output,
        model_name=model_name,
        context_digest=context_digest,
        instruction=params.instruction,
        source_snapshot={
            "task": ai_context["task"],
            "protocol": _protocol_improvement_snapshot(
                current_protocol, current_version
            ),
            "evidence": [
                {
                    "id": str(item.id),
                    "snapshot_digest": canonical_digest(_evidence_snapshot(item)),
                }
                for item in current_evidence
            ],
        },
    )
    receipt = sign_generation_receipt(
        generation,
        user_id=current_user.id,
        task_id=params.task_id,
        protocol_id=params.protocol_id,
    )
    await db_session.commit()
    return {
        "task_id": str(params.task_id),
        "protocol_id": str(params.protocol_id),
        "title": output.title,
        "rationale": output.rationale,
        "proposed_changes": output.proposed_changes,
        "evidence_ids": [str(item) for item in params.evidence_ids],
        "aira_generation": generation.model_dump(mode="json"),
        "aira_receipt": receipt,
    }


@router.post("/protocol-improvements/preview")
async def preview_protocol_improvement(
    params: ProtocolImprovementDraft,
    current_user: CurrentUser,
    db_session: DBSession,
):
    context, protocol, version = await _protocol_improvement_context(
        db_session,
        current_user,
        params.task_id,
        params.protocol_id,
    )
    evidence = await _knowledge_suggestion_evidence(
        db_session, current_user, context, params.evidence_ids
    )
    protocol_snapshot = _protocol_improvement_snapshot(protocol, version)
    generation = _verify_protocol_improvement_generation(
        params,
        current_user=current_user,
        context_digest=canonical_digest(
            _protocol_improvement_ai_context(
                context=context,
                protocol=protocol,
                version=version,
                evidence=evidence,
                instruction=params.aira_generation.instruction
                if params.aira_generation
                else "",
            )
        ),
    )
    command = _protocol_improvement_command(params, protocol_snapshot, evidence)
    return {
        "preview_digest": canonical_digest(command),
        "command": command,
        "destination": {
            "task_id": str(context.task.id),
            "task_title": context.task.title,
            "project_id": str(context.project.id),
            "project_name": context.project.name,
        },
        "effect": {
            "state": ProtocolImprovementState.SUGGESTED.value,
            "protocol_id": str(protocol.id),
            "base_protocol_version": version.version,
            "evidence_count": len(evidence),
            "requires_expert_review": True,
            "changes_published_protocol": False,
            "generated_by": "aira_assisted" if generation else "human",
        },
    }


@router.post("/protocol-improvements")
async def create_protocol_improvement(
    params: ProtocolImprovementCreate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    draft = ProtocolImprovementDraft.model_validate(
        params.model_dump(exclude={"preview_digest"})
    )
    context, protocol, version = await _protocol_improvement_context(
        db_session,
        current_user,
        draft.task_id,
        draft.protocol_id,
    )
    evidence = await _knowledge_suggestion_evidence(
        db_session,
        current_user,
        context,
        draft.evidence_ids,
        with_for_update=True,
    )
    protocol_snapshot = _protocol_improvement_snapshot(protocol, version)
    generation = _verify_protocol_improvement_generation(
        draft,
        current_user=current_user,
        context_digest=canonical_digest(
            _protocol_improvement_ai_context(
                context=context,
                protocol=protocol,
                version=version,
                evidence=evidence,
                instruction=draft.aira_generation.instruction
                if draft.aira_generation
                else "",
            )
        ),
    )
    command = _protocol_improvement_command(draft, protocol_snapshot, evidence)
    if canonical_digest(command) != params.preview_digest:
        raise HTTPException(
            status_code=409, detail="Protocol improvement preview has changed"
        )
    proposal = ProtocolImprovementProposal(
        task_id=context.task.id,
        protocol_id=protocol.id,
        base_protocol_version_id=version.id,
        base_protocol_version=version.version,
        title=draft.title,
        rationale=draft.rationale,
        proposed_changes=draft.proposed_changes,
        state=ProtocolImprovementState.SUGGESTED.value,
        generated_by="aira_assisted" if generation else "human",
        generation_id=generation.id if generation else None,
        generation_model=generation.model if generation else None,
        generation_snapshot=generation.model_dump(mode="json") if generation else None,
        generation_receipt_digest=(
            canonical_digest(draft.aira_receipt) if generation else None
        ),
        created_by_user_id=current_user.id,
    )
    db_session.add(proposal)
    try:
        await db_session.flush()
    except IntegrityError as error:
        await db_session.rollback()
        if generation is None:
            raise
        raise HTTPException(
            status_code=409,
            detail="This Aira draft has already been confirmed",
        ) from error
    for source in evidence:
        db_session.add(
            ProtocolImprovementEvidence(
                proposal_id=proposal.id,
                evidence_id=source.id,
                source_snapshot=_evidence_snapshot(source),
                created_by_user_id=current_user.id,
            )
        )
    db_session.add(
        ResearchArtifactLink(
            task_id=context.task.id,
            artifact_type="protocol_improvement",
            artifact_id=str(proposal.id),
            artifact_version="1",
            relation="suggested",
            link_metadata={
                "protocol_id": str(protocol.id),
                "base_protocol_version": version.version,
                "title": proposal.title,
            },
        )
    )
    await emit_research_event(
        db_session,
        task_id=context.task.id,
        kind="protocol_improvement.suggested",
        actor_user_id=current_user.id,
        payload={
            "proposal_id": str(proposal.id),
            "protocol_id": str(protocol.id),
            "base_protocol_version": version.version,
            "evidence_ids": [str(item.id) for item in evidence],
            "generated_by": proposal.generated_by,
        },
        idempotency_key=f"protocol-improvement:{proposal.id}:suggested:r1",
    )
    await db_session.commit()
    return await _protocol_improvement_payload(db_session, proposal)


@router.get("/protocol-improvements/{proposal_id}")
async def get_protocol_improvement(
    proposal_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    proposal = await db_session.get(ProtocolImprovementProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Protocol improvement not found")
    await _task_context(db_session, current_user, proposal.task_id, "research.read")
    return await _protocol_improvement_payload(db_session, proposal)


@router.post("/protocol-improvements/{proposal_id}/review")
async def review_protocol_improvement(
    proposal_id: UUID,
    params: ProtocolImprovementReview,
    current_user: CurrentUser,
    db_session: DBSession,
):
    proposal = await db_session.scalar(
        select(ProtocolImprovementProposal)
        .where(ProtocolImprovementProposal.id == proposal_id)
        .with_for_update()
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="Protocol improvement not found")
    context = await _task_context(
        db_session, current_user, proposal.task_id, "research.approve"
    )
    protocol = await db_session.get(Protocol, proposal.protocol_id)
    if protocol is None or protocol.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Protocol not found")
    await check_user_permission(
        db_session,
        project=context.project,
        user=current_user,
        action="update_protocol",
        protocol=protocol,
    )
    if protocol.latest_version != proposal.base_protocol_version:
        raise HTTPException(
            status_code=409,
            detail=(
                "Protocol changed after this improvement was proposed; "
                "create a new proposal against the latest version"
            ),
        )
    if (
        proposal.revision != params.expected_revision
        or proposal.state != params.expected_state.value
    ):
        raise HTTPException(
            status_code=409, detail="Protocol improvement review state has changed"
        )
    if proposal.state != ProtocolImprovementState.SUGGESTED.value:
        raise HTTPException(status_code=409, detail="Protocol improvement is final")
    proposal.state = params.state
    proposal.revision += 1
    proposal.reviewed_by_user_id = current_user.id
    proposal.reviewed_at = utcnow()
    await emit_research_event(
        db_session,
        task_id=context.task.id,
        kind="protocol_improvement.reviewed",
        actor_user_id=current_user.id,
        payload={
            "proposal_id": str(proposal.id),
            "state": proposal.state,
            "revision": proposal.revision,
        },
        idempotency_key=(
            f"protocol-improvement:{proposal.id}:review:{proposal.state}:"
            f"r{proposal.revision}"
        ),
    )
    await db_session.commit()
    return await _protocol_improvement_payload(db_session, proposal)
