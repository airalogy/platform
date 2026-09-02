from importlib import import_module
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.main import app
from app.models.research_asset import (
    DataAsset,
    DataAssetVersion,
    KnowledgeEvidenceLink,
    ResearchClaim,
    ResearchClaimEvidence,
    ResearchClaimRevision,
    ResearchEvidence,
)
from app.routers.research_assets import (
    ClaimDraft,
    DataAssetDraft,
    EvidenceDraft,
    KnowledgeSuggestionDraft,
    _knowledge_suggestion_command,
)
from app.services.research_runtime import canonical_digest


def compile_table(model) -> str:
    return str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))


def test_data_assets_have_immutable_versions_and_one_real_source():
    asset_ddl = compile_table(DataAsset)
    version_ddl = compile_table(DataAssetVersion)

    assert "project_id" in asset_ddl
    assert "current_version" in asset_ddl
    assert "UNIQUE (data_asset_id, version)" in version_ddl
    assert "ck_data_asset_version_source" in version_ddl
    assert "research_file_id" in version_ddl
    assert "external_uri" in version_ddl


def test_evidence_is_task_scoped_and_deduplicated_by_artifact():
    ddl = compile_table(ResearchEvidence)

    assert "task_id" in ddl
    assert "artifact_type" in ddl
    assert "quality_state" in ddl
    assert "uq_research_evidence_artifact" in ddl


def test_claims_are_revisioned_and_link_to_evidence_with_semantics():
    claim_ddl = compile_table(ResearchClaim)
    revision_ddl = compile_table(ResearchClaimRevision)
    relation_ddl = compile_table(ResearchClaimEvidence)

    assert "confidence" in claim_ddl
    assert "uncertainty" in claim_ddl
    assert "UNIQUE (claim_id, revision)" in revision_ddl
    assert "relation" in relation_ddl
    assert "UNIQUE (claim_id, evidence_id)" in relation_ddl


def test_suggested_knowledge_pins_validated_evidence_provenance():
    ddl = compile_table(KnowledgeEvidenceLink)

    assert "knowledge_revision" in ddl
    assert "evidence_id" in ddl
    assert "source_snapshot" in ddl
    assert "uq_knowledge_evidence_lineage" in ddl
    assert "fk_knowledge_evidence_target_revision" in ddl

    migration = import_module("migrations.versions.0020_knowledge_evidence_lineage")
    assert migration.down_revision == "0019_knowledge_protocol_lineage"
    assert migration.TABLE_NAMES == ("knowledge_evidence_links",)


def test_research_asset_migration_follows_research_log():
    migration = import_module("migrations.versions.0014_research_assets")

    assert migration.down_revision == "0013_research_log"
    assert migration.TABLE_NAMES == (
        "data_assets",
        "data_asset_versions",
        "research_evidence",
        "research_claims",
        "research_claim_revisions",
        "research_claim_evidence",
    )


def test_data_asset_draft_requires_one_safe_source_and_has_stable_preview():
    task_id = uuid4()
    payload = {
        "task_id": task_id,
        "name": "  Processed measurements  ",
        "kind": "table",
        "external_uri": "https://data.example.edu/results.csv",
    }

    draft = DataAssetDraft(**payload)

    assert draft.name == "Processed measurements"
    assert canonical_digest(draft.model_dump(mode="json")) == canonical_digest(
        DataAssetDraft(**dict(reversed(payload.items()))).model_dump(mode="json")
    )
    with pytest.raises(ValidationError):
        DataAssetDraft(**{**payload, "research_file_id": uuid4()})
    with pytest.raises(ValidationError):
        DataAssetDraft(**{**payload, "external_uri": "file:///etc/passwd"})


def test_evidence_and_claim_inputs_are_task_scoped_and_deduplicate_relations():
    task_id = uuid4()
    evidence_id = uuid4()

    evidence = EvidenceDraft(
        task_id=task_id,
        kind="measurement",
        artifact_type="data_asset",
        artifact_id=str(uuid4()),
    )

    assert evidence.summary == ""
    with pytest.raises(ValidationError):
        ClaimDraft(
            task_id=task_id,
            statement="A reproducible effect was observed",
            evidence=[
                {"evidence_id": evidence_id},
                {"evidence_id": evidence_id, "relation": "context"},
            ],
        )


def test_knowledge_suggestion_requires_content_and_unique_evidence():
    task_id = uuid4()
    evidence_id = uuid4()
    draft = KnowledgeSuggestionDraft(
        task_id=task_id,
        title="  Reusable finding  ",
        body="  Validated measurements support this candidate finding.  ",
        kind="finding",
        tags=[" assay ", "assay", "validated"],
        evidence_ids=[evidence_id],
    )

    assert draft.title == "Reusable finding"
    assert draft.tags == ["assay", "validated"]
    with pytest.raises(ValidationError):
        KnowledgeSuggestionDraft(
            task_id=task_id,
            title="Duplicate sources",
            body="Must not create ambiguous provenance.",
            evidence_ids=[evidence_id, evidence_id],
        )
    with pytest.raises(ValidationError):
        KnowledgeSuggestionDraft(
            task_id=task_id,
            title="Reference is not inferred",
            body="Paper references use the Paper Library flow.",
            kind="reference",
            evidence_ids=[evidence_id],
        )


def test_knowledge_suggestion_preview_is_bound_to_evidence_review_state():
    task_id = uuid4()
    evidence = ResearchEvidence(
        id=uuid4(),
        task_id=task_id,
        kind="measurement",
        artifact_type="data_asset",
        artifact_id=str(uuid4()),
        artifact_version="2",
        summary="Replicate measurements passed QC",
        quality_state="validated",
        validation_report={"qc": "passed"},
        created_by_user_id=uuid4(),
        reviewed_by_user_id=uuid4(),
    )
    draft = KnowledgeSuggestionDraft(
        task_id=task_id,
        title="Replicated effect",
        body="The measured effect was reproduced under the recorded conditions.",
        evidence_ids=[evidence.id],
    )
    validated_digest = canonical_digest(
        _knowledge_suggestion_command(draft, [evidence])
    )

    evidence.quality_state = "rejected"

    assert validated_digest != canonical_digest(
        _knowledge_suggestion_command(draft, [evidence])
    )


def test_research_asset_openapi_exposes_preview_confirm_and_review_boundaries():
    paths = app.openapi()["paths"]

    assert "/research-assets/data-assets/preview" in paths
    assert "/research-assets/data-assets" in paths
    assert "/research-assets/evidence/preview" in paths
    assert "/research-assets/evidence/{evidence_id}/review" in paths
    assert "/research-assets/claims/preview" in paths
    assert "/research-assets/claims/{claim_id}/review" in paths
    assert "/research-assets/knowledge-suggestions/preview" in paths
    assert "/research-assets/knowledge-suggestions" in paths
