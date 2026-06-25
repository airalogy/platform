import json
import uuid
from typing import Any

from sqlalchemy import and_, select

from app.database import DBSession
from app.libs.text_splitter import text_to_vectors
from app.models.answer import Answer
from app.models.embedding import Embedding, EmbeddingResourceType
from app.models.lab import Lab
from app.models.project import Project, ProjectType
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record

MAX_EDITOR_CONTEXT_SECTION_CHARS = 12000
MAX_RECORDER_CONTEXT_CHARS = 24000


def _truncate_editor_context(text: str, limit: int = MAX_EDITOR_CONTEXT_SECTION_CHARS):
    if len(text) <= limit:
        return text
    return (
        text[:limit]
        + "\n\n[Content truncated before sending to Aira. Ask the user for a smaller section if exact later lines are needed.]"
    )


def _line_number_text(text: str) -> str:
    return "\n".join(f"{index:04d}: {line}" for index, line in enumerate(text.splitlines(), 1))


def _format_editor_context_section(file_name: str, content: str | None) -> str | None:
    if not content or not content.strip():
        return None

    line_numbered = _line_number_text(_truncate_editor_context(content))
    return f"## {file_name}\n```text\n{line_numbered}\n```"


def build_current_editor_protocol_context_message(
    editor_context: dict[str, Any] | None,
) -> dict[str, str] | None:
    if not editor_context or not editor_context.get("enabled", False):
        return None

    sections = [
        _format_editor_context_section(
            "protocol.aimd",
            editor_context.get("protocol_aimd"),
        ),
        _format_editor_context_section(
            "model.py",
            editor_context.get("model_py"),
        ),
        _format_editor_context_section(
            "assigner.py",
            editor_context.get("assigner_py"),
        ),
        _format_editor_context_section(
            "protocol.toml",
            editor_context.get("protocol_toml"),
        ),
    ]
    sections = [section for section in sections if section]
    if not sections:
        return None

    title = editor_context.get("title") or "Current editor protocol"
    content = "\n\n".join(
        [
            "[Current editor protocol context]",
            f"Title: {title}",
            "Use the line numbers below when identifying errors. The line-number prefixes are not part of the files.",
            *sections,
        ]
    )

    return {
        "role": "user",
        "content": content,
    }


def _truncate_recorder_context(text: str, limit: int = MAX_RECORDER_CONTEXT_CHARS):
    if len(text) <= limit:
        return text
    return (
        text[:limit]
        + "\n\n[Current recorder record context truncated before sending to Aira. Ask the user for a narrower question if exact omitted values are needed.]"
    )


