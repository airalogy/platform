"""Real API + PostgreSQL + persistent-job acceptance, with explicit fault injection.

Run through `pnpm research:integration`, never against development data. No API
responses, authorization, ledger, or state transitions are mocked. Only external
provider latency/failure and crash state are injected where the test names say so.
"""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select

from app.config import config
from app.database import sessionmanager
from app.main import app
from app.models.lab import LabUser
from app.models.research import ResearchAction, ResearchTask
from app.models.research_asset import ResearchActionOutputSnapshot, ResearchEvidence
from app.models.research_execution import ResearchBudgetEntry, ResearchToolJob
from app.models.resource import PersistentJob
from app.services import research_tools, resource_job_worker
from app.services.persistent_jobs import (
    JobDeferred,
    claim_job,
    complete_job,
    defer_job,
    fail_job,
)
from app.services.research_action_outputs import action_output_digest
from app.services.resource_job_worker import (
    process_persistent_job,
    reconcile_exhausted_jobs,
)

pytestmark = pytest.mark.skipif(
    os.getenv("RESEARCH_INTEGRATION_TEST") != "1",
    reason="Use pnpm research:integration with the isolated migrated PostgreSQL runtime",
)


class Runtime:
    def __init__(self, runner):
        self.runner = runner
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )

    def run(self, coroutine):
        return self.runner.run(coroutine)

    async def json(self, method, url, data=None, status=200):
        response = await self.client.request(method, url, json=data)
        assert response.status_code == status, (
            url,
            response.status_code,
            response.text,
        )
        return response.json()

    async def confirm(self, url, draft):
        preview = await self.json("POST", url + "/preview", draft)
        return await self.json(
            "POST", url, {**draft, "preview_digest": preview["preview_digest"]}
        )

    async def setup(self):
        assert (
            config.DATABASE_URL
            == "postgresql+asyncpg://airalogy_e2e:airalogy_e2e@127.0.0.1:55432/airalogy_e2e"
        )
        self.seed = await self.json("POST", "/dev/fixtures/quickstart")
        owner = next(a for a in self.seed["accounts"] if a["key"] == "owner")
        auth = await self.json(
            "POST",
            "/signin_by_email",
            {"email": owner["email"], "password": owner["password"]},
        )
        self.client.headers["Auth-Token"] = auth["token"]

    async def task(self, **overrides):
        task = await self.confirm(
            "/research-tasks",
            {
                "project_id": self.seed["project"]["id"],
                "title": "Runtime acceptance " + uuid4().hex,
                "goal": "Preserve evidence and execution boundaries",
                "success_criteria": ["Traceable reviewed outcome"],
                "tool_keys": ["knowledge.search"],
                **overrides,
            },
        )
        return await self.transition(task["id"], "start")

    async def transition(self, task_id, operation, **extra):
        task = await self.json("GET", f"/research-tasks/{task_id}")
        return await self.json(
            "POST",
            f"/research-tasks/{task_id}/{operation}",
            {
                "expected_revision": task["revision"],
                "reason": "Integration acceptance",
                **extra,
            },
        )

    async def tool(self, task, key="knowledge.search", arguments=None):
        return await self.confirm(
            f"/research-tasks/{task['id']}/tool-actions",
            {
                "tool_key": key,
                "arguments": arguments or {"query": "acceptance"},
                "idempotency_key": uuid4().hex,
            },
        )

    async def dispatch(self, tool):
        # Restrict the actual claim query to this fixture's job, leaving other
        # acceptance tasks' planner and notification jobs untouched.
        async with sessionmanager.session() as db:
            job = await db.scalar(
                select(PersistentJob).where(
                    PersistentJob.idempotency_key
                    == f"research-tool-job:{tool['tool_job']['id']}"
                )
            )
            claimed = await claim_job(
                db, worker_id="integration", kinds={"research_tool_job"}, job_id=job.id
            )
            assert claimed is not None
            await db.commit()
            try:
                result = await process_persistent_job(db, claimed)
                await complete_job(
                    db, job=claimed, worker_id="integration", result=result
                )
            except JobDeferred as error:
                await defer_job(
                    db, job=claimed, worker_id="integration", reason=str(error)
                )
            except Exception as error:
                job_id = claimed.id
                await db.rollback()
                claimed = await db.get(PersistentJob, job_id)
                await fail_job(
                    db, job=claimed, worker_id="integration", error=str(error)
                )
                await research_tools.mark_research_tool_job_failure(
                    db,
                    tool_job_id=UUID(tool["tool_job"]["id"]),
                    error=str(error),
                    terminal=claimed.status == "failed",
                )
            await db.commit()
            return claimed.status, claimed.attempts


