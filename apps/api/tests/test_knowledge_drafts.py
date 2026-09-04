import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.models.knowledge import OwnerScope, Visibility
from app.routers.knowledge import (
    KnowledgeDraftParams,
    _has_restricted_source,
    _initial_knowledge_state,
    _require_restricted_ai_confirmation,
    _require_restricted_source_visibility,
    _research_file_search_access,
)
from app.services.knowledge import ScopeContext, canonical_digest
from app.services.knowledge_drafts import (
    AiraKnowledgeGeneration,
    AiraKnowledgeOutput,
    create_knowledge_generation,
    generate_knowledge_draft,
    knowledge_draft_prompt,
    sign_knowledge_generation_receipt,
    verify_knowledge_generation_receipt,
)


def _context():
    entry_id = uuid4()
    context = {
        "entry": {
            "library_entry_id": str(entry_id),
            "scope": {"scope_type": "personal"},
            "notes": "Relevant only to the reported assay.",
        },
        "paper": {
            "title": "A bounded result",
            "abstract": "The source reports one measured response.",
        },
        "authorized_full_text": [],
        "source_snapshot": {
            "library_entry_id": str(entry_id),
            "entry_digest": "a" * 64,
            "paper_digest": "b" * 64,
            "files": [],
        },
    }
    return entry_id, context


def _output():
    return AiraKnowledgeOutput(
        title="  Reported bounded result  ",
        kind="finding",
        body="  The Paper reports a bounded response; independent validation is missing.  ",
        tags=[" Assay ", "assay", "bounded"],
        rationale="  This is a reported result, not an adopted decision.  ",
        assumptions=[" The reported endpoint matches the intended use. "],
        warnings=[" Independent replication is not supplied. "],
    )


def test_aira_knowledge_output_is_bounded_and_normalized():
    output = _output()

    assert output.title == "Reported bounded result"
    assert output.tags == ["Assay", "bounded"]
    assert output.kind == "finding"

    with pytest.raises(ValidationError):
        AiraKnowledgeOutput(
            title="Invalid decision",
            kind="decision",
            body="A Paper cannot establish an organizational decision.",
            rationale="Reject this kind.",
        )


def test_knowledge_draft_prompt_preserves_scientific_and_execution_boundaries():
    _, context = _context()
    prompt = knowledge_draft_prompt(
        paper_context=context,
        instruction="Focus on the reported method.",
    )

    assert "A Paper cannot create an organizational decision" in prompt
    assert "Project or Lab the result remains Suggested" in prompt
    assert "performs no write" in prompt
    assert "untrusted scientific data" in prompt
    assert "A bounded result" in prompt


def test_generate_knowledge_draft_uses_strict_structured_transport(monkeypatch):
    _, context = _context()

    async def fake_proposal(prompt, model_name, *, usage_context):
        assert "editable Knowledge candidate" in prompt
        assert model_name == "qwen3.5-plus"
        assert usage_context is None
        return _output().model_dump()

    monkeypatch.setattr(
        "app.services.knowledge_drafts.aira_structured_proposal",
        fake_proposal,
    )

    output = asyncio.run(
        generate_knowledge_draft(
            paper_context=context,
            instruction="",
            model_name="qwen3.5-plus",
            usage_context=None,
        )
    )

    assert output.kind == "finding"
    assert "independent validation" in output.body


def test_knowledge_generation_receipt_binds_user_paper_context_and_output():
    user_id = uuid4()
    entry_id, context = _context()
    context_digest = canonical_digest(context)
    generation = create_knowledge_generation(
        output=_output(),
        model_name="qwen3.5-plus",
        context_digest=context_digest,
        instruction="",
        source_snapshot=context["source_snapshot"],
    )
    receipt = sign_knowledge_generation_receipt(
        generation,
        user_id=user_id,
        library_entry_id=entry_id,
    )

    verify_knowledge_generation_receipt(
        receipt,
        generation,
        user_id=user_id,
        library_entry_id=entry_id,
        context_digest=context_digest,
    )

    tampered = AiraKnowledgeGeneration.model_validate(generation.model_dump())
    tampered.output.body = "A broader unsupported statement."
    with pytest.raises(ValueError, match="does not match"):
        verify_knowledge_generation_receipt(
            receipt,
            tampered,
            user_id=user_id,
            library_entry_id=entry_id,
            context_digest=context_digest,
        )
    with pytest.raises(ValueError, match="does not match"):
        verify_knowledge_generation_receipt(
            receipt,
            generation,
            user_id=uuid4(),
            library_entry_id=entry_id,
            context_digest=context_digest,
        )


