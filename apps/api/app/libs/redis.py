import json

import redis.asyncio as redis

from app.config import config

pool = redis.ConnectionPool.from_url(config.REDIS_URL)


async def get_redis_client():
    return redis.Redis(connection_pool=pool)


async def set_cache(key: str, value: str | dict | list, ex: int = 60 * 60 * 24):
    client = await get_redis_client()
    value = json.dumps(value, ensure_ascii=False)
    await client.setex(key, ex, value)
    await client.aclose()


async def get_cache(key: str):
    client = await get_redis_client()
    val = await client.get(key)
    if val is not None:
        return json.loads(val)
    return None


async def clear_cache(key: str | list[str]):
    client = await get_redis_client()
    if isinstance(key, list):
        await client.delete(*key)
    else:
        await client.delete(key)
    await client.aclose()
