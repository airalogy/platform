"""One Project UID lock shared by all ordinary Protocol creation paths."""

from sqlalchemy import text


async def lock_protocol_uid(db, project_id, uid):
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"protocol-uid:{project_id}:{uid}"},
    )
