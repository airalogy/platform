from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import StringConstraints
from sqlalchemy import and_, func, or_, select

from app.database import DBSession
from app.models.answer import Answer
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.question import Question
from app.routers.depends import CurrentUser, get_current_user
from app.routers.permission import check_user_permission

router = APIRouter(
    prefix="/search",
    tags=["search"],
    dependencies=[Depends(get_current_user)],
)


async def search_from_question(db_session, protocol_id, q, page, page_size):
    where_conditions = [
        Question.protocol_id == protocol_id,
        or_(
            Question.tsv.bool_op("@@")(func.plainto_tsquery("chinese_cfg", q)),
            Answer.id.isnot(None),
        ),
    ]

    order = [
        func.ts_rank_cd(Question.tsv, func.plainto_tsquery("chinese_cfg", q)).desc(),
        func.ts_rank_cd(Answer.tsv, func.plainto_tsquery("chinese_cfg", q)).desc(),
        Question.updated_at.desc(),
    ]

    count_stmt = (
        select(func.count())
        .select_from(Question)
        .outerjoin(
            Answer,
            and_(
                Answer.question_id == Question.id,
                Answer.tsv.bool_op("@@")(func.plainto_tsquery("chinese_cfg", q)),
            ),
        )
        .where(*where_conditions)
    )
    total_count = (await db_session.execute(count_stmt)).scalar()
    query = (
        select(
            Question,
            Answer.id.label("answer_id"),
            func.ts_headline(
                "chinese_cfg",
                Question.content,
                func.plainto_tsquery("chinese_cfg", q),
                "StartSel=<em>, StopSel=</em>, MaxWords=50, MinWords=1, MaxFragments=3",
            ).label("q_headline"),
            func.ts_headline(
                "chinese_cfg",
                Answer.content,
                func.plainto_tsquery("chinese_cfg", q),
                "StartSel=<em>, StopSel=</em>, MaxWords=50, MinWords=1, MaxFragments=3",
            ).label("a_headline"),
        )
        .outerjoin(
            Answer,
            and_(
                Answer.question_id == Question.id,
                Answer.tsv.bool_op("@@")(func.plainto_tsquery("chinese_cfg", q)),
            ),
        )
        .where(*where_conditions)
        .order_by(*order)
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    query_result = (await db_session.execute(query)).all()
    result = [
        d.Question.as_dict(
            headline="\n".join([d.q_headline, d.a_headline or ""])
            if "<em>" in d.q_headline
            else d.a_headline,
            answer_id=d.answer_id,
            q_headline=d.q_headline,
            a_headline=d.a_headline,
        )
        for d in query_result
    ]

    return {"result": result, "total_count": total_count}


@router.get("")
async def search(
    db_session: DBSession,
    current_user: CurrentUser,
    protocol_id: UUID,
    type: Literal["qa", "protocol"],
    q: Annotated[
        str | None,
        StringConstraints(min_length=1, max_length=64, strip_whitespace=True),
    ] = None,
    page: int = 1,
    page_size: int = 10,
):
    protocol = await Protocol.find(db_session, id=protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="read_protocol",
    )
    if type == "qa":
        res = await search_from_question(db_session, protocol_id, q, page, page_size)
    else:
        res = {"result": [], "total_count": 0}
    return res
