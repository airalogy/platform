from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account_security import AccountSecurity

from .single_lab import utcnow


async def get_auth_version(db_session: AsyncSession, user_id: UUID) -> int:
    version = await db_session.scalar(
        select(AccountSecurity.auth_version).where(AccountSecurity.user_id == user_id)
    )
    return version or 0


async def bump_auth_version(db_session: AsyncSession, user_id: UUID) -> int:
    statement = (
        insert(AccountSecurity)
        .values(user_id=user_id, auth_version=1)
        .on_conflict_do_update(
            index_elements=[AccountSecurity.user_id],
            set_={
                "auth_version": AccountSecurity.auth_version + 1,
                "updated_at": utcnow(),
            },
        )
        .returning(AccountSecurity.auth_version)
    )
    version = await db_session.scalar(statement)
    assert version is not None
    return version
