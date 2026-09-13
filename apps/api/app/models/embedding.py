from datetime import datetime
from enum import IntEnum
from typing import Any
from uuid import UUID

from masterbrain.usage import UsageContext
from pgvector.sqlalchemy import Vector
from sqlalchemy import Integer, delete, false, func, literal, or_, select
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.database import DBSession, sessionmanager
from app.libs.embedding_config import EMBEDDING_DIMENSIONS
from app.libs.text_splitter import (
    optional_text_to_vectors,
    text_to_embeddings,
    text_to_words,
)

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
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    @staticmethod
    def search_conditions(
        query_str: str, vector: list[float] | None, distance: float = 0.5
    ):
        """Use real cosine distance when available, plus a local keyword path.

        Keyword-only rows stay discoverable even after AI is enabled again.
        No fake vector or confidence score is generated for the fallback.
        """
        words = text_to_words(query_str)
        # Quoted web-search terms preserve OR matching without treating research
        # punctuation (for example !, :, quotes or parentheses) as tsquery syntax.
        terms = [f'"{word.replace(chr(34), " ")}"' for word in words if word.strip()]
        tsquery = (
            func.websearch_to_tsquery("english", " OR ".join(terms)) if terms else None
        )
        keyword_match = Embedding.tsv.bool_op("@@")(tsquery) if terms else false()
        keyword_rank = func.ts_rank_cd(Embedding.tsv, tsquery) if terms else literal(0)
        if vector is None:
            return keyword_match, [keyword_rank.desc()]
        cosine_distance = Embedding.embedding.cosine_distance(vector)
        return or_(cosine_distance < distance, keyword_match), [
            cosine_distance.asc().nulls_last(),
            keyword_rank.desc(),
        ]

    @staticmethod
    async def retrieval_full_text(
        db_session: DBSession,
        protocol_id: UUID,
        resource_type: list[EmbeddingResourceType],
        query_str: str,
        limit: int = 3,
    ) -> list[str]:
        predicate, ordering = Embedding.search_conditions(query_str, None)
        query = (
            select(
                Embedding.text,
            )
            .where(
                Embedding.protocol_id == protocol_id,
                Embedding.resource_type.in_(resource_type),
                predicate,
            )
            .order_by(
                *ordering,
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
        *,
        usage_context: UsageContext | None = None,
    ) -> list[dict[str, Any]]:
        vectors = await optional_text_to_vectors(
            [query_str[0:1000]], usage_context=usage_context
        )
        vector = vectors[0] if vectors else None
        predicate, ordering = Embedding.search_conditions(query_str, vector)

        query = (
            select(
                Embedding.resource_id,
                Embedding.resource_type,
                Embedding.text,
                (
                    Embedding.embedding.cosine_distance(vector)
                    if vector
                    else literal(None)
                ).label("distance"),
            )
            .where(
                Embedding.protocol_id == protocol_id,
                Embedding.resource_type.in_(resource_types),
                predicate,
            )
            .order_by(*ordering, Embedding.id.desc())
            .limit(limit)
        )
        result = (await db_session.execute(query)).all()
        return [
            {
                "resource_id": r.resource_id,
                "resource_type": r.resource_type,
                "text": r.text,
                "similarity": 1 - r.distance
                if r.distance is not None and r.distance < 0.5
                else None,
            }
            for r in result
        ]

    @staticmethod
    async def add_resource(
        protocol_id: UUID,
        resource_id: UUID,
        resource_type: EmbeddingResourceType,
        text: str,
        *,
        usage_context: UsageContext | None = None,
    ):
        embeddings = []
        for chunk, words, embedding in await text_to_embeddings(
            text, usage_context=usage_context
        ):
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
            # Serialize replacement per Protocol; model calls happen before this
            # short transaction. Readers never see a committed delete-only gap.
            from app.models.protocol import Protocol

            await db_session.execute(
                select(Protocol.id).where(Protocol.id == protocol_id).with_for_update()
            )
            await db_session.execute(
                delete(Embedding).where(
                    Embedding.protocol_id == protocol_id,
                    Embedding.resource_id == resource_id,
                    Embedding.resource_type == resource_type,
                )
            )
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
        *,
        usage_context: UsageContext | None = None,
    ):
        await Embedding.add_resource(
            protocol_id, resource_id, resource_type, text, usage_context=usage_context
        )
