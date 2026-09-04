"""Allowlisted, schema-validated digital tools for Research Actions."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

from jsonschema import Draft202012Validator
from masterbrain.usage import UsageContext
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.models.knowledge import KnowledgeItem, KnowledgeState, OwnerScope, Visibility
from app.models.research import (
    ResearchAction,
    ResearchActionStatus,
    ResearchRun,
    ResearchRunStatus,
    ResearchTask,
    ResearchTaskStatus,
)
from app.models.research_execution import ResearchToolJob, ResearchToolJobStatus
from app.services.literature_provider import get_literature_provider
from app.services.model_usage import create_usage_context
from app.services.research_runtime import (
    emit_research_event,
    enqueue_research_advance,
    hold_or_release_aira_action_group,
    utcnow,
)


@dataclass(frozen=True)
class ResearchToolDefinition:
    key: str
    version: str
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk: str
    executor_type: str
    available: bool
    unavailable_reason: str = ""

    def payload(self) -> dict[str, Any]:
        return asdict(self)


def research_tool_catalog() -> dict[str, ResearchToolDefinition]:
    from app.services.research_specialists import (
        SPECIALIST_TOOL_KEY,
        SPECIALIST_TOOL_VERSION,
        SpecialistAgentRequest,
        SpecialistAgentResult,
    )

    literature_available = get_literature_provider() is not None
    return {
        "knowledge.search": ResearchToolDefinition(
            key="knowledge.search",
            version="1",
            name="Search reviewed Knowledge",
            description=(
                "Search reviewed, non-restricted Project and Lab Knowledge in the "
                "current Research Environment."
            ),
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 500},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
            },
            output_schema={
                "type": "object",
                "required": ["items"],
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "revision": {"type": "integer"},
                                "kind": {"type": "string"},
                                "title": {"type": "string"},
                                "body": {"type": "string"},
                                "tags": {"type": "array"},
                                "scope_type": {"type": "string"},
                            },
                        },
                    }
                },
            },
            risk="read_only",
            executor_type="platform_tool",
            available=True,
        ),
        "literature.search": ResearchToolDefinition(
            key="literature.search",
            version="1",
            name="Search external literature",
            description=(
                "Search the configured read-only LiteratureProvider for candidates. "
                "Results are not imported as formal assets automatically."
            ),
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 500},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
            },
            output_schema={
                "type": "object",
                "required": ["provider", "items"],
                "properties": {
                    "provider": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "doi": {"type": ["string", "null"]},
                                "title": {"type": "string"},
                                "abstract": {"type": ["string", "null"]},
                                "publish_year": {"type": ["integer", "null"]},
                                "authors": {"type": "array"},
                                "journal_name": {"type": ["string", "null"]},
                            },
                        },
                    },
                },
            },
            risk="external_read_only",
            executor_type="platform_tool",
            available=literature_available,
            unavailable_reason=(
                "No LiteratureProvider is configured"
                if not literature_available
                else ""
            ),
        ),
        "literature.resolve_doi": ResearchToolDefinition(
            key="literature.resolve_doi",
            version="1",
            name="Resolve literature DOI",
            description=(
                "Resolve one DOI through the configured read-only LiteratureProvider. "
                "The candidate is not imported as a formal asset automatically."
            ),
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["doi"],
                "properties": {
                    "doi": {"type": "string", "minLength": 1, "maxLength": 255}
                },
            },
            output_schema={
                "type": "object",
                "required": ["provider", "found", "item"],
                "properties": {
                    "provider": {"type": "string"},
                    "found": {"type": "boolean"},
                    "item": {"type": ["object", "null"]},
                },
            },
            risk="external_read_only",
            executor_type="platform_tool",
            available=literature_available,
            unavailable_reason=(
                "No LiteratureProvider is configured"
                if not literature_available
                else ""
            ),
        ),
        SPECIALIST_TOOL_KEY: ResearchToolDefinition(
            key=SPECIALIST_TOOL_KEY,
            version=SPECIALIST_TOOL_VERSION,
            name="Ask a bounded research specialist",
            description=(
                "Ask one source-grounded Literature, Experiment Design, Data, or "
                "Research Critic specialist for structured advice. The specialist "
                "cannot execute Actions, approve work, or write research assets."
            ),
            input_schema=SpecialistAgentRequest.model_json_schema(),
            output_schema=SpecialistAgentResult.model_json_schema(
                by_alias=True, mode="serialization"
            ),
            risk="model_advisory",
            executor_type="platform_tool",
            available=config.effective_ai_enabled,
            unavailable_reason=(
                "AI is disabled or no model provider is configured"
                if not config.effective_ai_enabled
                else ""
            ),
        ),
    }


def get_research_tool(tool_key: str) -> ResearchToolDefinition:
    definition = research_tool_catalog().get(tool_key)
    if definition is None:
        raise ValueError("Unknown Research Tool")
    if not definition.available:
        raise ValueError(
            definition.unavailable_reason or "Research Tool is unavailable"
        )
    return definition


def validate_tool_arguments(
    definition: ResearchToolDefinition,
    arguments: dict[str, Any],
) -> None:
    issues = sorted(
        Draft202012Validator(definition.input_schema).iter_errors(arguments),
        key=lambda item: list(item.absolute_path),
    )
    if issues:
        issue = issues[0]
        path = ".".join(str(item) for item in issue.absolute_path)
        raise ValueError(
            f"Invalid Tool arguments{f' at {path}' if path else ''}: {issue.message}"
        )


def validate_tool_argument_template(
    definition: ResearchToolDefinition,
    arguments: dict[str, Any],
    *,
    bound_argument_names: set[str],
) -> None:
    """Validate static arguments while reserving declared properties for bindings."""

    properties = dict(definition.input_schema.get("properties") or {})
    unknown_targets = bound_argument_names - set(properties)
    if unknown_targets:
        raise ValueError("Tool result binding targets an undeclared input property")
    if set(arguments) & bound_argument_names:
        raise ValueError("A bound Tool argument cannot also have a static value")
    schema = {
        **definition.input_schema,
        "required": [
            name
            for name in list(definition.input_schema.get("required") or [])
            if name not in bound_argument_names
        ],
    }
    issues = sorted(
        Draft202012Validator(schema).iter_errors(arguments),
        key=lambda item: list(item.absolute_path),
    )
    if issues:
        issue = issues[0]
        path = ".".join(str(item) for item in issue.absolute_path)
        raise ValueError(
            "Invalid Tool argument template"
            f"{f' at {path}' if path else ''}: {issue.message}"
        )


def validate_tool_output_path(
    definition: ResearchToolDefinition,
    path: list[str],
) -> None:
    """Reject binding paths that are impossible under a Tool's output contract."""

    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "tool_key": {"type": "string"},
            "tool_version": {"type": "string"},
            "result": definition.output_schema,
        },
    }
    for segment in path:
        schema_type = schema.get("type")
        schema_types = set(
            schema_type if isinstance(schema_type, list) else [schema_type]
        )
        properties = dict(schema.get("properties") or {})
        if "object" in schema_types or properties:
            next_schema = properties.get(segment)
            if not isinstance(next_schema, dict):
                raise ValueError(
                    "Tool result binding source path is outside the output Schema"
                )
            schema = next_schema
            continue
        if "array" in schema_types:
            if not segment.isdigit():
                raise ValueError("Tool result binding array path must use an index")
            next_schema = schema.get("items")
            if not isinstance(next_schema, dict):
                raise ValueError(
                    "Tool result binding array has no declared item Schema"
                )
            schema = next_schema
            continue
        raise ValueError("Tool result binding source path crosses a scalar Schema")