@pytest.fixture(scope="module")
def runtime():
    with asyncio.Runner() as runner:
        runtime = Runtime(runner)
        runtime.run(runtime.setup())
        yield runtime
        runtime.run(runtime.client.aclose())
        runtime.run(sessionmanager._engine.dispose())


def test_ai_disabled_tool_pause_resume_evidence_and_final_package(runtime):
    async def exercise():
        assert not config.effective_ai_enabled
        task = await runtime.task()
        tool = await runtime.tool(task)
        await runtime.transition(task["id"], "pause")
        assert await runtime.dispatch(tool) == ("pending", 0)
        paused = await runtime.json("GET", f"/research-tasks/{task['id']}")
        assert paused["actions"][0]["status"] == "queued"
        await runtime.transition(task["id"], "resume")
        assert await runtime.dispatch(tool) == ("succeeded", 1)
        evidence = await runtime.confirm(
            "/research-assets/evidence",
            {
                "task_id": task["id"],
                "run_id": task["runs"][0]["id"],
                "action_id": tool["id"],
                "kind": "citation",
                "artifact_type": "action_output",
                "artifact_id": tool["id"],
                "summary": "The local search returned its actual structured result",
            },
        )
        assert evidence["quality_state"] == "pending"
        assert len(evidence["artifact_version"]) == 64
        await runtime.json(
            "POST",
            f"/research-assets/evidence/{evidence['id']}/review",
            {
                "expected_quality_state": "pending",
                "quality_state": "validated",
                "validation_report": {
                    "scope": "search result only, not experimental proof"
                },
            },
        )
        completed = await runtime.transition(
            task["id"],
            "complete",
            outcome="inconclusive",
            scientific_outcome="inconclusive",
            conclusion="Local search alone cannot settle the research question.",
        )
        assert completed["status"] == "completed"
        package = await runtime.json(
            "GET", f"/research-tasks/{task['id']}/result-package"
        )
        assert evidence["id"] in str(package)

    runtime.run(exercise())


@pytest.mark.parametrize("late_failure", [True, False])
def test_cancellation_wins_over_provider_return(runtime, monkeypatch, late_failure):
    async def exercise():
        task = await runtime.task()
        tool = await runtime.tool(task)
        started, released = asyncio.Event(), asyncio.Event()
        stop = asyncio.Event()
        async with sessionmanager.session() as db:
            persistent_id = await db.scalar(
                select(PersistentJob.id).where(
                    PersistentJob.idempotency_key
                    == f"research-tool-job:{tool['tool_job']['id']}"
                )
            )

        async def select_fixture_job(db, **kwargs):
            return await claim_job(db, **kwargs, job_id=persistent_id)

        async def delayed_provider(*args, **kwargs):
            started.set()
            await released.wait()
            stop.set()
            if late_failure:
                raise ValueError("Injected late provider failure")
            return {"items": []}

        monkeypatch.setattr(research_tools, "execute_research_tool", delayed_provider)
        monkeypatch.setattr(resource_job_worker, "claim_job", select_fixture_job)
        worker = asyncio.create_task(
            resource_job_worker.run_persistent_job_worker(stop, poll_seconds=0.01)
        )
        await asyncio.wait_for(started.wait(), 10)
        try:
            await runtime.transition(task["id"], "cancel")
        finally:
            released.set()
        await worker
        cancelled = await runtime.json("GET", f"/research-tasks/{task['id']}")
        assert cancelled["status"] == cancelled["runs"][0]["status"] == "cancelled"
        assert cancelled["actions"][0]["status"] == "cancelled"
        assert not any(e["kind"] == "tool_job.completed" for e in cancelled["events"])
        async with sessionmanager.session() as db:
            persisted = await db.get(PersistentJob, persistent_id)
            assert persisted.status != "running" and persisted.lease_owner is None

    runtime.run(exercise())


