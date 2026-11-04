from functools import lru_cache

from redis.asyncio import Redis

from app.config import get_settings


@lru_cache
def get_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


def new_redis() -> Redis:
    """Fresh client (for Celery tasks that run in a new event loop each time)."""
    return Redis.from_url(get_settings().redis_url, decode_responses=True)
