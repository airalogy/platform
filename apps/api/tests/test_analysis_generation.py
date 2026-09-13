"""Cycle and engine boundaries for source-authorized analysis provenance."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services import analysis_generation
from app.services.analysis_compute_contracts import AnalysisComputeRecipe
from app.services.analysis_engine import AnalysisRecipe, canonical_digest


def seal(value):
    return {**value, "digest": canonical_digest(value)}


def test_interpretation_reference_is_rejected_before_recursive_run_authorization(
    monkeypatch,
):
    user = SimpleNamespace(id=uuid4())
    request_id = uuid4()
    db = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                created_by_user_id=user.id,
                kind="interpretation",
            )
        )
    )
    traverse = AsyncMock(
        side_effect=AssertionError("Must not enter a report-to-interpretation cycle")
    )
    monkeypatch.setattr(analysis_generation, "owned_ai_request", traverse)
    with pytest.raises(HTTPException) as invalid:
        asyncio.run(
            analysis_generation.authorize_ai_provenance(
                db,
                seal({"request_id": str(request_id)}),
                user,
            )
        )
    assert invalid.value.status_code == 409
    assert traverse.await_count == 0


@pytest.mark.parametrize("mode,is_compute", [("builtin", True), ("compute", False)])
def test_inherited_provenance_cannot_cross_analysis_engines(mode, is_compute):
    recipe = (
        AnalysisComputeRecipe(
            environment_revision_id=uuid4(),
            language="python",
            source_code="print('draft')",
        )
        if is_compute
        else AnalysisRecipe(numeric_fields=["value"])
    )
    with pytest.raises(HTTPException) as mismatch:
        analysis_generation.inherited_provenance(
            seal({"generation": {"mode": mode}}), recipe
        )
    assert mismatch.value.status_code == 409
