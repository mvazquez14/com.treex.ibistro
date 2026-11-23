import logging

from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def ping_redis() -> bool:
    return bool(await get_redis().ping())


async def claim_webhook_event(event_id: str) -> bool:
    """Return False when this event id was already processed.

    If Redis is down, the webhook still applies. A missed idempotency key is
    safer than dropping a billing update.
    """
    try:
        stored = await get_redis().set(
            f"nuna:webhook:{event_id}",
            "1",
            nx=True,
            ex=60 * 60 * 24,
        )
    except Exception:
        logger.exception(
            "Redis unavailable; processing Nuna webhook without idempotency"
        )
        return True
    return bool(stored)
