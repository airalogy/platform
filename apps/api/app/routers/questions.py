from datetime import datetime
from typing import Annotated
from uuid import UUID

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

router = APIRouter(
    prefix="/questions",
    tags=["questions"],
)


@router.get("")
async def get_questions(
    db_session: DBSession,
    current_user: OptionalCurrentUser,
    protocol_id: UUID,
    page: int = 1,
    page_size: int = 10,
):
    protocol = await Protocol.find(db_session, id=protocol_id)
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
    where_conditions = [Question.protocol_id == protocol_id]
    total_count = await Question.count(db_session, where_conditions)
    query = (
        select(
            Question,
            User.name,
            User.username,
            Attachment,
            literal(None).label("upvote_id"),
            literal(None).label("star_id"),
        )
        .outerjoin(User, User.id == Question.user_id)
        .outerjoin(Attachment, Attachment.id == User.avatar)
        .where(*where_conditions)
        .order_by(Question.updated_at.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )

    if current_user is not None:
        query = (
            select(
                Question,
                User.name,
                User.username,
                Attachment,
                Upvote.id.label("upvote_id"),
                Star.id.label("star_id"),
            )
            .outerjoin(User, User.id == Question.user_id)
            .outerjoin(
                Upvote,
                and_(
                    Upvote.resource_id == Question.id,
                    Upvote.resource_type == UpvoteResourceType.QUESTION,
                    Upvote.user_id == current_user.id,
                ),
            )
            .outerjoin(
                Star,
                and_(
                    Star.resource_id == Question.id,
                    Star.resource_type == StarResourceType.QUESTION,
                    Star.user_id == current_user.id,
                ),
            )
            .outerjoin(Attachment, Attachment.id == User.avatar)
            .where(*where_conditions)
            .order_by(Question.updated_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )

    results = (await db_session.execute(query)).all()
    questions = []
    for question, name, username, attachment, upvote_id, star_id in results:
        avatar_url = None
        if attachment is not None:
            avatar_url = await attachment.url(expires=24 * 7)
        questions.append(
            question.as_dict(
                upvoted=upvote_id is not None,
                starred=star_id is not None,
                user={
                    "name": name,
                    "username": username,
                    "avatar_url": avatar_url,
                },
            )
        )
    return {"questions": questions, "total_count": total_count}


@router.get("/{question_id}")
async def get_question(
    question_id: UUID,
    db_session: DBSession,
    current_user: OptionalCurrentUser,
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

    user = await User.find(
        db_session,
        id=question.user_id,
        options=selectinload(User.avatar_attachment),
    )
    await user.load_avatar_attachment()
    upvote = None
    star = None
    if current_user is not None:
        upvote = await Upvote.find_by(
            db_session,
            [
                Upvote.resource_id == question_id,
                Upvote.resource_type == UpvoteResourceType.QUESTION,
                Upvote.user_id == current_user.id,
            ],
        )
        star = await Star.find_by(
            db_session,
            [
                Star.resource_id == question_id,
                Star.resource_type == StarResourceType.QUESTION,
                Star.user_id == current_user.id,
            ],
        )

    return question.as_dict(
        upvoted=upvote is not None,
        starred=star is not None,
        user={
            "name": user.name,
            "username": user.username,
            "avatar_url": user.avatar_url,
        },
    )


class QuestionCreateParams(BaseModel):
    protocol_id: UUID
    title: Annotated[
        str, StringConstraints(max_length=255, min_length=1, strip_whitespace=True)
    ]
    content: str = ""
    tags: list[str] = []


@router.post("")
async def create_question(
    params: QuestionCreateParams,
    current_user: CurrentUser,
    db_session: DBSession,
    background_tasks: BackgroundTasks,
):
    protocol = await Protocol.find(db_session, id=params.protocol_id)
    project = await Project.find(db_session, id=protocol.project_id)
    await check_user_permission(
        db_session,
        project=project,
        user=current_user,
        action="read_protocol",
        protocol=protocol,
    )
    embedding_content = params.title + "\n\n" + params.content
    question = Question(
        user_id=current_user.id,
        **params.model_dump(exclude_none=True),
    )
    db_session.add(question)
    await db_session.flush()

    background_tasks.add_task(
        Embedding.add_resource,
        question.protocol_id,
        question.id,
        EmbeddingResourceType.QUESTION,
        embedding_content,
    )
    await current_user.load_avatar_attachment()
    await db_session.commit()
    return question.as_dict(
        upvoted=False,
        starred=False,
        user={
            "name": current_user.name,
            "username": current_user.username,
            "avatar_url": current_user.avatar_url,
        },
    )


class QuestionUpateParams(BaseModel):
    title: (
        Annotated[
            str, StringConstraints(max_length=255, min_length=1, strip_whitespace=True)
        ]
        | None
    ) = None
    content: str | None = None
    tags: list[str] | None = None


@router.put("/{question_id}")
async def update_question(
    question_id: UUID,
    params: QuestionUpateParams,
    current_user: CurrentUser,
    db_session: DBSession,
    background_tasks: BackgroundTasks,
):
    question = await Question.find(db_session, id=question_id)
    if question.user_id != current_user.id:
        raise HTTPException(status_code=400, detail="Permission denied")

    is_content_changed = False
    if params.title != question.title or params.content != question.content:
        is_content_changed = True
        embedding_content = params.title + "\n\n" + params.content
    question.set_attrs(**params.model_dump(exclude_none=True))
    question.updated_at = datetime.now()
    await db_session.commit()
    if is_content_changed:
        background_tasks.add_task(
            Embedding.rebuild_resource,
            question.protocol_id,
            question.id,
            EmbeddingResourceType.QUESTION,
            embedding_content,
        )

    return {"message": "success"}


@router.delete("/{question_id}")
async def delete_question(
    question_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    background_tasks: BackgroundTasks,
):
    question = await Question.find(db_session, id=question_id)
    if question.user_id != current_user.id:
        raise HTTPException(status_code=400, detail="Permission denied")

    answer_ids = (
        (
            await db_session.execute(
                select(Answer.id).where(Answer.question_id == question_id)
            )
        )
        .scalars()
        .all()
    )
    await db_session.execute(delete(Question).where(Question.id == question_id))
    await db_session.execute(delete(Answer).where(Answer.question_id == question_id))
    await db_session.commit()

    background_tasks.add_task(
        Embedding.remove_resource, question.id, EmbeddingResourceType.QUESTION
    )
    for answer_id in answer_ids:
        background_tasks.add_task(
            Embedding.remove_resource, answer_id, EmbeddingResourceType.ANSWER
        )
    return {"message": "success"}


@router.post("/{question_id}/upvote")
async def upvote_question(
    question_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    up: bool = Body(default=True, embed=True),
):
    question = await Question.find(db_session, id=question_id)
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
            Upvote.resource_id == question_id,
            Upvote.resource_type == UpvoteResourceType.QUESTION,
            Upvote.user_id == current_user.id,
        ],
    )
    if up:
        if upvote is not None:
            return {"upvotes_count": question.upvotes_count}
        else:
            upvote = Upvote(
                resource_id=question_id,
                resource_type=UpvoteResourceType.QUESTION,
                user_id=current_user.id,
            )
            db_session.add(upvote)
            await db_session.flush()
    else:
        if upvote is not None:
            await db_session.delete(upvote)
            await db_session.flush()
        else:
            return {"upvotes_count": question.upvotes_count}

    question.upvotes_count = await Upvote.count(
        db_session,
        [
            Upvote.resource_id == question_id,
            Upvote.resource_type == UpvoteResourceType.QUESTION,
        ],
    )
    await db_session.commit()
    return {"upvotes_count": question.upvotes_count}