def test_knowledge_draft_requires_complete_aira_provenance():
    entry_id, context = _context()
    generation = create_knowledge_generation(
        output=_output(),
        model_name="qwen3.5-plus",
        context_digest=canonical_digest(context),
        instruction="",
        source_snapshot=context["source_snapshot"],
    )

    with pytest.raises(ValidationError, match="must be supplied together"):
        KnowledgeDraftParams(
            scope_type="personal",
            visibility="private",
            kind="finding",
            title="Draft",
            body="Body",
            paper_library_entry_ids=[entry_id],
            aira_generation=generation,
        )


def test_personal_aira_knowledge_is_a_draft_while_shared_scopes_need_review():
    generation = create_knowledge_generation(
        output=_output(),
        model_name="qwen3.5-plus",
        context_digest="c" * 64,
        instruction="",
        source_snapshot={"library_entry_id": str(uuid4())},
    )
    personal = KnowledgeDraftParams(
        scope_type="personal",
        visibility="private",
        kind="finding",
        title="Personal candidate",
        body="Confirmed by its owner as a personal draft.",
    )
    project = KnowledgeDraftParams(
        scope_type="project",
        lab_id=uuid4(),
        project_id=uuid4(),
        visibility="project",
        kind="finding",
        title="Project candidate",
        body="Requires a separate organizational review.",
    )

    assert _initial_knowledge_state(personal, generation) == "draft"
    assert _initial_knowledge_state(project, generation) == "suggested"


def test_restricted_paper_requires_explicit_ai_processing_confirmation():
    with pytest.raises(HTTPException, match="research data policy") as error:
        _require_restricted_ai_confirmation(True, confirmed=False)
    assert error.value.status_code == 422

    _require_restricted_ai_confirmation(True, confirmed=True)
    _require_restricted_ai_confirmation(False, confirmed=False)


def test_restricted_ai_processing_includes_authorized_linked_files():
    assert _has_restricted_source("private", [{"visibility": "restricted"}])
    assert _has_restricted_source("restricted", [{"visibility": "private"}])
    assert not _has_restricted_source("private", [{"visibility": "private"}])


def test_personal_full_text_search_excludes_other_users_restricted_files():
    user_id = uuid4()
    access = asyncio.run(
        _research_file_search_access(
            None,
            SimpleNamespace(id=user_id),
            ScopeContext(OwnerScope.PERSONAL, user_id, None, None),
        )
    )
    sql = str(access.compile(dialect=postgresql.dialect()))

    assert "research_files.visibility !=" in sql
    assert "research_files.uploaded_by_user_id =" in sql
    assert "research_files.owner_user_id =" in sql


def test_knowledge_derived_from_restricted_source_cannot_widen_visibility():
    with pytest.raises(HTTPException, match="must remain Restricted") as error:
        _require_restricted_source_visibility(
            ["restricted"],
            target_visibility=Visibility.LAB,
        )
    assert error.value.status_code == 422

    _require_restricted_source_visibility(
        ["restricted"],
        target_visibility=Visibility.RESTRICTED,
    )


def test_openapi_exposes_paper_to_aira_knowledge_preview_confirm_contract():
    from app.main import app

    paths = app.openapi()["paths"]
    assert "/knowledge/papers/{entry_id}/knowledge-draft-with-aira" in paths
    assert "/knowledge/items/preview" in paths
