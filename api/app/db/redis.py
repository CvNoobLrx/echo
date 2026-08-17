"""Redis 异步客户端（显式连接池 + 健康检查）。"""
from redis import asyncio as aioredis

from app.config import settings
from app.core.loop_local import LoopLocal

_resources = LoopLocal[tuple[aioredis.ConnectionPool, aioredis.Redis]]()


def get_redis() -> aioredis.Redis:
    def _create() -> tuple[aioredis.ConnectionPool, aioredis.Redis]:
        pool = aioredis.ConnectionPool.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=settings.redis_max_connections,
            health_check_interval=30,
        )
        return pool, aioredis.Redis(connection_pool=pool)

    return _resources.get_or_create(_create)[1]


async def ping() -> bool:
    try:
        return await get_redis().ping()
    except Exception:
        return False


async def close() -> None:
    resource = _resources.pop_current()
    if resource is not None:
        pool, client = resource
        await client.aclose()
        await pool.disconnect()
