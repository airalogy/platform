from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.params import Body
from pydantic import BaseModel, StringConstraints
from sqlalchemy import and_, delete, literal, select
from sqlalchemy.orm import selectinload

from app.database import DBSession
from app.models.answer import Answer
from app.models.attachment import Attachment
from app.models.embedding import Embedding, EmbeddingResourceType
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.question import Question
from app.models.star import Star, StarResourceType
from app.models.upvote import Upvote, UpvoteResourceType
from app.models.user import User
from app.routers.depends import CurrentUser, OptionalCurrentUser
from app.routers.permission import check_user_permission
from app.routers.utils import UUID

router = APIRouter(
    prefix="/answers",
    tags=["question answers"],
)


@router.get("")
async def get_answers(
    db_session: DBSession,
    current_user: OptionalCurrentUser,
    question_id: UUID,
    parent_id: UUID | None = None,
    page: int = 1,
    page_size: int = 10,
):
    question = await Question.find(db_session, id=question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    protocol = await Protocol.find(db_session, id=question.protocol_id)
    if protocol is None:
        raise HTTPException(status_code=404, detail="Protocol not found")
    project = await Project.find(db_session, id=protocol.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="read_protocol",
        protocol=protocol,
    )

    conditions = [Answer.question_id == question_id, Answer.parent_id == parent_id]
    total_count = await Answer.count(db_session, conditions)
    order = [Answer.upvotes_count.desc(), Answer.id.asc()]
    query = (
        select(
            Answer,
            User.name,
            User.username,
            Attachment,
            literal(None).label("upvote_id"),
            literal(None).label("star_id"),
        )
        .outerjoin(User, User.id == Answer.user_id)
        .outerjoin(Attachment, Attachment.id == User.avatar)
        .where(*conditions)
        .order_by(*order)
        .limit(page_size)
        .offset((page - 1) * page_size)
    )

    if current_user is not None:
        query = (
            select(
                Answer,
                User.name,
                User.username,
                Attachment,
                Upvote.id.label("upvote_id"),
                Star.id.label("star_id"),
            )
            .outerjoin(User, User.id == Answer.user_id)
            .outerjoin(
                Upvote,
                and_(
                    Upvote.resource_id == Answer.id,
                    Upvote.resource_type == UpvoteResourceType.ANSWER,
                    Upvote.user_id == current_user.id,
                ),
            )
            .outerjoin(
                Star,
                and_(
                    Star.resource_id == Answer.id,
                    Star.resource_type == StarResourceType.ANSWER,
                    Star.user_id == current_user.id,
                ),
            )
            .outerjoin(Attachment, Attachment.id == User.avatar)
            .where(*conditions)
            .order_by(*order)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )

    results = (await db_session.execute(query)).all()
    answers = []
    for answer, name, username, attachment, upvote_id, star_id in results:
        avatar_url = None
        if attachment is not None:
            avatar_url = await attachment.url(expires=24 * 7)
        answers.append(
            answer.as_dict(
                upvoted=upvote_id is not None,
                starred=star_id is not None,
                user={
                    "name": name,
                    "username": username,
                    "avatar_url": avatar_url,
                },
            )
        )
    return {"answers": answers, "total_count": total_count}


@router.get("/{answer_id}")
async def get_answer(
    answer_id: UUID,
    db_session: DBSession,
    current_user: OptionalCurrentUser,
):
    answer = await Answer.find(db_session, id=answer_id)
    if answer is None:
        raise HTTPException(status_code=404, detail="Answer not found")
    question = await Question.find(db_session, id=answer.question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    protocol = await Protocol.find(db_session, id=question.protocol_id)
    if protocol is None:
        raise HTTPException(status_code=404, detail="Protocol not found")
    project = await Project.find(db_session, id=protocol.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="read_protocol",
        protocol=protocol,
    )

    user = await User.find(
        db_session,
        id=answer.user_id,
        options=selectinload(User.avatar_attachment),
    )
    await user.load_avatar_attachment()
    upvote = None
    star = None
    if current_user is not None:
        upvote = await Upvote.find_by(
            db_session,
            [
                Upvote.resource_id == answer_id,
                Upvote.resource_type == UpvoteResourceType.ANSWER,
                Upvote.user_id == current_user.id,
            ],
        )
        star = await Star.find_by(
            db_session,
            [
                Star.resource_id == answer_id,
                Star.resource_type == StarResourceType.ANSWER,
                Star.user_id == current_user.id,
            ],
        )

    return answer.as_dict(
        upvoted=upvote is not None,
        starred=star is not None,
        user={
            "name": user.name,
            "username": user.username,
            "avatar_url": user.avatar_url,
        },
    )


class AnswerCreateParams(BaseModel):
    question_id: UUID
    content: Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
    parent_id: UUID | None = None


@router.post("")
async def create_answer(
    params: AnswerCreateParams,
    current_user: CurrentUser,
    db_session: DBSession,
    background_tasks: BackgroundTasks,
):
    question = await Question.find(db_session, id=params.question_id)
    protocol = await Protocol.find(db_session, id=question.protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="read_protocol",
        protocol=protocol,
    )

    if params.parent_id is not None:
        parent_answer = await Answer.find_by(
            db_session, [Answer.id == params.parent_id]
        )
        if parent_answer is None:
            raise HTTPException(400, "Parent answer not found")
        if parent_answer.question_id != question.id:
            raise HTTPException(400, "Parent answer does not belong to this")

    answer = Answer(
        user_id=current_user.id,
        **params.model_dump(exclude_none=True),
    )
    db_session.add(answer)
    await db_session.flush()
    background_tasks.add_task(
        Embedding.add_resource,
        question.protocol_id,
        answer.id,
        EmbeddingResourceType.ANSWER,
        params.content,
    )

    if params.parent_id is not None:
        parent_answer.comments_count = await Answer.count(
            db_session, [Answer.parent_id == params.parent_id]
        )
    else:
        question.answers_count = await Answer.count(
            db_session, [Answer.question_id == question.id, Answer.parent_id.is_(None)]
        )

    await db_session.commit()
    return answer


@router.put("/{answer_id}")
async def update_answer(
    current_user: CurrentUser,
    db_session: DBSession,
    answer_id: UUID,
    background_tasks: BackgroundTasks,
    content: str = Body(embed=True),
):
    answer = await Answer.find(db_session, id=answer_id)
    if answer.user_id != current_user.id:
        raise HTTPException(400, "Permission denied")

    if content != answer.content:
        answer.content = content
        question = await Question.find(db_session, id=answer.question_id)
        background_tasks.add_task(
            Embedding.rebuild_resource,
            question.protocol_id,
            answer.id,
            EmbeddingResourceType.ANSWER,
            content,
        )
        await db_session.commit()

    return answer


@router.delete("/{answer_id}")
async def delete_answer(
    answer_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    background_tasks: BackgroundTasks,
):
    answer = await Answer.find(db_session, id=answer_id)
    if answer.user_id != current_user.id:
        raise HTTPException(400, "Permission denied")

    await db_session.execute(delete(Answer).where(Answer.id == answer_id))
    await db_session.execute(
        delete(Upvote).where(
            Upvote.resource_id == answer_id,
            Upvote.resource_type == UpvoteResourceType.ANSWER,
        )
    )
    await db_session.execute(
        delete(Star).where(
            Star.resource_id == answer_id,
            Star.resource_type == StarResourceType.ANSWER,
        )
    )
    background_tasks.add_task(
        Embedding.remove_resource,
        answer.id,
        EmbeddingResourceType.ANSWER,
    )
    # remove child answers
    child_answer_ids = (
        (
            await db_session.execute(
                select(Answer.id).where(Answer.parent_id == answer_id)
            )
        )
        .scalars()
        .all()
    )
    await db_session.execute(
        delete(Upvote).where(
            Upvote.resource_id.in_(child_answer_ids),
            Upvote.resource_type == UpvoteResourceType.ANSWER,
        )
    )
    await db_session.execute(
        delete(Star).where(
            Star.resource_id.in_(child_answer_ids),
            Star.resource_type == StarResourceType.ANSWER,
        )
    )
    background_tasks.add_task(
        Embedding.remove_resource,
        child_answer_ids,
        EmbeddingResourceType.ANSWER,
    )
    await db_session.execute(delete(Answer).where(Answer.parent_id == answer_id))
    await db_session.commit()
    return {"message": "success"}


@router.post("/{answer_id}/upvote")
async def upvote_answer(
    answer_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    up: bool = Body(default=True, embed=True),
):
    answer = await Answer.find(db_session, id=answer_id)
    question = await Question.find(db_session, id=answer.question_id)
    protocol = await Protocol.find(db_session, id=question.protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="read_protocol",
        protocol=protocol,
    )

    upvote = await Upvote.find_by(
        db_session,
        [
            Upvote.resource_id == answer_id,
            Upvote.resource_type == UpvoteResourceType.ANSWER,
            Upvote.user_id == current_user.id,
        ],
    )
    if up:
        if upvote is not None:
            return {"upvotes_count": answer.upvotes_count}
        else:
            upvote = Upvote(
                resource_id=answer_id,
                resource_type=UpvoteResourceType.ANSWER,
                user_id=current_user.id,
            )
            db_session.add(upvote)
            await db_session.flush()
    else:
        if upvote is not None:
            await db_session.delete(upvote)
            await db_session.flush()
        else:
            return {"upvotes_count": answer.upvotes_count}

    answer.upvotes_count = await Upvote.count(
        db_session,
        [
            Upvote.resource_id == answer_id,
            Upvote.resource_type == UpvoteResourceType.ANSWER,
        ],
    )
    await db_session.commit()
    return {"upvotes_count": answer.upvotes_count}
