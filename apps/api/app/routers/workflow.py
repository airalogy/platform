import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.database import DBSession
from app.libs.masterbrain import aira_workflow_step
from app.models.lab import Lab
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.user import User
from app.models.workflow import ProtocolWorkflow
from app.routers.depends import CurrentUser
from app.routers.permission import check_user_permission
from app.routers.utils import UUID

router = APIRouter(prefix="/workflow", tags=["workflow"])

AIRALOGY_PROTOCOL_ID_RE = re.compile(
    r"^airalogy\.id\.lab\.([A-Za-z0-9_-]+)\.project\.([A-Za-z0-9_-]+)\.protocol\.([A-Za-z0-9_-]+)\.v\.(\d+\.\d+\.\d+)$"
)
AIRALOGY_RECORD_ID_RE = re.compile(
    r"^airalogy\.id\.record\.([0-9a-fA-F-]{36})(?:\.v\.(\d+))?$"
)

AI_WORKFLOW_STATUSES = {
    "waiting_for_research_goal",
    "waiting_for_research_strategy",
    "waiting_for_next_protocol",
    "waiting_for_initial_values_for_fields_in_next_protocol",
    "waiting_for_phased_research_conclusion",
    "waiting_for_final_research_conclusion",
}

NON_AI_WORKFLOW_STATUSES = {
    "completed",
    "waiting_for_record",
    "end_after_generating_research_strategy",
    "end_after_selecting_next_protocol",
}


class WorkflowProtocolNode(BaseModel):
    model_config = ConfigDict(extra="allow")

    protocol_index: int = Field(ge=1)
    protocol_name: str = ""
    airalogy_protocol_id: str


class WorkflowInfoPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    title: str = "Workflow"
    protocols: list[WorkflowProtocolNode]
    edges: list[str] = Field(default_factory=list)
    logic: str | list[str] = ""
    default_initial_protocol_index: int | None = None
    default_research_goal: str | None = None
    default_research_strategy: str | None = None


class WorkflowCreatePayload(BaseModel):
    workflow_info: WorkflowInfoPayload
    airalogy_protocol_id: str
    research_goal: str = ""
    model: str | None = None


class WorkflowStepPayload(BaseModel):
    workflow_id: UUID
    path_data: dict[str, Any]
    model: str | None = None


@dataclass
class ProtocolContext:
    protocol: Protocol
    protocol_version: ProtocolVersion
    project: Project
    lab: Lab
    airalogy_protocol_id: str


def _logic_as_text(logic: str | list[str]) -> str:
    if isinstance(logic, list):
        return "\n".join(str(item) for item in logic if str(item).strip())
    return logic or ""


def _parse_record_airalogy_id(value: str) -> tuple[uuid.UUID, int | None]:
    match = AIRALOGY_RECORD_ID_RE.match(value.strip())
    if not match:
        raise HTTPException(status_code=400, detail=f"Invalid record id: {value}")

    record_id = uuid.UUID(match.group(1))
    version = int(match.group(2)) if match.group(2) else None
    return record_id, version


