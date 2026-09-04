"""Immutable provenance snapshots for typed Research Action outputs."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from fastapi.encoders import jsonable_encoder

from app.models.research import ResearchAction, ResearchActionStatus
from app.models.research_asset import ResearchActionOutputSnapshot


class ResearchActionOutputError(ValueError):
    pass


def action_output_payload(action: ResearchAction, *, task_id: UUID) -> dict[str, Any]:
    """Build the exact source payload eligible for scientific review."""

    if action.status != ResearchActionStatus.COMPLETED.value:
        raise ResearchActionOutputError(
            "Only a completed Research Action can become Evidence"
        )
    if not isinstance(action.output_data, dict) or not action.output_data:
        raise ResearchActionOutputError(
            "Completed Research Action does not contain a structured output"
        )
    return jsonable_encoder(
        {
            "schema": "airalogy.research-action-output.v1",
            "task_id": str(task_id),
            "run_id": str(action.run_id),
            "action_id": str(action.id),
            "action_revision": action.revision,
            "action_kind": action.kind,
            "output_data": action.output_data,
        }
    )


def action_output_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        jsonable_encoder(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def verify_action_output_snapshot(snapshot: ResearchActionOutputSnapshot) -> None:
    payload = {
        "schema": "airalogy.research-action-output.v1",
        "task_id": str(snapshot.task_id),
        "run_id": str(snapshot.run_id),
        "action_id": str(snapshot.action_id),
        "action_revision": snapshot.action_revision,
        "action_kind": snapshot.action_kind,
        "output_data": snapshot.output_data,
    }
    if action_output_digest(payload) != snapshot.digest:
        raise ResearchActionOutputError(
            "Research Action output snapshot digest does not match its content"
        )


def action_output_snapshot_data(
    snapshot: ResearchActionOutputSnapshot,
) -> dict[str, Any]:
    verify_action_output_snapshot(snapshot)
    return {
        "schema": "airalogy.research-action-output.v1",
        "id": str(snapshot.id),
        "task_id": str(snapshot.task_id),
        "run_id": str(snapshot.run_id),
        "action_id": str(snapshot.action_id),
        "action_revision": snapshot.action_revision,
        "action_kind": snapshot.action_kind,
        "output_data": jsonable_encoder(snapshot.output_data),
        "digest": snapshot.digest,
        "created_by_user_id": (
            str(snapshot.created_by_user_id)
            if snapshot.created_by_user_id is not None
            else None
        ),
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
    }
