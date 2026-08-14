"""Public, non-secret runtime identity endpoints."""

from fastapi import APIRouter
from sqlalchemy import text

from app.build_info import resolve_build_info
from app.config import config
from app.database import DBSession

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/version")
async def system_version(db_session: DBSession):
    database_revision = "unavailable"
    try:
        result = await db_session.execute(text("SELECT version_num FROM alembic_version"))
        database_revision = result.scalar_one_or_none() or "unversioned"
    except Exception:
        # Build identity must remain available while the database is being
        # restored or diagnosed. Readiness reports database health separately.
        pass

    return {
        **resolve_build_info().as_dict(),
        "database_revision": database_revision,
        "deployment_id": config.AIRALOGY_DEPLOYMENT_ID or None,
    }