def _extract_airalogy_record_id(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None

    for key in ("airalogy_record_id", "airalogy_id"):
        record_id = value.get(key)
        if isinstance(record_id, str) and record_id.startswith("airalogy.id.record."):
            return record_id

    nested_data = value.get("data")
    if isinstance(nested_data, dict):
        return _extract_airalogy_record_id(nested_data)

    return None


def _path_status_after_step(current_status: str, step: dict[str, Any]) -> str:
    data = step.get("data") or {}

    if current_status == "waiting_for_research_goal":
        return "waiting_for_research_strategy"
    if current_status == "waiting_for_research_strategy":
        return (
            "waiting_for_next_protocol"
            if data.get("researchable", True)
            else "end_after_generating_research_strategy"
        )
    if current_status == "waiting_for_next_protocol":
        return (
            "end_after_selecting_next_protocol"
            if data.get("end_path")
            else "waiting_for_initial_values_for_fields_in_next_protocol"
        )
    if current_status == "waiting_for_initial_values_for_fields_in_next_protocol":
        return "waiting_for_record"
    if current_status == "waiting_for_phased_research_conclusion":
        return "waiting_for_next_protocol"
    if current_status == "waiting_for_final_research_conclusion":
        return "completed"
    return current_status


def _derive_path_fields(path_data: dict[str, Any], step: dict[str, Any]) -> None:
    if step.get("step") == "add_research_strategy":
        data = step.get("data") or {}
        if "researchable" in data:
            path_data["researchable"] = bool(data["researchable"])

    if step.get("step") == "add_final_research_conclusion":
        data = step.get("data") or {}
        conclusion = data.get("conclusion")
        if conclusion:
            path_data["final_research_conclusion"] = conclusion


async def _find_protocol_version(
    db_session: AsyncSession,
    protocol: Protocol,
    version: str | None = None,
) -> ProtocolVersion:
    protocol_version = await ProtocolVersion.find_by(
        db_session,
        [
            ProtocolVersion.protocol_id == protocol.id,
            ProtocolVersion.version == (version or protocol.latest_version),
        ],
    )
    if protocol_version is None:
        raise HTTPException(status_code=404, detail="Protocol version not found")
    return protocol_version


def _apply_airalogy_context(
    protocol: Protocol,
    protocol_version: ProtocolVersion,
    project: Project,
    lab: Lab,
) -> str:
    protocol.lab_uid = lab.uid
    protocol.project_uid = project.uid
    protocol.version = protocol_version.version
    protocol_version.lab_uid = lab.uid
    protocol_version.project_uid = project.uid
    return protocol.airalogy_id


async def _resolve_protocol_reference(
    db_session: AsyncSession,
    current_user: User,
    reference: str,
    *,
    project_id: uuid.UUID | None = None,
) -> ProtocolContext:
    value = str(reference or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="Protocol id is required")

    version: str | None = None
    protocol: Protocol | None = None
    project: Project | None = None
    lab: Lab | None = None

    full_id_match = AIRALOGY_PROTOCOL_ID_RE.match(value)
    if full_id_match:
        lab_uid, project_uid, protocol_uid, version = full_id_match.groups()
        lab = await Lab.find_by(db_session, [Lab.uid == lab_uid])
        if lab is None:
            raise HTTPException(status_code=404, detail="Lab not found")

        project = await Project.find_by(
            db_session,
            [
                Project.lab_id == lab.id,
                Project.uid == project_uid,
                Project.deleted_at.is_(None),
            ],
        )
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        protocol = await Protocol.find_by(
            db_session,
            [
                Protocol.project_id == project.id,
                Protocol.uid == protocol_uid,
                Protocol.deleted_at.is_(None),
            ],
        )
    else:
        protocol_uuid: uuid.UUID | None = None
        try:
            protocol_uuid = uuid.UUID(value)
        except ValueError:
            protocol_uuid = None

        if protocol_uuid is not None:
            protocol = await Protocol.find_by(
                db_session,
                [
                    Protocol.id == protocol_uuid,
                    Protocol.deleted_at.is_(None),
                ],
            )
        else:
            conditions = [
                Protocol.uid == value,
                Protocol.deleted_at.is_(None),
            ]
            if project_id is not None:
                conditions.append(Protocol.project_id == project_id)

            protocols = (await db_session.scalars(select(Protocol).where(*conditions))).all()
            if len(protocols) > 1:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Short protocol uid is ambiguous; use the full "
                        "airalogy_protocol_id."
                    ),
                )
            protocol = protocols[0] if protocols else None

        if protocol is not None:
            project = await Project.find(db_session, id=protocol.project_id)
            lab = await Lab.find(db_session, id=project.lab_id)

    if protocol is None or project is None or lab is None:
        raise HTTPException(status_code=404, detail=f"Protocol not found: {value}")

    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="read_protocol",
        protocol=protocol,
    )

    protocol_version = await _find_protocol_version(db_session, protocol, version)
    airalogy_protocol_id = _apply_airalogy_context(
        protocol,
        protocol_version,
        project,
        lab,
    )

    return ProtocolContext(
        protocol=protocol,
        protocol_version=protocol_version,
        project=project,
        lab=lab,
        airalogy_protocol_id=airalogy_protocol_id,
    )


