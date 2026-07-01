import redis.asyncio as aioredis
from src.core.settings import settings

_redis: aioredis.Redis | None = None


async def init_redis() -> None:
    global _redis
    _redis = await aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )
    await _redis.ping()


async def close_redis() -> None:
    if _redis:
        await _redis.close()


def get_redis() -> aioredis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialized")
    return _redis