def build_current_recorder_record_context_message(
    record_context: dict[str, Any] | None,
) -> dict[str, str] | None:
    if not record_context or not record_context.get("enabled", False):
        return None

    field_summary = record_context.get("field_summary")
    record_data = record_context.get("record_data")
    if not field_summary and not record_data:
        return None

    title = record_context.get("title") or "Current recorder record"
    payload = {
        "metadata": {
            "title": title,
            "protocol_id": record_context.get("protocol_id"),
            "protocol_uid": record_context.get("protocol_uid"),
            "protocol_name": record_context.get("protocol_name"),
            "readonly": record_context.get("readonly", False),
            "filled_count": record_context.get("filled_count"),
            "empty_count": record_context.get("empty_count"),
            "truncated_on_client": record_context.get("truncated", False),
        },
        "field_summary": field_summary or [],
        "record_data": record_data or {},
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    content = "\n\n".join(
        [
            "[Current recorder record context]",
            "This is the current Recorder form state for the user's active record. It may include unsaved changes.",
            "Use `field_summary` for field IDs, labels, filled status, and filled values. Use `record_data` as the structured record payload when available.",
            f"```json\n{_truncate_recorder_context(serialized)}\n```",
        ]
    )

    return {
        "role": "user",
        "content": content,
    }


async def inject_airalogy_protocols(
    db_session: DBSession, airalogy_record_ids: list[str]
) -> dict[str, list[dict[str, Any]]]:
    ids = [uuid.UUID(id.split(".")[-1]) for id in airalogy_record_ids]
    query = (
        select(Protocol, ProtocolVersion)
        .where(Protocol.id.in_(ids))
        .join(
            ProtocolVersion,
            and_(
                ProtocolVersion.protocol_id == Protocol.id,
                ProtocolVersion.version == Protocol.latest_version,
            ),
        )
    )
    result = await db_session.execute(query)
    data = []
    for row in result:
        protocol = row.Protocol
        protocol_version = row.ProtocolVersion
        data.append(
            {
                "id": f"airalogy.id.protocol.{protocol.id}",
                "markdown": protocol_version.aimd,
                "field_json_schema": protocol_version.json_schema,
            }
        )
    return {"airalogy_protocols": data}


async def inject_airalogy_records(
    db_session: DBSession, airalogy_record_ids: list[str]
) -> dict[str, list[dict[str, Any]]]:
    ids = [uuid.UUID(id.split(".")[-1]) for id in airalogy_record_ids]
    records = await Record.all(
        db_session,
        [Record.id.in_(ids)],
    )
    data = []
    for record in records:
        protocol = await Protocol.find(db_session, id=record.protocol_id)
        data.append(
            {
                "id": f"airalogy.id.record.{record.id}",
                "metadata": {
                    "protocol_id": f"airalogy.id.protocol.{protocol.id}",
                },
                "data": record.data,
            }
        )
    return {"airalogy_records": data}


async def inject_airalogy_discussions(db_session, protocol_id: uuid.UUID, content: str):
    query_result = await Embedding.retrieval_vector(
        db_session,
        protocol_id,
        [EmbeddingResourceType.QUESTION, EmbeddingResourceType.ANSWER],
        content,
    )
    data = []
    for result in query_result:
        if result["resource_type"] == EmbeddingResourceType.ANSWER:
            question_id = (
                await Answer.find(db_session, id=result["resource_id"])
            ).question_id
        else:
            question_id = result["resource_id"]
        data.append(
            {
                "airalogy_discussion_id": f"airalogy.id.discussion.{question_id}",
                "content": result["text"],
                "similarity": result["similarity"],
            }
        )
    return {"airalogy_discussions": data}


async def inject_recommended_airalogy_protocols(
    db_session, content: str, limit: int = 3
):
    vector = text_to_vectors([content[0:1000]])[0]

    sub_query = (
        select(
            Protocol.id,
        )
        .join(
            Embedding,
            and_(
                Embedding.resource_id == Protocol.id,
                Embedding.resource_type == EmbeddingResourceType.PROTOCOL,
            ),
        )
        .join(
            Project,
            Protocol.project_id == Project.id,
        )
        .where(
            Project.type == ProjectType.PUBLIC,
            Protocol.parent_protocol_id.is_(None),
            Embedding.embedding.cosine_distance(vector) < 0.5,
        )
        .order_by(
            Embedding.embedding.cosine_distance(vector).asc(),
            Protocol.stars_count.desc(),
            Protocol.forks_count.desc(),
        )
        .limit(limit * 2)
        .subquery()
    )
    query = (
        select(
            ProtocolVersion, Lab.uid.label("lab_uid"), Project.uid.label("project_uid")
        )
        .join(
            Protocol,
            and_(
                ProtocolVersion.protocol_id == Protocol.id,
                ProtocolVersion.version == Protocol.latest_version,
            ),
        )
        .outerjoin(
            Project,
            Protocol.project_id == Project.id,
        )
        .outerjoin(
            Lab,
            Project.lab_id == Lab.id,
        )
        .where(
            Protocol.id.in_(select(sub_query.c.id)),
        )
        .order_by(
            Protocol.stars_count.desc(),
            Protocol.forks_count.desc(),
        )
        .limit(limit)
    )
    result = (await db_session.execute(query)).all()

    data = []
    for protocol_version, lab_uid, project_uid in result:
        protocol_version.lab_uid = lab_uid
        protocol_version.project_uid = project_uid
        data.append(
            {
                "id": protocol_version.airalogy_id,
                "markdown": protocol_version.aimd,
                "field_json_schema": protocol_version.json_schema,
            }
        )
    return {"airalogy_protocols": data}