async def _normalize_workflow_info(
    db_session: AsyncSession,
    current_user: User,
    workflow_info: WorkflowInfoPayload,
    *,
    workflow_id: uuid.UUID,
    initial_protocol_id: str | None = None,
) -> tuple[dict[str, Any], list[ProtocolContext], ProtocolContext]:
    if not workflow_info.protocols:
        raise HTTPException(
            status_code=400,
            detail="Workflow must contain at least one protocol",
        )

    initial_reference = (
        initial_protocol_id
        or next(
            (
                node.airalogy_protocol_id
                for node in workflow_info.protocols
                if node.protocol_index == workflow_info.default_initial_protocol_index
            ),
            None,
        )
        or workflow_info.protocols[0].airalogy_protocol_id
    )
    initial_context = await _resolve_protocol_reference(
        db_session,
        current_user,
        initial_reference,
    )
    project_id = initial_context.project.id

    raw_protocol_indexes = [node.protocol_index for node in workflow_info.protocols]
    if sorted(raw_protocol_indexes) != list(range(1, len(raw_protocol_indexes) + 1)):
        raise HTTPException(
            status_code=400,
            detail="Workflow protocol indexes must be sequential starting from 1",
        )

    contexts: list[ProtocolContext] = []
    normalized_protocols: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for node in sorted(workflow_info.protocols, key=lambda item: item.protocol_index):
        context = await _resolve_protocol_reference(
            db_session,
            current_user,
            node.airalogy_protocol_id,
            project_id=project_id,
        )
        if context.project.id != project_id:
            raise HTTPException(
                status_code=400,
                detail="Community workflow protocols must belong to the same project",
            )
        if context.airalogy_protocol_id in seen_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate workflow protocol: {context.airalogy_protocol_id}",
            )
        seen_ids.add(context.airalogy_protocol_id)
        contexts.append(context)
        normalized_protocols.append(
            {
                **node.model_dump(exclude={"airalogy_protocol_id"}),
                "protocol_name": node.protocol_name or context.protocol.name,
                "airalogy_protocol_id": context.airalogy_protocol_id,
            }
        )

    indexes = {node["protocol_index"] for node in normalized_protocols}
    for edge in workflow_info.edges:
        parts = re.split(r" -> | <-> ", edge)
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail=f"Invalid workflow edge: {edge}")
        try:
            source_index = int(parts[0])
            target_index = int(parts[1])
        except ValueError as err:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid workflow edge: {edge}",
            ) from err
        if source_index not in indexes or target_index not in indexes:
            raise HTTPException(
                status_code=400,
                detail=f"Workflow edge references missing protocol: {edge}",
            )

    if (
        workflow_info.default_initial_protocol_index is not None
        and workflow_info.default_initial_protocol_index not in indexes
    ):
        raise HTTPException(
            status_code=400,
            detail="default_initial_protocol_index is not in workflow protocols",
        )

    normalized = workflow_info.model_dump()
    normalized.update(
        {
            "id": str(workflow_id),
            "title": workflow_info.title or "Workflow",
            "protocols": normalized_protocols,
            "edges": workflow_info.edges,
            "logic": _logic_as_text(workflow_info.logic),
            "default_initial_protocol_index": (
                workflow_info.default_initial_protocol_index
                or normalized_protocols[0]["protocol_index"]
            ),
            "default_research_goal": workflow_info.default_research_goal,
            "default_research_strategy": workflow_info.default_research_strategy,
        }
    )
    return normalized, contexts, initial_context


def _protocol_info_from_context(context: ProtocolContext) -> dict[str, Any]:
    json_schema = context.protocol_version.json_schema or {}
    field_json_schema = (
        json_schema.get("vars")
        or json_schema.get("research_variable")
        or json_schema
    )
    assigners = context.protocol_version.assigners or None
    assigner = (
        json.dumps(assigners, ensure_ascii=False)
        if isinstance(assigners, dict) and assigners
        else assigners
        if isinstance(assigners, str)
        else None
    )

    return {
        "airalogy_protocol_id": context.airalogy_protocol_id,
        "markdown": context.protocol_version.aimd or "",
        "model": None,
        "assigner": assigner,
        "field_json_schema": field_json_schema,
    }


async def _load_workflow_contexts(
    db_session: AsyncSession,
    current_user: User,
    workflow_info: dict[str, Any],
    *,
    project_id: uuid.UUID,
) -> list[ProtocolContext]:
    contexts: list[ProtocolContext] = []
    for node in workflow_info.get("protocols") or []:
        contexts.append(
            await _resolve_protocol_reference(
                db_session,
                current_user,
                node.get("airalogy_protocol_id", ""),
                project_id=project_id,
            )
        )
    return contexts