def test_resume_with_ai_available_waits_for_existing_tool(runtime, monkeypatch):
    async def exercise():
        task = await runtime.task()
        await runtime.tool(task)
        paused = await runtime.transition(task["id"], "pause")
        generation = paused["runs"][0]["advance_generation"]
        monkeypatch.setattr(config, "AI_ENABLED", True)
        monkeypatch.setattr(
            config, "DASHSCOPE_API_KEY", "integration-fake-key-not-a-credential"
        )
        resumed = await runtime.transition(task["id"], "resume")
        assert resumed["runs"][0]["status"] == "waiting_for_tool"
        assert resumed["runs"][0]["advance_generation"] == generation
        await runtime.transition(task["id"], "cancel")

    runtime.run(exercise())


def test_final_attempt_crash_is_reconciled_once_without_reexecution(runtime):
    async def exercise():
        task = await runtime.task()
        tool = await runtime.tool(task)
        async with sessionmanager.session() as db:
            job = await db.scalar(
                select(PersistentJob).where(
                    PersistentJob.idempotency_key
                    == f"research-tool-job:{tool['tool_job']['id']}"
                )
            )
            # Fault injection: persisted state at process death after its final claim.
            job.max_attempts = job.attempts = 1
            job.status, job.lease_owner = "running", "dead-worker"
            job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            action = await db.get(ResearchAction, UUID(tool["id"]))
            typed = await db.get(ResearchToolJob, UUID(tool["tool_job"]["id"]))
            action.status = typed.status = "running"
            await db.commit()
        async with sessionmanager.session() as restarted:
            assert await reconcile_exhausted_jobs(restarted) == 1
            await restarted.commit()
        async with sessionmanager.session() as restarted:
            assert await reconcile_exhausted_jobs(restarted) == 0
        stopped = await runtime.json("GET", f"/research-tasks/{task['id']}")
        assert stopped["status"] == stopped["runs"][0]["status"] == "paused"
        assert stopped["actions"][0]["status"] == "failed"
        assert "uncertain" in stopped["runs"][0]["last_error"]

    runtime.run(exercise())


@pytest.mark.parametrize("limit", ["time", "budget"])
def test_limits_rechecked_after_queueing(runtime, limit):
    async def exercise():
        task = await runtime.task(budget_limit="1", budget_currency="USD")
        tool = await runtime.tool(task)
        async with sessionmanager.session() as db:
            stored = await db.get(ResearchTask, UUID(task["id"]))
            if limit == "time":
                stored.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
            else:
                db.add(
                    ResearchBudgetEntry(
                        task_id=stored.id,
                        kind="expense",
                        amount=Decimal(1),
                        currency="USD",
                        command_digest="a" * 64,
                        idempotency_key=uuid4().hex,
                    )
                )
            await db.commit()
        assert await runtime.dispatch(tool) == ("pending", 0)
        paused = await runtime.json("GET", f"/research-tasks/{task['id']}")
        assert paused["status"] == "paused" and paused["outcome"] == f"stopped_{limit}"
        assert paused["actions"][0]["status"] == "queued"

    runtime.run(exercise())


def test_current_membership_is_required_at_dispatch(runtime):
    async def exercise():
        task = await runtime.task()
        tool = await runtime.tool(task)
        async with sessionmanager.session() as db:
            membership = await db.scalar(
                select(LabUser).where(
                    LabUser.lab_id == UUID(task["lab_id"]),
                    LabUser.user_id == UUID(task["owner_user_id"]),
                )
            )
            original = membership.as_dict()
            await db.delete(membership)
            await db.commit()
        try:
            assert await runtime.dispatch(tool) == ("pending", 0)
        finally:
            async with sessionmanager.session() as db:
                db.add(LabUser(**original))
                await db.commit()
        paused = await runtime.json("GET", f"/research-tasks/{task['id']}")
        assert paused["status"] == "paused"
        assert "permission was revoked" in paused["runs"][0]["last_error"]

    runtime.run(exercise())


