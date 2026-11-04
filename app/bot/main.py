import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatType
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand, BotCommandScopeDefault
from redis.asyncio import Redis

from app.bot.handlers import errors
from app.bot.handlers.client import build_client_router
from app.bot.handlers.staff import build_staff_router
from app.bot.middlewares import (
    DbSessionMiddleware,
    I18nMiddleware,
    LoggingMiddleware,
    ThrottlingMiddleware,
    UserMiddleware,
)
from app.config import get_settings
from app.infrastructure.database.session import get_session_factory
from app.infrastructure.llm.client import LLMClient, build_llm_client
from app.infrastructure.redis.client import get_redis
from app.infrastructure.telegram.bot import create_bot
from app.shared.i18n import Language, Translator
from app.shared.logging import get_logger, setup_logging

log = get_logger(__name__)

COMMANDS = ("start", "search", "bookings", "support", "language", "reset", "help")


def create_dispatcher(*, llm: LLMClient | None = None, redis: Redis | None = None) -> Dispatcher:
    settings = get_settings()
    redis = redis or get_redis()
    storage = RedisStorage.from_url(
        settings.redis_url, key_builder=DefaultKeyBuilder(prefix="fsm", with_destiny=True)
    )
    # kwargs become "workflow data" available in every handler by name
    dp = Dispatcher(storage=storage, llm=llm, redis=redis)

    dp.message.filter(F.chat.type == ChatType.PRIVATE)

    # Order: logging -> DB session -> user -> i18n (each depends on the previous)
    dp.update.outer_middleware(LoggingMiddleware())
    dp.update.outer_middleware(DbSessionMiddleware(get_session_factory()))
    dp.update.outer_middleware(UserMiddleware())
    dp.update.outer_middleware(I18nMiddleware())
    dp.message.outer_middleware(ThrottlingMiddleware(redis))

    dp.include_routers(errors.router, build_staff_router(), build_client_router())
    return dp


async def set_commands(bot: Bot) -> None:
    for language in Language:
        t = Translator(language)
        commands = [BotCommand(command=c, description=t(f"commands.{c}")) for c in COMMANDS]
        await bot.set_my_commands(commands, scope=BotCommandScopeDefault(), language_code=language.value)
    t = Translator(Language(get_settings().default_language))
    await bot.set_my_commands(
        [BotCommand(command=c, description=t(f"commands.{c}")) for c in COMMANDS],
        scope=BotCommandScopeDefault(),
    )


async def main() -> None:
    setup_logging()
    settings = get_settings()
    if settings.bot_mode == "webhook":
        log.warning("bot.webhook_mode", detail="BOT_MODE=webhook: updates are handled by the API process")
        return

    bot = create_bot()
    llm = build_llm_client()
    dp = create_dispatcher(llm=llm)
    if llm is None:
        log.warning("bot.llm_disabled", detail="LLM_API_KEY is empty: scripted scenarios only")
    try:
        await set_commands(bot)
        await bot.delete_webhook(drop_pending_updates=False)
        log.info("bot.polling_started")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        if llm is not None and hasattr(llm, "aclose"):
            await llm.aclose()
        await dp.storage.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