async def _get_record_payload(
    db_session: AsyncSession,
    current_user: User,
    airalogy_record_id: str,
) -> tuple[dict[str, Any], Record]:
    record_id, version = _parse_record_airalogy_id(airalogy_record_id)

    conditions = [
        Record.id == record_id,
        Record.deleted_at.is_(None),
    ]
    if version is not None:
        conditions.append(Record.version == version)

    record = (
        await db_session.scalars(
            select(Record).where(*conditions).order_by(Record.version.desc()).limit(1)
        )
    ).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Workflow record not found")

    protocol = await Protocol.find(db_session, id=record.protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="read_record",
        protocol=protocol,
        record=record,
    )

    lab = await Lab.find(db_session, id=project.lab_id)
    protocol_version = await _find_protocol_version(
        db_session,
        protocol,
        record.protocol_version,
    )
    _apply_airalogy_context(protocol, protocol_version, project, lab)

    init_record = record
    if record.version > 1:
        init_record = await Record.find_by(
            db_session,
            [
                Record.id == record.id,
                Record.version == 1,
            ],
        ) or record

    record_user = await User.find(db_session, id=record.user_id)
    init_record_user = (
        record_user
        if init_record.user_id == record.user_id
        else await User.find(db_session, id=init_record.user_id)
    )
    payload = {
        "airalogy_record_id": record.airalogy_id,
        "record_id": record.id,
        "record_version": record.version,
        "metadata": {
            "airalogy_protocol_id": protocol.airalogy_id,
            "protocol_id": protocol.uid,
            "protocol_uuid": record.protocol_id,
            "protocol_version": record.protocol_version,
            "record_current_version_submission_time": record.created_at,
            "record_current_version_submission_user_id": record_user.username,
            "record_initial_version_submission_time": init_record.created_at,
            "record_initial_version_submission_user_id": init_record_user.username,
            "lab_id": lab.uid,
            "project_id": project.uid,
            "record_num": record.number,
            "sha1": record.hash,
        },
        "data": record.data,
        "report": record.report,
    }
    return jsonable_encoder(payload), record


async def _normalize_path_data(
    db_session: AsyncSession,
    current_user: User,
    path_data: dict[str, Any],
    contexts: list[ProtocolContext],
) -> dict[str, Any]:
    normalized = {
        **path_data,
        "path_status": path_data.get("path_status") or "waiting_for_research_goal",
        "researchable": bool(path_data.get("researchable", False)),
        "final_research_conclusion": path_data.get("final_research_conclusion") or "",
        "steps": [],
    }

    protocol_by_index = {
        index + 1: context
        for index, context in enumerate(contexts)
    }

    for index, raw_step in enumerate(path_data.get("steps") or []):
        step = {
            **raw_step,
            "path_index": raw_step.get("path_index", index),
            "mode": raw_step.get("mode") or "user",
            "data": dict(raw_step.get("data") or {}),
        }
        data = step["data"]

        if step.get("step") in {
            "add_next_protocol",
            "add_initial_values_for_fields_in_next_protocol",
            "add_record",
        }:
            protocol_index = data.get("protocol_index")
            protocol_index = (
                int(protocol_index)
                if str(protocol_index).isdigit()
                else protocol_index
            )
            if protocol_index in protocol_by_index:
                data["airalogy_protocol_id"] = protocol_by_index[
                    protocol_index
                ].airalogy_protocol_id

        if step.get("step") == "add_record":
            record_id = data.get("airalogy_record_id") or _extract_airalogy_record_id(
                data.get("record_data")
            )
            if record_id:
                record_payload, record = await _get_record_payload(
                    db_session,
                    current_user,
                    record_id,
                )
                protocol_index = data.get("protocol_index")
                protocol_index = (
                    int(protocol_index)
                    if str(protocol_index).isdigit()
                    else protocol_index
                )
                if protocol_index in protocol_by_index:
                    context = protocol_by_index[protocol_index]
                    if context.protocol.id != record.protocol_id:
                        raise HTTPException(
                            status_code=400,
                            detail="Workflow record protocol does not match the step protocol",
                        )
                data["airalogy_record_id"] = record_payload["airalogy_record_id"]
                data["record_data"] = record_payload
            else:
                data["record_data"] = data.get("record_data") or {}

        normalized["steps"].append(step)

    return normalized