def test_human_submission_validation_review_and_finalization_without_ai(runtime):
    async def exercise():
        task = await runtime.task()
        action = await runtime.confirm(
            f"/research-tasks/{task['id']}/human-actions",
            {
                "idempotency_key": uuid4().hex,
                "request": {
                    "title": "Read instrument display",
                    "instructions": "Record the displayed temperature",
                    "fields": [
                        {
                            "key": "temperature",
                            "label": "Temperature",
                            "value_type": "number",
                            "unit": "C",
                        }
                    ],
                },
            },
        )
        work = action["work_item"]
        url = f"/research-work-items/{work['id']}"
        await runtime.json(
            "POST",
            url + "/submission/preview",
            {
                "expected_revision": work["revision"],
                "values": {"temperature": "not-a-number"},
            },
            status=422,
        )
        submitted = await runtime.confirm(
            url + "/submission",
            {
                "expected_revision": work["revision"],
                "values": {"temperature": 23.5},
            },
        )
        assert submitted["status"] == "submitted"
        reviewed = await runtime.confirm(
            url + "/review",
            {
                "expected_revision": submitted["revision"],
                "expected_action_revision": submitted["action"]["revision"],
                "decision": "accept",
                "reason": "Checked against the recorded display",
            },
        )
        assert (
            reviewed["status"] == "accepted"
            and reviewed["action"]["status"] == "completed"
        )
        completed = await runtime.transition(
            task["id"],
            "complete",
            outcome="inconclusive",
            scientific_outcome="inconclusive",
            conclusion="One verified observation is insufficient for the research goal.",
        )
        assert completed["status"] == "completed"
        package = await runtime.json(
            "GET", f"/research-tasks/{task['id']}/result-package"
        )
        assert "23.5" in str(package) and "validated" in str(package)

    runtime.run(exercise())


def test_specialist_output_cannot_enter_evidence_api(runtime, monkeypatch):
    from app.services import research_specialists

    async def provider(*args, **kwargs):
        return {
            "summary": "No empirical conclusion is possible from the task description alone."
        }

    monkeypatch.setattr(config, "AI_ENABLED", True)
    monkeypatch.setattr(
        config, "DASHSCOPE_API_KEY", "integration-fake-key-not-a-credential"
    )
    monkeypatch.setattr(research_specialists, "aira_structured_proposal", provider)

    async def exercise():
        task = await runtime.task(tool_keys=["aira.specialist"])
        tool = await runtime.tool(
            task,
            "aira.specialist",
            {"role": "research_critic", "question": "Assess the available sources"},
        )
        assert await runtime.dispatch(tool) == ("succeeded", 1)
        await runtime.json(
            "POST",
            "/research-assets/evidence/preview",
            {
                "task_id": task["id"],
                "run_id": task["runs"][0]["id"],
                "action_id": tool["id"],
                "artifact_type": "action_output",
                "artifact_id": tool["id"],
                "kind": "analysis",
            },
            status=409,
        )
        # A pre-fix pending Evidence/snapshot must not bypass the new review gate.
        async with sessionmanager.session() as db:
            stored = await db.get(ResearchAction, UUID(tool["id"]))
            digest = action_output_digest(
                {
                    "schema": "airalogy.research-action-output.v1",
                    "task_id": task["id"],
                    "run_id": str(stored.run_id),
                    "action_id": str(stored.id),
                    "action_revision": stored.revision,
                    "action_kind": stored.kind,
                    "output_data": stored.output_data,
                }
            )
            db.add(
                ResearchActionOutputSnapshot(
                    task_id=UUID(task["id"]),
                    run_id=stored.run_id,
                    action_id=stored.id,
                    action_revision=stored.revision,
                    action_kind=stored.kind,
                    output_data=stored.output_data,
                    digest=digest,
                    created_by_user_id=UUID(task["owner_user_id"]),
                )
            )
            evidence = ResearchEvidence(
                task_id=UUID(task["id"]),
                run_id=stored.run_id,
                action_id=stored.id,
                kind="analysis",
                artifact_type="action_output",
                artifact_id=str(stored.id),
                artifact_version=digest,
                quality_state="pending",
                created_by_user_id=UUID(task["owner_user_id"]),
            )
            db.add(evidence)
            await db.commit()
            evidence_id = str(evidence.id)
        await runtime.json(
            "POST",
            f"/research-assets/evidence/{evidence_id}/review",
            {
                "expected_quality_state": "pending",
                "quality_state": "validated",
            },
            status=409,
        )
        rejected = await runtime.json(
            "POST",
            f"/research-assets/evidence/{evidence_id}/review",
            {
                "expected_quality_state": "pending",
                "quality_state": "rejected",
            },
        )
        assert rejected["quality_state"] == "rejected"

    runtime.run(exercise())
