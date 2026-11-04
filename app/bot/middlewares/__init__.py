import time
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, Update
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.modules.users.service import UserService
from app.shared.i18n import Language, Translator, resolve_language
from app.shared.logging import get_logger

log = get_logger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]
AfterCommit = list[Callable[[], Any]]


class LoggingMiddleware(BaseMiddleware):
    """Binds update/user ids to every log line produced while handling the update."""

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        structlog.contextvars.clear_contextvars()
        tg_user = data.get("event_from_user")
        update_id = event.update_id if isinstance(event, Update) else None
        structlog.contextvars.bind_contextvars(
            update_id=update_id, tg_user_id=tg_user.id if tg_user else None
        )
        started = time.perf_counter()
        try:
            return await handler(event, data)
        finally:
            log.info(
                "bot.update",
                event_type=event.event_type if isinstance(event, Update) else type(event).__name__,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )


class DbSessionMiddleware(BaseMiddleware):
    """Unit of work per update: one session, commit on success, rollback on error.

    Handlers append callables to `after_commit` (e.g. Celery `.delay`) so background
    jobs never see uncommitted data."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        after_commit: AfterCommit = []
        async with self.session_factory() as session:
            data["session"] = session
            data["after_commit"] = after_commit
            result = await handler(event, data)
            await session.commit()
        for callback in after_commit:
            try:
                callback()
            except Exception:
                log.exception("bot.after_commit_failed")
        return result


class UserMiddleware(BaseMiddleware):
    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)
        user = await UserService(data["session"]).get_or_create(
            tg_user.id, username=tg_user.username, full_name=tg_user.full_name
        )
        if user.is_blocked:
            return None
        data["user"] = user
        structlog.contextvars.bind_contextvars(user_id=user.id, role=str(user.role))
        return await handler(event, data)


class I18nMiddleware(BaseMiddleware):
    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        default = Language(get_settings().default_language)
        user = data.get("user")
        tg_user = data.get("event_from_user")
        if user is not None and user.language:
            language = user.language
        else:
            language = resolve_language(tg_user.language_code if tg_user else None, default)
        data["t"] = Translator(language)
        return await handler(event, data)


class ThrottlingMiddleware(BaseMiddleware):
    """Fixed-window rate limit in Redis (protects the LLM budget from spam)."""

    def __init__(self, redis: Redis, limit: int = 5, window_seconds: int = 3) -> None:
        self.redis = redis
        self.limit = limit
        self.window = window_seconds

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        if isinstance(event, Message) and event.from_user:
            key = f"throttle:{event.from_user.id}"
            count = await self.redis.incr(key)
            if count == 1:
                await self.redis.expire(key, self.window)
            if count > self.limit:
                t: Translator | None = data.get("t")
                if count == self.limit + 1 and t is not None:
                    await event.answer(t("errors.throttled"))
                return None
        return await handler(event, data)