def _build_workflow_response(
    workflow_info: dict[str, Any],
    contexts: list[ProtocolContext],
    path_data: dict[str, Any],
) -> dict[str, Any]:
    return {
        "workflow_info": workflow_info,
        "protocols_info": [
            _protocol_info_from_context(context)
            for context in contexts
        ],
        "path_data": path_data,
    }


async def _persist_workflow_path(
    db_session: AsyncSession,
    workflow: ProtocolWorkflow,
    path_data: dict[str, Any],
) -> None:
    workflow.path_data = path_data
    workflow.updated_at = datetime.now()
    await db_session.commit()


@router.post("")
async def start_workflow(
    params: WorkflowCreatePayload,
    current_user: CurrentUser,
    db_session: DBSession,
):
    workflow_id = uuid.uuid4()

    workflow_info, _contexts, initial_context = await _normalize_workflow_info(
        db_session,
        current_user,
        params.workflow_info,
        workflow_id=workflow_id,
        initial_protocol_id=params.airalogy_protocol_id,
    )

    research_goal = (
        params.research_goal
        or workflow_info.get("default_research_goal")
        or ""
    ).strip()
    steps = []
    path_status = "waiting_for_research_goal"
    if research_goal:
        steps.append(
            {
                "step": "add_research_goal",
                "path_index": 0,
                "mode": "user",
                "data": {
                    "thought": "",
                    "goal": research_goal,
                },
            }
        )
        path_status = "waiting_for_research_strategy"

    path_data = {
        "path_status": path_status,
        "researchable": False,
        "final_research_conclusion": "",
        "steps": steps,
    }

    workflow = ProtocolWorkflow(
        id=workflow_id,
        project_id=initial_context.project.id,
        user_id=current_user.id,
        root_protocol_id=initial_context.protocol.id,
        title=workflow_info["title"],
        workflow_info=workflow_info,
        path_data=path_data,
    )
    db_session.add(workflow)
    await db_session.commit()

    return {
        "id": str(workflow.id),
        "path_data": path_data,
    }


@router.post("/step")
async def generate_workflow_step(
    params: WorkflowStepPayload,
    current_user: CurrentUser,
    db_session: DBSession,
):
    workflow = await ProtocolWorkflow.find_by(
        db_session,
        [ProtocolWorkflow.id == params.workflow_id],
        with_for_update=True,
    )
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if workflow.user_id != current_user.id:
        raise HTTPException(status_code=400, detail="Permission denied")

    contexts = await _load_workflow_contexts(
        db_session,
        current_user,
        workflow.workflow_info,
        project_id=workflow.project_id,
    )
    path_data = await _normalize_path_data(
        db_session,
        current_user,
        params.path_data,
        contexts,
    )
    path_status = path_data["path_status"]

    if path_status in NON_AI_WORKFLOW_STATUSES:
        if path_status == "completed" and not path_data.get("final_research_conclusion"):
            final_step = next(
                (
                    step
                    for step in reversed(path_data["steps"])
                    if step.get("step") == "add_final_research_conclusion"
                ),
                None,
            )
            if final_step:
                path_data["final_research_conclusion"] = (
                    final_step.get("data") or {}
                ).get("conclusion", "")
        await _persist_workflow_path(db_session, workflow, path_data)
        return _build_workflow_response(workflow.workflow_info, contexts, path_data)

    if path_status not in AI_WORKFLOW_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported workflow status: {path_status}",
        )

    workflow_data = _build_workflow_response(workflow.workflow_info, contexts, path_data)
    next_step = await aira_workflow_step(
        workflow_data,
        params.model or config.CHAT_MODEL_FAST,
    )
    path_data["steps"] = [*path_data["steps"], next_step]
    _derive_path_fields(path_data, next_step)
    path_data["path_status"] = _path_status_after_step(path_status, next_step)

    await _persist_workflow_path(db_session, workflow, path_data)
    return _build_workflow_response(workflow.workflow_info, contexts, path_data)


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    workflow = await ProtocolWorkflow.find_by(
        db_session,
        [ProtocolWorkflow.id == workflow_id],
    )
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if workflow.user_id != current_user.id:
        raise HTTPException(status_code=400, detail="Permission denied")

    contexts = await _load_workflow_contexts(
        db_session,
        current_user,
        workflow.workflow_info,
        project_id=workflow.project_id,
    )
    path_data = await _normalize_path_data(
        db_session,
        current_user,
        workflow.path_data,
        contexts,
    )
    return _build_workflow_response(workflow.workflow_info, contexts, path_data)
