from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import get_settings


def create_bot() -> Bot:
    return Bot(
        token=get_settings().bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )


@asynccontextmanager
async def bot_session() -> AsyncIterator[Bot]:
    """Short-lived bot for Celery tasks; closes its aiohttp session afterwards."""
    bot = create_bot()
    try:
        yield bot
    finally:
        await bot.session.close()
