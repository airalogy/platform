from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.params import Header, Query
from pydantic import StringConstraints
from sqlalchemy import and_, distinct, func, select
from typing_extensions import Annotated

from app.config import config
from app.database import DBSession
from app.libs.text_splitter import text_to_vectors, text_to_words
from app.models.embedding import Embedding, EmbeddingResourceType
from app.models.lab import Lab
from app.models.project import PermissionType, Project, ProjectType
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.user import User

router = APIRouter(prefix="/hub", tags=["hub"])


@router.get("")
async def get_protocols(
    db_session: DBSession,
    name: Annotated[
        str | None,
        StringConstraints(min_length=1, max_length=64, strip_whitespace=True),
    ] = None,
    q: Annotated[
        str | None,
        StringConstraints(min_length=1, max_length=64, strip_whitespace=True),
    ] = None,
    sorted_by: Literal["stars_count", "forks_count", "updated_at"] = "stars_count",
    page: int = 1,
    page_size: int = 10,
):
    if config.is_single_lab:
        raise HTTPException(status_code=404, detail="Not found")
    # Build conditions
    conditions = [Protocol.deleted_at.is_(None)]

    if name is not None:
        conditions.append(Protocol.name.ilike(f"%{name}%"))
    # Create subquery for records count
    records_count_subquery = (
        select(
            Record.protocol_id, func.count(distinct(Record.id)).label("records_count")
        )
        .where(Record.deleted_at.is_(None))
        .group_by(Record.protocol_id)
        .subquery()
    )

    # Start building the query
    query = (
        select(
            Protocol,
            ProtocolVersion.meta_data.label("metadata"),
            Project.name.label("project_name"),
            Project.uid.label("project_uid"),
            Lab.id.label("lab_id"),
            Lab.name.label("lab_name"),
            Lab.uid.label("lab_uid"),
            User.username.label("user_username"),
            User.name.label("user_name"),
            func.coalesce(records_count_subquery.c.records_count, 0).label(
                "records_count"
            ),
        )
        .select_from(Protocol)
        .join(
            Project,
            and_(
                Protocol.project_id == Project.id,
                Project.type == ProjectType.PUBLIC,
                Project.permission_type == PermissionType.INHERIT,
                Project.deleted_at.is_(None),
            ),
        )
        .outerjoin(Lab, Lab.id == Project.lab_id)
        .outerjoin(User, User.id == Protocol.user_id)
        .outerjoin(
            ProtocolVersion,
            and_(
                ProtocolVersion.protocol_id == Protocol.id,
                ProtocolVersion.version == Protocol.latest_version,
            ),
        )
        .outerjoin(
            records_count_subquery, records_count_subquery.c.protocol_id == Protocol.id
        )
    )
    # Get total count
    count_query = (
        select(func.count())
        .select_from(Protocol)
        .join(
            Project,
            and_(
                Project.id == Protocol.project_id,
                Project.type == ProjectType.PUBLIC,
                Project.permission_type == PermissionType.INHERIT,
            ),
        )
    )
    if q is not None:
        words = text_to_words(q.lower())
        qs = " | ".join(words)
        sub_query = (
            select(Embedding.resource_id)
            .where(
                Embedding.resource_type == EmbeddingResourceType.PROTOCOL,
                Embedding.tsv.bool_op("@@")(func.to_tsquery("english", qs)),
            )
            .order_by(
                func.ts_rank_cd(Embedding.tsv, func.to_tsquery("english", qs)).desc(),
            )
            .limit(30)
        )
        conditions.append(Protocol.id.in_(sub_query))

    # Apply conditions
    query = query.where(*conditions)
    count_query = count_query.where(*conditions)

    # Apply order by
    if sorted_by == "stars_count":
        query_order = [
            Protocol.stars_count.desc(),
            Protocol.forks_count.desc(),
            Protocol.id.desc(),
        ]
    elif sorted_by == "forks_count":
        query_order = [
            Protocol.forks_count.desc(),
            Protocol.stars_count.desc(),
            Protocol.id.desc(),
        ]
    elif sorted_by == "updated_at":
        query_order = [Protocol.updated_at.desc()]
    query = query.order_by(*query_order)
    # Add pagination
    query = query.limit(page_size).offset((page - 1) * page_size)

    # Execute query
    result = await db_session.execute(query)
    total_count = await db_session.scalar(count_query)

    # Process results with additional counts
    protocols = []
    for row in result:
        row.Protocol.lab_uid = row.lab_uid
        row.Protocol.project_uid = row.project_uid
        protocol_dict = row.Protocol.as_dict(
            lab={
                "id": row.lab_id,
                "name": row.lab_name,
                "uid": row.lab_uid,
            },
            project={
                "id": row.Protocol.project_id,
                "name": row.project_name,
                "uid": row.project_uid,
            },
            user={
                "id": row.Protocol.user_id,
                "username": row.user_username,
                "name": row.user_name,
            },
            metadata=row.metadata,
            records_count=row.records_count,
        )

        protocols.append(protocol_dict)

    return {"protocols": protocols, "total_count": total_count}


@router.get("/retrieval")
async def retrieval(
    db_session: DBSession,
    x_api_key: Annotated[str, Header()],
    content: Annotated[
        str,
        StringConstraints(min_length=1, max_length=500, strip_whitespace=True),
    ],
    top_k: Annotated[int, Query(ge=1, le=10)] = 3,
    distance: Annotated[float, Query(ge=0.1, le=1)] = 0.6,
) -> dict[str, list[dict[str, Any]]]:
    if x_api_key != config.INNER_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    vector = text_to_vectors([content])[0]

    ids_query = (
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
            Project.permission_type == PermissionType.INHERIT,
            Protocol.parent_protocol_id.is_(None),
            Embedding.embedding.cosine_distance(vector) < distance,
        )
        .order_by(
            Embedding.embedding.cosine_distance(vector).asc(),
            Protocol.stars_count.desc(),
            Protocol.forks_count.desc(),
            Embedding.id.asc(),
        )
        .limit(top_k * 2)
    )
    res1 = (await db_session.execute(ids_query)).all()
    if len(res1) == 0:
        return {"result": []}

    protocol_ids = []
    for row in res1:
        if len(protocol_ids) >= top_k:
            break
        if row.id not in protocol_ids:
            protocol_ids.append(row.id)

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
            Protocol.id.in_(protocol_ids),
        )
        .order_by(
            Protocol.id.desc(),
        )
        .limit(len(protocol_ids))
    )
    result = (await db_session.execute(query)).all()

    data = {}
    for protocol_version, lab_uid, project_uid in result:
        protocol_version.lab_uid = lab_uid
        protocol_version.project_uid = project_uid
        data[protocol_version.protocol_id] = {
            "id": protocol_version.airalogy_id,
            "aimd": protocol_version.aimd,
            "json_schema": protocol_version.json_schema,
        }
    result = []
    for id in protocol_ids:
        if data.get(id):
            result.append(data[id])

    return {"result": result}
