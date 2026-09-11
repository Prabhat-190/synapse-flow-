"""Redis pub/sub for live agent state streaming and SSE reconstruction."""

from __future__ import annotations

import json
from typing import AsyncIterator

import structlog

from atlas.config import get_settings
from atlas.core.models import AgentEvent

logger = structlog.get_logger()

_redis_client = None


async def get_redis():
    global _redis_client
    if _redis_client is None:
        try:
            import redis.asyncio as aioredis

            settings = get_settings()
            client = aioredis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=1,
            )
            await client.ping()
            _redis_client = client
        except Exception as exc:
            logger.warning("redis_unavailable", error=str(exc))
            _redis_client = None
    return _redis_client


def channel_name(run_id: str) -> str:
    return f"atlas:run:{run_id}:events"


async def publish_event(event: AgentEvent) -> None:
    redis = await get_redis()
    if redis is None:
        return
    try:
        await redis.publish(channel_name(event.run_id), event.model_dump_json())
    except Exception as exc:
        logger.warning("publish_failed", error=str(exc))


async def subscribe_events(run_id: str) -> AsyncIterator[AgentEvent]:
    redis = await get_redis()
    if redis is None:
        return
        yield  # type: ignore[misc]

    pubsub = redis.pubsub()
    await pubsub.subscribe(channel_name(run_id))
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data = json.loads(message["data"])
            yield AgentEvent.model_validate(data)
    finally:
        await pubsub.unsubscribe(channel_name(run_id))
        await pubsub.aclose()


async def store_checkpoint(run_id: str, snapshot: dict) -> None:
    redis = await get_redis()
    if redis is None:
        return
    try:
        key = f"atlas:run:{run_id}:checkpoint"
        await redis.set(key, json.dumps(snapshot), ex=86400)
    except Exception as exc:
        logger.warning("checkpoint_store_failed", error=str(exc))


async def get_checkpoint(run_id: str) -> dict | None:
    redis = await get_redis()
    if redis is None:
        return None
    data = await redis.get(f"atlas:run:{run_id}:checkpoint")
    return json.loads(data) if data else None
