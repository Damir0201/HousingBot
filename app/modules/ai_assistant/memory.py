from redis.asyncio import Redis

from app.infrastructure.llm.schemas import ChatMessage

HISTORY_TTL_SECONDS = 24 * 3600


class ConversationMemory:
    """Short-term dialog memory in Redis (list of JSON messages, capped & expiring)."""

    def __init__(self, redis: Redis, limit: int = 20) -> None:
        self.redis = redis
        self.limit = limit

    @staticmethod
    def _key(user_id: int) -> str:
        return f"ai:history:{user_id}"

    async def load(self, user_id: int) -> list[ChatMessage]:
        raw = await self.redis.lrange(self._key(user_id), -self.limit, -1)
        messages = [ChatMessage.model_validate_json(item) for item in raw]
        # never start the window with orphan tool results
        while messages and messages[0].role == "tool":
            messages.pop(0)
        return messages

    async def append(self, user_id: int, *messages: ChatMessage) -> None:
        if not messages:
            return
        key = self._key(user_id)
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.rpush(key, *(m.model_dump_json(exclude_none=True) for m in messages))
            pipe.ltrim(key, -self.limit * 2, -1)
            pipe.expire(key, HISTORY_TTL_SECONDS)
            await pipe.execute()

    async def clear(self, user_id: int) -> None:
        await self.redis.delete(self._key(user_id))
