from fastapi import APIRouter
from fastapi.responses import ORJSONResponse
from sqlalchemy import text

from app.config import config
from app.database import DBSession
from app.libs.file_storage import get_storage_backend
from app.libs.redis import get_redis_client

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def health_live():
    return {"status": "ok"}


@router.get("/ready")
async def health_ready(db_session: DBSession):
    checks = {"database": False, "redis": False, "storage": False}
    try:
        await db_session.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        pass

    client = None
    try:
        client = await get_redis_client()
        checks["redis"] = bool(await client.ping())
    except Exception:
        pass
    finally:
        if client is not None:
            await client.aclose()

    try:
        if config.STORAGE_BACKEND == "minio":
            storage = get_storage_backend("minio")
            checks["storage"] = bool(
                await storage.client.bucket_exists(storage.bucket)
            )
        else:
            # OSS operations authenticate per request. Configuration validation
            # catches missing credentials; avoid listing private buckets here.
            checks["storage"] = True
    except Exception:
        pass

    ready = all(checks.values())
    response = {"status": "ok" if ready else "unavailable", "checks": checks}
    if not ready:
        return ORJSONResponse(status_code=503, content=response)
    return response
