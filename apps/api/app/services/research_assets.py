"""Read models for traceable scientific assets attached to Research Tasks."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeItem
from app.models.protocol import Protocol
from app.models.research import ResearchTask
from app.models.research_asset import (
    DataAsset,
    DataAssetVersion,
    KnowledgeEvidenceLink,
    ProtocolImprovementEvidence,
    ProtocolImprovementProposal,
    ResearchActionOutputSnapshot,
    ResearchClaim,
    ResearchClaimEvidence,
    ResearchEvidence,
)
from app.services.research_action_outputs import (
    ResearchActionOutputError,
    action_output_snapshot_data,
)
from app.services.research_asset_visibility import (
    HIDDEN_SOURCE_STATUSES,
    evidence_source_readable,
    require_artifact_source_readable,
    require_protocol_improvement_readable,
    visible_knowledge_evidence_links,
)


def _confidence(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


async def research_asset_bundle(
    db_session: AsyncSession,
    *,
    task_id: UUID,
    current_user=None,
) -> dict[str, list[dict[str, Any]]]:
    """Read exact assets; public callers must supply their current reader.

    Internal result assembly may omit the reader after authorizing its complete
    context; filtered public views must never be sealed as complete results.
    """

    assets = list(
        (
            await db_session.scalars(
                select(DataAsset)
                .where(DataAsset.task_id == task_id, DataAsset.archived_at.is_(None))
                .order_by(DataAsset.created_at, DataAsset.id)
            )
        ).all()
    )
    asset_ids = [item.id for item in assets]
    versions = (
        list(
            (
                await db_session.scalars(
                    select(DataAssetVersion)
                    .where(DataAssetVersion.data_asset_id.in_(asset_ids))
                    .order_by(DataAssetVersion.data_asset_id, DataAssetVersion.version)
                )
            ).all()
        )
        if asset_ids
        else []
    )
    versions_by_asset: dict[UUID, list[dict[str, Any]]] = {}
    task = await db_session.get(ResearchTask, task_id) if current_user else None
    for version in versions:
        if current_user:
            try:
                if task is None:
                    raise HTTPException(403, "Research Task not found")
                await require_artifact_source_readable(
                    db_session,
                    task=task,
                    user=current_user,
                    artifact_type="data_asset",
                    artifact_id=version.data_asset_id,
                    artifact_version=str(version.version),
                )
            except HTTPException as exc:
                if exc.status_code in HIDDEN_SOURCE_STATUSES:
                    continue
                raise
        versions_by_asset.setdefault(version.data_asset_id, []).append(
            version.as_dict()
        )
    if current_user:
        assets = [item for item in assets if item.id in versions_by_asset]

    evidence = list(
        (
            await db_session.scalars(
                select(ResearchEvidence)
                .where(ResearchEvidence.task_id == task_id)
                .order_by(ResearchEvidence.created_at, ResearchEvidence.id)
            )
        ).all()
    )
    if current_user:
        evidence = [
            item
            for item in evidence
            if await evidence_source_readable(db_session, item, current_user)
        ]
    visible_evidence_ids = {item.id for item in evidence}
    action_output_ids = [
        UUID(item.artifact_id)
        for item in evidence
        if item.artifact_type == "action_output"
    ]
    action_output_snapshots = (
        list(
            (
                await db_session.scalars(
                    select(ResearchActionOutputSnapshot).where(
                        ResearchActionOutputSnapshot.action_id.in_(action_output_ids)
                    )
                )
            ).all()
        )
        if action_output_ids
        else []
    )
    action_output_by_action_id = {
        item.action_id: action_output_snapshot_data(item)
        for item in action_output_snapshots
    }
    if set(action_output_ids) != set(action_output_by_action_id):
        raise ResearchActionOutputError(
            "Action output Evidence is missing its immutable source snapshot"
        )
    publication_evidence = [
        item for item in evidence if item.artifact_type == "analysis_publication"
    ]
    publication_snapshots: dict[UUID, dict[str, Any]] = {}
    if publication_evidence:
        from app.models.analysis_publication import AnalysisEvidencePublication
        from app.services.analysis_publications import publication_payload

        publications = list(
            (
                await db_session.scalars(
                    select(AnalysisEvidencePublication).where(
                        AnalysisEvidencePublication.id.in_(
                            [UUID(item.artifact_id) for item in publication_evidence]
                        )
                    )
                )
            ).all()
        )
        by_id = {row.id: row for row in publications}
        for item in publication_evidence:
            publication = by_id.get(UUID(item.artifact_id))
            if (
                publication is None
                or publication.task_id != task_id
                or publication.evidence_id != item.id
                or publication.digest != item.artifact_version
            ):
                raise HTTPException(
                    409, "Analysis Evidence is missing its exact publication snapshot"
                )
            # The payload verifies its sealed digest even for internal assembly;
            # live source access is checked before public views or result export.
            publication_snapshots[item.id] = publication_payload(publication)
    claims = list(
        (
            await db_session.scalars(
                select(ResearchClaim)
                .where(ResearchClaim.task_id == task_id)
                .order_by(ResearchClaim.created_at, ResearchClaim.id)
            )
        ).all()
    )
    claim_ids = [item.id for item in claims]
    relations = (
        list(
            (
                await db_session.scalars(
                    select(ResearchClaimEvidence)
                    .where(ResearchClaimEvidence.claim_id.in_(claim_ids))
                    .order_by(ResearchClaimEvidence.created_at)
                )
            ).all()
        )
        if claim_ids
        else []
    )
    relations_by_claim: dict[UUID, list[dict[str, Any]]] = {}
    for relation in relations:
        relations_by_claim.setdefault(relation.claim_id, []).append(relation.as_dict())
    if current_user:
        hidden_claims = {
            relation.claim_id
            for relation in relations
            if relation.evidence_id not in visible_evidence_ids
        }
        claims = [item for item in claims if item.id not in hidden_claims]

    knowledge_links = list(
        (
            await db_session.scalars(
                select(KnowledgeEvidenceLink)
                .join(
                    ResearchEvidence,
                    ResearchEvidence.id == KnowledgeEvidenceLink.evidence_id,
                )
                .where(ResearchEvidence.task_id == task_id)
                .order_by(KnowledgeEvidenceLink.created_at, KnowledgeEvidenceLink.id)
            )
        ).all()
    )
    knowledge_item_ids = list(
        dict.fromkeys(link.knowledge_item_id for link in knowledge_links)
    )
    knowledge_items = (
        list(
            (
                await db_session.scalars(
                    select(KnowledgeItem).where(
                        KnowledgeItem.id.in_(knowledge_item_ids)
                    )
                )
            ).all()
        )
        if knowledge_item_ids
        else []
    )
    knowledge_by_id = {item.id: item for item in knowledge_items}
    if current_user:
        from app.services.knowledge import authorize_knowledge_item

        for item in knowledge_items:
            try:
                await authorize_knowledge_item(db_session, current_user, item)
            except HTTPException as exc:
                if exc.status_code in HIDDEN_SOURCE_STATUSES:
                    knowledge_by_id.pop(item.id, None)
                    continue
                raise
        knowledge_links = await visible_knowledge_evidence_links(
            db_session, knowledge_links, current_user
        )
    links_by_knowledge: dict[UUID, list[dict[str, Any]]] = {}
    for link in knowledge_links:
        links_by_knowledge.setdefault(link.knowledge_item_id, []).append(link.as_dict())

    improvement_proposals = list(
        (
            await db_session.scalars(
                select(ProtocolImprovementProposal)
                .where(ProtocolImprovementProposal.task_id == task_id)
                .order_by(
                    ProtocolImprovementProposal.created_at,
                    ProtocolImprovementProposal.id,
                )
            )
        ).all()
    )
    proposal_ids = [item.id for item in improvement_proposals]
    protocol_ids = list(
        dict.fromkeys(item.protocol_id for item in improvement_proposals)
    )
    protocols = (
        list(
            (
                await db_session.scalars(
                    select(Protocol).where(Protocol.id.in_(protocol_ids))
                )
            ).all()
        )
        if protocol_ids
        else []
    )
    protocol_by_id = {item.id: item for item in protocols}
    improvement_links = (
        list(
            (
                await db_session.scalars(
                    select(ProtocolImprovementEvidence)
                    .where(ProtocolImprovementEvidence.proposal_id.in_(proposal_ids))
                    .order_by(ProtocolImprovementEvidence.created_at)
                )
            ).all()
        )
        if proposal_ids
        else []
    )
    links_by_proposal: dict[UUID, list[dict[str, Any]]] = {}
    for link in improvement_links:
        links_by_proposal.setdefault(link.proposal_id, []).append(link.as_dict())
    if current_user:
        hidden_proposals = {
            link.proposal_id
            for link in improvement_links
            if link.evidence_id not in visible_evidence_ids
        }
        improvement_proposals = [
            item for item in improvement_proposals if item.id not in hidden_proposals
        ]
        allowed_proposals = []
        for item in improvement_proposals:
            try:
                await require_protocol_improvement_readable(
                    db_session, item, current_user
                )
            except HTTPException as exc:
                if exc.status_code in HIDDEN_SOURCE_STATUSES:
                    continue
                raise
            allowed_proposals.append(item)
        improvement_proposals = allowed_proposals

    return {
        "data_assets": [
            {
                **item.as_dict(),
                "versions": versions_by_asset.get(item.id, []),
            }
            for item in assets
        ],
        "evidence": [
            {
                **item.as_dict(),
                "artifact_snapshot": (
                    action_output_by_action_id.get(UUID(item.artifact_id))
                    if item.artifact_type == "action_output"
                    else publication_snapshots.get(item.id)
                ),
            }
            for item in evidence
        ],
        "claims": [
            {
                **item.as_dict(),
                "confidence": _confidence(item.confidence),
                "evidence": relations_by_claim.get(item.id, []),
            }
            for item in claims
        ],
        "knowledge_items": [
            {
                **knowledge_by_id[item_id].as_dict(),
                "evidence": links_by_knowledge.get(item_id, []),
            }
            for item_id in knowledge_item_ids
            if item_id in knowledge_by_id
        ],
        "protocol_improvements": [
            {
                **item.as_dict(),
                "protocol": (
                    {
                        "id": str(protocol_by_id[item.protocol_id].id),
                        "uid": protocol_by_id[item.protocol_id].uid,
                        "name": protocol_by_id[item.protocol_id].name,
                        "base_protocol_version": item.base_protocol_version,
                    }
                    if item.protocol_id in protocol_by_id
                    else None
                ),
                "evidence": links_by_proposal.get(item.id, []),
            }
            for item in improvement_proposals
        ],
    }
