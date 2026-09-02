"""Read models for traceable scientific assets attached to Research Tasks."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_asset import (
    DataAsset,
    DataAssetVersion,
    ResearchClaim,
    ResearchClaimEvidence,
    ResearchEvidence,
)


def _confidence(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


async def research_asset_bundle(
    db_session: AsyncSession,
    *,
    task_id: UUID,
) -> dict[str, list[dict[str, Any]]]:
    """Return stable, ordered Task results without exposing private file internals."""

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
    for version in versions:
        versions_by_asset.setdefault(version.data_asset_id, []).append(
            version.as_dict()
        )

    evidence = list(
        (
            await db_session.scalars(
                select(ResearchEvidence)
                .where(ResearchEvidence.task_id == task_id)
                .order_by(ResearchEvidence.created_at, ResearchEvidence.id)
            )
        ).all()
    )
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

    return {
        "data_assets": [
            {
                **item.as_dict(),
                "versions": versions_by_asset.get(item.id, []),
            }
            for item in assets
        ],
        "evidence": [item.as_dict() for item in evidence],
        "claims": [
            {
                **item.as_dict(),
                "confidence": _confidence(item.confidence),
                "evidence": relations_by_claim.get(item.id, []),
            }
            for item in claims
        ],
    }
