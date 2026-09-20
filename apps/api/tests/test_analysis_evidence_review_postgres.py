"""Two real publication reviewers cannot both finalize the same pending Evidence."""

import asyncio
import os
from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text, update

from app.config import config
from app.models.project import ProjectRole, ProjectUser
from app.models.research import ResearchEvent
from app.models.research_asset import ResearchEvidence
from app.routers import research_assets as assets
from tests.test_analysis_publication_postgres import (
    confirm,
    preview,
    publication_draft,
    setup_publication,
)
from tests.test_record_analysis_postgres import database

pytestmark = pytest.mark.skipif(
    not os.environ.get("RESOURCE_TEST_DATABASE_URL"),
    reason="Dedicated PostgreSQL is required for concurrent Evidence review",
)


@pytest.fixture(autouse=True)
def manual_flat_permissions(monkeypatch):
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")
    monkeypatch.setattr(config, "AI_ENABLED", False)


def test_analysis_evidence_concurrent_review_has_one_final_decision():
    async def scenario():
        async with database() as sessions:
            f, run, task = await setup_publication(sessions)
            draft = publication_draft(task)
            prepared = await preview(sessions, f, run, draft)
            published = await confirm(sessions, f, run, draft, prepared)
            evidence_id = UUID(published["evidence"]["id"])
            async with sessions() as db:
                await db.execute(
                    update(ProjectUser)
                    .where(
                        ProjectUser.project_id == f.scope.project.id,
                        ProjectUser.user_id == f.scope.analyst.id,
                    )
                    .values(role=ProjectRole.MANAGER)
                )
                await db.commit()

            async with sessions() as first, sessions() as second, sessions() as blocker:
                # Both identity maps contain the old pending row before the race.
                # A locking get must refresh it after the winning transaction.
                cached_rows = []
                for db in (first, second):
                    cached = await db.get(ResearchEvidence, evidence_id)
                    assert cached.quality_state == "pending"
                    cached_rows.append(cached)
                    await db.execute(text("SET LOCAL statement_timeout = '10s'"))
                pids = [
                    await first.scalar(text("SELECT pg_backend_pid()")),
                    await second.scalar(text("SELECT pg_backend_pid()")),
                ]
                await blocker.scalar(
                    select(ResearchEvidence.id)
                    .where(ResearchEvidence.id == evidence_id)
                    .with_for_update()
                )
                reviews = [
                    asyncio.create_task(
                        assets.review_evidence(
                            evidence_id,
                            assets.EvidenceReview(
                                expected_quality_state="pending",
                                quality_state=decision,
                                validation_report={"synthetic_reviewer": str(user.id)},
                            ),
                            user,
                            db,
                        )
                    )
                    for decision, user, db in [
                        ("validated", f.scope.owner, first),
                        ("rejected", f.scope.analyst, second),
                    ]
                ]
                try:
                    # Observe actual PostgreSQL lock waits instead of hoping
                    # two fast coroutines happen to overlap.
                    async with asyncio.timeout(8):
                        while True:
                            blocked = [
                                bool(
                                    await blocker.scalar(
                                        text(
                                            "SELECT cardinality(pg_blocking_pids(:pid)) > 0"
                                        ),
                                        {"pid": pid},
                                    )
                                )
                                for pid in pids
                            ]
                            if all(blocked):
                                break
                            assert not any(review.done() for review in reviews)
                            await asyncio.sleep(0.01)
                    await blocker.commit()
                    outcomes = await asyncio.gather(*reviews, return_exceptions=True)
                finally:
                    await blocker.rollback()
                    for review in reviews:
                        if not review.done():
                            review.cancel()
                    await asyncio.gather(*reviews, return_exceptions=True)

            succeeded = [result for result in outcomes if isinstance(result, dict)]
            failed = [
                result for result in outcomes if isinstance(result, BaseException)
            ]
            assert len(succeeded) == len(failed) == 1, outcomes
            assert isinstance(failed[0], HTTPException)
            assert failed[0].status_code == 409
            winner = succeeded[0]
            async with sessions() as db:
                evidence = await db.get(ResearchEvidence, evidence_id)
                assert evidence.quality_state == winner["quality_state"]
                assert evidence.reviewed_by_user_id == winner["reviewed_by_user_id"]
                assert evidence.validation_report == winner["validation_report"]
                events = list(
                    (
                        await db.scalars(
                            select(ResearchEvent).where(
                                ResearchEvent.task_id == task.id,
                                ResearchEvent.kind == "evidence.reviewed",
                            )
                        )
                    ).all()
                )
                assert len(events) == 1
                assert events[0].payload["evidence_id"] == str(evidence_id)
                assert events[0].payload["quality_state"] == evidence.quality_state

    asyncio.run(scenario())