async def _search_knowledge(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    query = str(arguments["query"]).strip()
    limit = int(arguments.get("limit") or 20)
    pattern = f"%{query}%"
    items = list(
        (
            await db_session.scalars(
                select(KnowledgeItem)
                .where(
                    KnowledgeItem.lab_id == task.lab_id,
                    KnowledgeItem.archived_at.is_(None),
                    KnowledgeItem.state == KnowledgeState.REVIEWED.value,
                    KnowledgeItem.visibility != Visibility.RESTRICTED.value,
                    or_(
                        KnowledgeItem.scope_type == OwnerScope.LAB.value,
                        KnowledgeItem.project_id == task.project_id,
                    ),
                    or_(
                        KnowledgeItem.title.ilike(pattern),
                        KnowledgeItem.body.ilike(pattern),
                    ),
                )
                .order_by(KnowledgeItem.updated_at.desc())
                .limit(limit)
            )
        ).all()
    )
    return {
        "items": [
            {
                "id": str(item.id),
                "revision": item.revision,
                "kind": item.kind,
                "title": item.title,
                "body": item.body,
                "tags": item.tags,
                "scope_type": item.scope_type,
            }
            for item in items
        ]
    }


async def _search_literature(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = get_literature_provider()
    if provider is None:
        raise ValueError("No LiteratureProvider is configured")
    items = await provider.search(
        str(arguments["query"]).strip(), int(arguments.get("limit") or 20)
    )
    return {"provider": config.LITERATURE_PROVIDER, "items": items}


async def _resolve_literature_doi(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = get_literature_provider()
    if provider is None:
        raise ValueError("No LiteratureProvider is configured")
    item = await provider.resolve_doi(str(arguments["doi"]).strip())
    return {
        "provider": config.LITERATURE_PROVIDER,
        "found": item is not None,
        "item": item,
    }


async def execute_research_tool(
    db_session: AsyncSession,
    *,
    task: ResearchTask,
    definition: ResearchToolDefinition,
    arguments: dict[str, Any],
    context_snapshot: dict[str, Any] | None = None,
    model_name: str | None = None,
    usage_context: UsageContext | None = None,
) -> dict[str, Any]:
    validate_tool_arguments(definition, arguments)
    if definition.key == "knowledge.search":
        result = await _search_knowledge(db_session, task=task, arguments=arguments)
    elif definition.key == "literature.search":
        result = await _search_literature(arguments)
    elif definition.key == "literature.resolve_doi":
        result = await _resolve_literature_doi(arguments)
    elif definition.key == "aira.specialist":
        from app.services.research_specialists import (
            run_specialist_agent,
            validate_specialist_context_snapshot,
        )

        if context_snapshot is None or not model_name:
            raise ValueError("Specialist Agent requires a pinned context and model")
        validate_specialist_context_snapshot(context_snapshot, task=task)
        result = await run_specialist_agent(
            arguments=arguments,
            context_snapshot=context_snapshot,
            model_name=model_name,
            usage_context=usage_context,
        )
    else:  # pragma: no cover - registry and dispatch change together
        raise ValueError("Research Tool has no executor")
    output_issues = list(
        Draft202012Validator(definition.output_schema).iter_errors(result)
    )
    if output_issues:
        raise ValueError(
            f"Research Tool returned invalid output: {output_issues[0].message}"
        )
    return result


async def process_research_tool_job(
    db_session: AsyncSession,
    *,
    tool_job_id: UUID,
) -> dict[str, Any]:
    tool_job = await db_session.get(ResearchToolJob, tool_job_id)
    if tool_job is None:
        raise ValueError("Research Tool Job was not found")
    action = await db_session.get(ResearchAction, tool_job.action_id)
    if action is None:
        raise ValueError("Research Action was not found")
    run = await db_session.get(ResearchRun, action.run_id)
    task = await db_session.get(ResearchTask, run.task_id) if run else None
    if run is None or task is None:
        raise ValueError("Research Tool Job context was not found")
    if tool_job.status == ResearchToolJobStatus.COMPLETED.value:
        return tool_job.output
    if action.status == ResearchActionStatus.CANCELLED.value:
        tool_job.status = ResearchToolJobStatus.CANCELLED.value
        tool_job.completed_at = tool_job.completed_at or utcnow()
        await db_session.flush()
        return {"status": "cancelled"}
    if action.status not in {
        ResearchActionStatus.APPROVED.value,
        ResearchActionStatus.QUEUED.value,
        ResearchActionStatus.RUNNING.value,
    }:
        raise ValueError("Research Tool Action is not executable")

    definition = get_research_tool(tool_job.tool_key)
    if definition.version != tool_job.tool_version:
        raise ValueError("Pinned Research Tool version is unavailable")
    validate_tool_arguments(definition, tool_job.arguments)
    specialist_context: dict[str, Any] | None = None
    specialist_model: str | None = None
    specialist_usage: UsageContext | None = None
    if definition.key == "aira.specialist":
        from app.services.research_specialists import (
            validate_specialist_context_snapshot,
        )

        raw_context = action.input_data.get("specialist_context")
        if not isinstance(raw_context, dict):
            raise ValueError("Specialist Agent context is missing")
        specialist_context = dict(raw_context)
        validate_specialist_context_snapshot(
            specialist_context,
            task=task,
            run=run,
        )
        specialist_model = str(
            action.input_data.get("specialist_model")
            or specialist_context.get("model")
            or ""
        ).strip()
        if not specialist_model or specialist_model != specialist_context.get("model"):
            raise ValueError("Specialist Agent model does not match its context")
        specialist_usage = create_usage_context(
            feature="research.specialist_agent.run",
            user_id=run.requested_by_user_id,
            lab_id=task.lab_id,
            project_id=task.project_id,
            attributes={
                "task_id": str(task.id),
                "run_id": str(run.id),
                "action_id": str(action.id),
                "role": str(tool_job.arguments.get("role") or ""),
            },
        )
    now = utcnow()
    tool_job.status = ResearchToolJobStatus.RUNNING.value
    tool_job.started_at = tool_job.started_at or now
    tool_job.error = None
    action.status = ResearchActionStatus.RUNNING.value
    action.started_at = action.started_at or now
    action.revision += 1
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="tool_job.started",
        actor_user_id=None,
        payload={"tool_key": definition.key, "tool_version": definition.version},
        idempotency_key=f"tool-job:{tool_job.id}:started",
    )
    await db_session.commit()

    async with asyncio.timeout(tool_job.timeout_seconds):
        result = await execute_research_tool(
            db_session,
            task=task,
            definition=definition,
            arguments=tool_job.arguments,
            context_snapshot=specialist_context,
            model_name=specialist_model,
            usage_context=specialist_usage,
        )
    # The tool call intentionally runs without a long-lived write transaction.
    # Re-lock and refresh the execution chain so a concurrent Task cancellation
    # wins over a late external result.
    tool_job = (
        await db_session.execute(
            select(ResearchToolJob)
            .where(ResearchToolJob.id == tool_job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    action = (
        await db_session.execute(
            select(ResearchAction)
            .where(ResearchAction.id == tool_job.action_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    run = (
        await db_session.execute(
            select(ResearchRun)
            .where(ResearchRun.id == action.run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    task = (
        await db_session.execute(
            select(ResearchTask)
            .where(ResearchTask.id == run.task_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    if (
        tool_job.status == ResearchToolJobStatus.CANCELLED.value
        or action.status == ResearchActionStatus.CANCELLED.value
        or task.status == ResearchTaskStatus.CANCELLED.value
    ):
        tool_job.status = ResearchToolJobStatus.CANCELLED.value
        tool_job.completed_at = tool_job.completed_at or utcnow()
        await db_session.flush()
        return {"status": "cancelled"}
    completed_at = utcnow()
    tool_job.output = result
    tool_job.status = ResearchToolJobStatus.COMPLETED.value
    tool_job.completed_at = completed_at
    action.output_data = {
        "tool_key": definition.key,
        "tool_version": definition.version,
        "result": result,
    }
    action.status = ResearchActionStatus.COMPLETED.value
    action.completed_at = completed_at
    action.error = None
    action.revision += 1
    if action.input_data.get("resume_run"):
        previous_results = list((run.aira_state or {}).get("tool_results") or [])
        run.aira_state = {
            **(run.aira_state or {}),
            "tool_results": [
                *previous_results[-49:],
                {
                    "action_id": str(action.id),
                    "tool_key": definition.key,
                    "tool_version": definition.version,
                    "result": result,
                },
            ],
        }
        run.status = (
            ResearchRunStatus.PAUSED.value
            if task.status == ResearchTaskStatus.PAUSED.value
            else ResearchRunStatus.RUNNING.value
        )
        run.last_error = None
        frontier_settled = await hold_or_release_aira_action_group(
            db_session,
            task=task,
            run=run,
            action=action,
        )
        if (
            frontier_settled
            and run.status == ResearchRunStatus.RUNNING.value
            and task.status == ResearchTaskStatus.ACTIVE.value
        ):
            if config.effective_ai_enabled:
                await enqueue_research_advance(db_session, task=task, run=run)
            else:
                run.last_error = "AI is disabled; continue this Research Task manually."
                await emit_research_event(
                    db_session,
                    task_id=task.id,
                    run_id=run.id,
                    action_id=action.id,
                    kind="run.manual_control_required",
                    actor_user_id=None,
                    payload={"reason": "ai_disabled"},
                    idempotency_key=f"run:{run.id}:manual:tool-job:{tool_job.id}",
                )
    await emit_research_event(
        db_session,
        task_id=task.id,
        run_id=run.id,
        action_id=action.id,
        kind="tool_job.completed",
        actor_user_id=None,
        payload={
            "tool_key": definition.key,
            "result_count": len(result.get("items") or result.get("findings") or []),
        },
        idempotency_key=f"tool-job:{tool_job.id}:completed",
    )
    await db_session.flush()
    return result


async def mark_research_tool_job_failure(
    db_session: AsyncSession,
    *,
    tool_job_id: UUID,
    error: str,
    terminal: bool,
) -> None:
    tool_job = await db_session.get(ResearchToolJob, tool_job_id)
    if tool_job is None:
        return
    action = await db_session.get(ResearchAction, tool_job.action_id)
    run = await db_session.get(ResearchRun, action.run_id) if action else None
    task = await db_session.get(ResearchTask, run.task_id) if run else None
    tool_job.error = error[:8000]
    if terminal:
        now = utcnow()
        tool_job.status = ResearchToolJobStatus.FAILED.value
        tool_job.completed_at = now
        if action is not None:
            action.status = ResearchActionStatus.FAILED.value
            action.error = error[:8000]
            action.completed_at = now
            action.revision += 1
        if task is not None and run is not None and action is not None:
            await emit_research_event(
                db_session,
                task_id=task.id,
                run_id=run.id,
                action_id=action.id,
                kind="tool_job.failed",
                actor_user_id=None,
                payload={"tool_key": tool_job.tool_key, "error": error[:2000]},
                idempotency_key=f"tool-job:{tool_job.id}:failed",
            )
            if action.input_data.get("resume_run"):
                previous_results = list(
                    (run.aira_state or {}).get("tool_results") or []
                )
                run.aira_state = {
                    **(run.aira_state or {}),
                    "tool_results": [
                        *previous_results[-49:],
                        {
                            "action_id": str(action.id),
                            "tool_key": tool_job.tool_key,
                            "tool_version": tool_job.tool_version,
                            "error": error[:8000],
                        },
                    ],
                }
                run.status = (
                    ResearchRunStatus.PAUSED.value
                    if task.status == ResearchTaskStatus.PAUSED.value
                    else ResearchRunStatus.RUNNING.value
                )
                frontier_settled = await hold_or_release_aira_action_group(
                    db_session,
                    task=task,
                    run=run,
                    action=action,
                )
                run.last_error = f"Research Tool failed: {error[:7900]}"
                if (
                    frontier_settled
                    and run.status == ResearchRunStatus.RUNNING.value
                    and task.status == ResearchTaskStatus.ACTIVE.value
                ):
                    if config.effective_ai_enabled:
                        await enqueue_research_advance(db_session, task=task, run=run)
                    else:
                        await emit_research_event(
                            db_session,
                            task_id=task.id,
                            run_id=run.id,
                            action_id=action.id,
                            kind="run.manual_control_required",
                            actor_user_id=None,
                            payload={"reason": "tool_job_failed"},
                            idempotency_key=(
                                f"run:{run.id}:manual:tool-job-failed:{tool_job.id}"
                            ),
                        )
    else:
        tool_job.status = ResearchToolJobStatus.QUEUED.value
