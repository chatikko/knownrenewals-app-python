from redis import asyncio as aioredis

from app.core.config import get_settings

settings = get_settings()

redis_client = aioredis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)


def get_redis_client() -> aioredis.Redis:
    return redis_client
