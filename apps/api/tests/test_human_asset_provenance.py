"""The SQL provenance constraint requires SQL NULL, not a JSON null value."""

import pytest
from sqlalchemy.dialects.postgresql import dialect

from app.models.knowledge import KnowledgeItem
from app.models.research_asset import ProtocolImprovementProposal, ResearchClaim


@pytest.mark.parametrize("model", [KnowledgeItem, ResearchClaim, ProtocolImprovementProposal])
def test_human_authored_assets_bind_absent_generation_as_sql_null(model):
    column = model.__table__.c.generation_snapshot
    bind = column.type.bind_processor(dialect())
    assert bind(None) is None
    assert bind({"model": "test-model"}) == '{"model": "test-model"}'
