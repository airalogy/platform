from datetime import datetime
from enum import IntEnum
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import Integer, delete, func, select
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.database import DBSession, sessionmanager
from app.libs.text_splitter import text_to_embeddings, text_to_vectors, text_to_words

from .base import Base


class EmbeddingResourceType(IntEnum):
    QUESTION = 1
    ANSWER = 2
    PROTOCOL = 3


class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[int] = mapped_column(
        nullable=False, primary_key=True, autoincrement=True, index=True
    )
    protocol_id: Mapped[UUID] = mapped_column(nullable=False)
    resource_id: Mapped[UUID] = mapped_column(nullable=False)
    resource_type: Mapped[EmbeddingResourceType] = mapped_column(
        Integer, nullable=False
    )
    text: Mapped[str] = mapped_column(nullable=False)
    tsv: Mapped[TSVECTOR] = mapped_column(TSVECTOR, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    @staticmethod
    async def retrieval_full_text(
        db_session: DBSession,
        protocol_id: UUID,
        resource_type: list[EmbeddingResourceType],
        query_str: str,
        limit: int = 3,
    ) -> list[str]:
        words = text_to_words(query_str)
        if len(words) == 0:
            return []

        q = " | ".join(words)
        query = (
            select(
                Embedding.text,
            )
            .where(
                Embedding.protocol_id == protocol_id,
                Embedding.resource_type.in_(resource_type),
                Embedding.tsv.bool_op("@@")(func.to_tsquery("english", q)),
            )
            .order_by(
                func.ts_rank_cd(Embedding.tsv, func.to_tsquery("english", q)).desc(),
                Embedding.id.desc(),
            )
            .limit(limit)
        )
        query_result = (await db_session.execute(query)).all()
        return [d.text for d in query_result]

    @staticmethod
    async def retrieval_vector(
        db_session: DBSession,
        protocol_id: UUID,
        resource_types: list[EmbeddingResourceType],
        query_str: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        vector = text_to_vectors([query_str[0:1000]])[0]

        query = (
            select(
                Embedding.resource_id,
                Embedding.resource_type,
                Embedding.text,
                Embedding.embedding.cosine_distance(vector).label("distance"),
            )
            .where(
                Embedding.protocol_id == protocol_id,
                Embedding.resource_type.in_(resource_types),
                Embedding.embedding.cosine_distance(vector) < 0.5,
            )
            .order_by(Embedding.embedding.cosine_distance(vector).asc())
            .limit(limit)
        )
        result = (await db_session.execute(query)).all()
        return [
            {
                "resource_id": r.resource_id,
                "resource_type": r.resource_type,
                "text": r.text,
                "similarity": 1 - r.distance,
            }
            for r in result
        ]

    @staticmethod
    async def add_resource(
        protocol_id: UUID,
        resource_id: UUID,
        resource_type: EmbeddingResourceType,
        text: str,
    ):
        embeddings = []
        for chunk, words, embedding in text_to_embeddings(text):
            embeddings.append(
                Embedding(
                    protocol_id=protocol_id,
                    resource_id=resource_id,
                    resource_type=resource_type,
                    text=chunk,
                    tsv=func.to_tsvector("english", " ".join(words)),
                    embedding=embedding,
                )
            )
        async with sessionmanager.session() as db_session:
            db_session.add_all(embeddings)
            await db_session.commit()

    @staticmethod
    async def remove_resource(
        resource_id: UUID | list[UUID],
        resource_type: EmbeddingResourceType,
    ):
        async with sessionmanager.session() as db_session:
            await db_session.execute(
                delete(Embedding).where(
                    Embedding.resource_id.in_(resource_id)
                    if isinstance(resource_id, list)
                    else Embedding.resource_id == resource_id,
                    Embedding.resource_type == resource_type,
                )
            )
            await db_session.commit()

    @staticmethod
    async def rebuild_resource(
        protocol_id: UUID,
        resource_id: UUID,
        resource_type: EmbeddingResourceType,
        text: str,
    ):
        async with sessionmanager.session() as db_session:
            await Embedding.remove_resource(db_session, resource_id, resource_type)
            await Embedding.add_resource(
                db_session, protocol_id, resource_id, resource_type, text
            )
            await db_session.commit()
