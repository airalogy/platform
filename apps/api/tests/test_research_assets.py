import asyncio
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.main import app
from app.models.research import ResearchAction, ResearchActionStatus
from app.models.research_asset import (
    DataAsset,
    DataAssetVersion,
    KnowledgeEvidenceLink,
    ProtocolImprovementEvidence,
    ProtocolImprovementProposal,
    ResearchActionOutputSnapshot,
    ResearchClaim,
    ResearchClaimEvidence,
    ResearchClaimRevision,
    ResearchEvidence,
)
from app.services.research_action_outputs import (
    ResearchActionOutputError,
    action_output_digest,
    action_output_payload,
    verify_action_output_snapshot,
)
from app.routers.research_assets import (
    AiraClaimDraftRequest,
    ClaimDraft,
    DataAssetDraft,
    EvidenceDraft,
    KnowledgeSuggestionDraft,
    ProtocolImprovementDraft,
    _knowledge_suggestion_command,
    _protocol_improvement_command,
)
from app.services.research_claims import (
    AiraClaimEvidenceOutput,
    AiraClaimOutput,
    create_claim_generation,
    generate_claim,
    sign_claim_generation_receipt,
    verify_claim_generation_receipt,
)
from app.services.research_protocol_improvements import (
    AiraProtocolImprovementOutput,
    create_generation,
    generate_protocol_improvement,
    sign_generation_receipt,
    verify_generation_receipt,
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


def test_action_output_evidence_uses_an_append_only_digest_bound_snapshot():
    ddl = compile_table(ResearchActionOutputSnapshot)
    migration = import_module(
        "migrations.versions.0036_research_action_output_snapshots"
    )

    assert "UNIQUE (action_id)" in ddl
    assert "ck_research_action_output_revision" in ddl
    assert "ck_research_action_output_digest" in ddl
    assert migration.down_revision == "0035_research_result_package_snapshots"
    assert migration.TABLE_NAMES == ("research_action_output_snapshots",)
    source = Path(migration.__file__).read_text(encoding="utf-8")
    assert "research_action_output_snapshots_append_only" in source
    assert "BEFORE UPDATE OR DELETE" in source


def test_action_output_snapshot_requires_a_completed_structured_result():
    task_id = uuid4()
    action = ResearchAction(
        id=uuid4(),
        run_id=uuid4(),
        kind="tool_job",
        status=ResearchActionStatus.COMPLETED.value,
        revision=2,
        output_data={"result": {"items": [{"id": "paper-1"}]}},
    )
    payload = action_output_payload(action, task_id=task_id)
    digest = action_output_digest(payload)
    snapshot = ResearchActionOutputSnapshot(
        id=uuid4(),
        task_id=task_id,
        run_id=action.run_id,
        action_id=action.id,
        action_revision=action.revision,
        action_kind=action.kind,
        output_data=action.output_data,
        digest=digest,
    )

    verify_action_output_snapshot(snapshot)
    snapshot.output_data = {"result": {"items": []}}
    with pytest.raises(ResearchActionOutputError, match="does not match"):
        verify_action_output_snapshot(snapshot)

    action.status = ResearchActionStatus.RUNNING.value
    with pytest.raises(ResearchActionOutputError, match="completed"):
        action_output_payload(action, task_id=task_id)


def test_claims_are_revisioned_and_link_to_evidence_with_semantics():
    claim_ddl = compile_table(ResearchClaim)
    revision_ddl = compile_table(ResearchClaimRevision)
    relation_ddl = compile_table(ResearchClaimEvidence)

    assert "confidence" in claim_ddl
    assert "uncertainty" in claim_ddl
    assert "UNIQUE (claim_id, revision)" in revision_ddl
    assert "relation" in relation_ddl
    assert "UNIQUE (claim_id, evidence_id)" in relation_ddl
    assert "ck_research_claim_generation_provenance" in claim_ddl
    assert "uq_research_claims_generation_id" in {
        index.name for index in ResearchClaim.__table__.indexes
    }

    migration = import_module("migrations.versions.0034_research_claim_ai_provenance")
    assert migration.down_revision == "0033_research_compute_outputs"
    assert set(migration.ADDED_COLUMNS) == {
        "generation_id",
        "generation_model",
        "generation_snapshot",
        "generation_receipt_digest",
    }


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


def test_protocol_improvements_pin_method_version_and_evidence():
    proposal_ddl = compile_table(ProtocolImprovementProposal)
    evidence_ddl = compile_table(ProtocolImprovementEvidence)

    assert "base_protocol_version_id" in proposal_ddl
    assert "applied_protocol_version_id" in proposal_ddl
    assert "ix_protocol_improvement_task_state" in {
        index.name for index in ProtocolImprovementProposal.__table__.indexes
    }
    assert "source_snapshot" in evidence_ddl
    assert "uq_protocol_improvement_evidence" in evidence_ddl
    assert "ck_protocol_improvement_generation_provenance" in proposal_ddl
    assert "uq_protocol_improvement_proposals_generation_id" in {
        index.name for index in ProtocolImprovementProposal.__table__.indexes
    }

    migration = import_module("migrations.versions.0021_protocol_improvement_lineage")
    assert migration.down_revision == "0020_knowledge_evidence_lineage"
    assert migration.TABLE_NAMES == (
        "protocol_improvement_proposals",
        "protocol_improvement_evidence",
    )

    provenance_migration = import_module(
        "migrations.versions.0022_protocol_improvement_ai_provenance"
    )
    assert provenance_migration.down_revision == "0021_protocol_improvement_lineage"
    assert set(provenance_migration.ADDED_COLUMNS) == {
        "generation_id",
        "generation_model",
        "generation_snapshot",
        "generation_receipt_digest",
    }


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
    with pytest.raises(ValidationError, match="provided together"):
        ClaimDraft(
            task_id=task_id,
            statement="Generated statement",
            aira_receipt="orphaned-receipt",
        )
    with pytest.raises(ValidationError, match="duplicates"):
        AiraClaimDraftRequest(
            task_id=task_id,
            evidence_ids=[evidence_id, evidence_id],
        )


def test_aira_claim_receipt_is_user_and_context_bound():
    user_id = uuid4()
    task_id = uuid4()
    evidence_id = uuid4()
    generation = create_claim_generation(
        output=AiraClaimOutput(
            statement="The measured response was reproducible in this dataset.",
            confidence=0.8,
            uncertainty="The Evidence does not establish generality beyond this dataset.",
            evidence=[
                AiraClaimEvidenceOutput(
                    evidence_id=evidence_id,
                    relation="supports",
                    rationale="The validated replicate result directly supports the statement.",
                )
            ],
        ),
        model_name="qwen3.5-plus",
        context_digest="c" * 64,
        instruction="Keep the scope narrow.",
        source_snapshot={"task": {"goal": "Assess reproducibility"}},
    )
    receipt = sign_claim_generation_receipt(
        generation,
        user_id=user_id,
        task_id=task_id,
    )

    verify_claim_generation_receipt(
        receipt,
        generation,
        user_id=user_id,
        task_id=task_id,
        context_digest="c" * 64,
    )
    with pytest.raises(ValueError, match="does not match"):
        verify_claim_generation_receipt(
            receipt,
            generation,
            user_id=uuid4(),
            task_id=task_id,
            context_digest="c" * 64,
        )
    tampered = generation.model_copy(deep=True)
    tampered.output.statement = "The result applies universally."
    with pytest.raises(ValueError, match="does not match"):
        verify_claim_generation_receipt(
            receipt,
            tampered,
            user_id=user_id,
            task_id=task_id,
            context_digest="c" * 64,
        )


def test_aira_claim_requires_one_relation_for_every_selected_evidence(monkeypatch):
    supporting_id = uuid4()
    contradicting_id = uuid4()

    async def fake_proposal(prompt, model_name, *, usage_context):
        assert "Use every supplied validated Evidence item exactly once" in prompt
        assert "do not force every relation to supports" in prompt
        assert model_name == "qwen3.5-plus"
        return {
            "statement": "The response appears under the tested conditions.",
            "confidence": 0.65,
            "uncertainty": "One validated result contradicts the primary observation.",
            "evidence": [
                {
                    "evidence_id": str(supporting_id),
                    "relation": "supports",
                    "rationale": "The primary measurement supports the bounded response.",
                },
                {
                    "evidence_id": str(contradicting_id),
                    "relation": "contradicts",
                    "rationale": "The replicate did not reproduce the same response.",
                },
            ],
        }

    monkeypatch.setattr(
        "app.services.research_claims.aira_structured_proposal",
        fake_proposal,
    )
    output = asyncio.run(
        generate_claim(
            context={"task": {"goal": "Assess the response"}},
            instruction="Preserve conflicting results",
            evidence_ids=[supporting_id, contradicting_id],
            model_name="qwen3.5-plus",
            usage_context=None,
        )
    )

    assert [item.relation for item in output.evidence] == [
        "supports",
        "contradicts",
    ]

    async def missing_evidence(*_args, **_kwargs):
        return {
            "statement": "Incomplete synthesis",
            "confidence": 0.5,
            "uncertainty": "A source was omitted.",
            "evidence": [
                {
                    "evidence_id": str(supporting_id),
                    "relation": "supports",
                    "rationale": "Only one source was assessed.",
                }
            ],
        }

    monkeypatch.setattr(
        "app.services.research_claims.aira_structured_proposal",
        missing_evidence,
    )
    with pytest.raises(ValueError, match="every selected Evidence"):
        asyncio.run(
            generate_claim(
                context={"task": {"goal": "Assess the response"}},
                instruction="",
                evidence_ids=[supporting_id, contradicting_id],
                model_name="qwen3.5-plus",
                usage_context=None,
            )
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


def test_protocol_improvement_preview_pins_protocol_and_evidence_state():
    task_id = uuid4()
    protocol_id = uuid4()
    evidence = ResearchEvidence(
        id=uuid4(),
        task_id=task_id,
        kind="measurement",
        artifact_type="record",
        artifact_id=str(uuid4()),
        artifact_version="1",
        summary="Replicate showed a narrower incubation window",
        quality_state="validated",
        validation_report={"replicates": 3},
        created_by_user_id=uuid4(),
        reviewed_by_user_id=uuid4(),
    )
    draft = ProtocolImprovementDraft(
        task_id=task_id,
        protocol_id=protocol_id,
        title="Tighten incubation timing",
        rationale="Validated Records show that timing variance changes the result.",
        proposed_changes="Specify a 28-32 minute incubation window.",
        evidence_ids=[evidence.id],
    )
    protocol_snapshot = {
        "id": str(protocol_id),
        "uid": "timing_assay",
        "name": "Timing assay",
        "base_protocol_version_id": str(uuid4()),
        "base_protocol_version": "1.2.0",
    }
    validated_digest = canonical_digest(
        _protocol_improvement_command(draft, protocol_snapshot, [evidence])
    )

    evidence.quality_state = "rejected"

    assert validated_digest != canonical_digest(
        _protocol_improvement_command(draft, protocol_snapshot, [evidence])
    )


def test_aira_protocol_improvement_receipt_is_user_and_context_bound():
    user_id = uuid4()
    task_id = uuid4()
    protocol_id = uuid4()
    generation = create_generation(
        output=AiraProtocolImprovementOutput(
            title="Tighten incubation timing",
            rationale="Validated measurements support a narrower window.",
            proposed_changes="Use a 28-32 minute incubation window.",
        ),
        model_name="qwen3.5-plus",
        context_digest="a" * 64,
        instruction="Prefer the smallest safe change.",
        source_snapshot={"task": {"goal": "Reduce variance"}},
    )
    receipt = sign_generation_receipt(
        generation,
        user_id=user_id,
        task_id=task_id,
        protocol_id=protocol_id,
    )

    with pytest.raises(ValidationError, match="provided together"):
        ProtocolImprovementDraft(
            task_id=task_id,
            protocol_id=protocol_id,
            title=generation.output.title,
            rationale=generation.output.rationale,
            proposed_changes=generation.output.proposed_changes,
            evidence_ids=[uuid4()],
            aira_generation=generation,
        )

    verify_generation_receipt(
        receipt,
        generation,
        user_id=user_id,
        task_id=task_id,
        protocol_id=protocol_id,
        context_digest="a" * 64,
    )
    with pytest.raises(ValueError, match="does not match"):
        verify_generation_receipt(
            receipt,
            generation,
            user_id=uuid4(),
            task_id=task_id,
            protocol_id=protocol_id,
            context_digest="a" * 64,
        )
    tampered = generation.model_copy(deep=True)
    tampered.output.title = "Unrelated change"
    with pytest.raises(ValueError, match="does not match"):
        verify_generation_receipt(
            receipt,
            tampered,
            user_id=user_id,
            task_id=task_id,
            protocol_id=protocol_id,
            context_digest="a" * 64,
        )


def test_aira_protocol_improvement_uses_strict_structured_output(monkeypatch):
    async def fake_proposal(prompt, model_name, *, usage_context):
        assert "Do not claim approval" in prompt
        assert model_name == "qwen3.5-plus"
        return {
            "title": "Tighten incubation timing",
            "rationale": "Validated measurements support a narrower window.",
            "proposed_changes": "Use a 28-32 minute incubation window.",
        }

    monkeypatch.setattr(
        "app.services.research_protocol_improvements.aira_structured_proposal",
        fake_proposal,
    )

    output = asyncio.run(
        generate_protocol_improvement(
            context={"task": {"goal": "Reduce variance"}},
            instruction="Prefer a minimal safe change",
            model_name="qwen3.5-plus",
            usage_context=None,
        )
    )

    assert output.title == "Tighten incubation timing"


def test_aira_protocol_improvement_receipt_expires():
    user_id = uuid4()
    task_id = uuid4()
    protocol_id = uuid4()
    generation = create_generation(
        output=AiraProtocolImprovementOutput(
            title="Old draft",
            rationale="This generation is intentionally expired.",
            proposed_changes="Do not apply this stale proposal.",
        ),
        model_name="qwen3.5-plus",
        context_digest="b" * 64,
        instruction="",
        source_snapshot={"task": {"goal": "Expired test"}},
        now=datetime.now(UTC) - timedelta(hours=2),
    )
    receipt = sign_generation_receipt(
        generation,
        user_id=user_id,
        task_id=task_id,
        protocol_id=protocol_id,
    )

    with pytest.raises(ValueError, match="invalid or expired"):
        verify_generation_receipt(
            receipt,
            generation,
            user_id=user_id,
            task_id=task_id,
            protocol_id=protocol_id,
            context_digest="b" * 64,
        )


def test_research_asset_openapi_exposes_preview_confirm_and_review_boundaries():
    paths = app.openapi()["paths"]

    assert "/research-assets/data-assets/preview" in paths
    assert "/research-assets/data-assets" in paths
    assert "/research-assets/evidence/preview" in paths
    assert "/research-assets/evidence/{evidence_id}/review" in paths
    assert "/research-assets/claims/preview" in paths
    assert "/research-assets/claims/aira-draft" in paths
    assert "/research-assets/claims/{claim_id}/review" in paths
    assert "/research-assets/knowledge-suggestions/preview" in paths
    assert "/research-assets/knowledge-suggestions" in paths
    assert "/research-assets/protocol-improvements/preview" in paths
    assert "/research-assets/protocol-improvements" in paths
    assert "/research-assets/protocol-improvements/aira-draft" in paths
    assert "/research-assets/protocol-improvements/{proposal_id}/review" in paths
