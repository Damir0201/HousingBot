from collections.abc import Sequence

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InputMediaPhoto, Message

from app.bot import texts
from app.bot.keyboards import client as client_kb
from app.modules.properties.models import Property
from app.shared.i18n import Translator
from app.shared.logging import get_logger

log = get_logger(__name__)


async def safe_edit(
    callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None = None
) -> None:
    """Edit the callback's message, or send a new one if it can't be edited."""
    message = callback.message
    if isinstance(message, Message):
        try:
            await message.edit_text(text, reply_markup=reply_markup)
            return
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc):
                return
        await message.answer(text, reply_markup=reply_markup)
    elif callback.from_user and callback.bot:
        await callback.bot.send_message(callback.from_user.id, text, reply_markup=reply_markup)


async def send_property_cards(message: Message, props: Sequence[Property], t: Translator) -> None:
    for prop in props:
        await message.answer(texts.property_card(prop, t), reply_markup=client_kb.property_card(prop.id, t))


async def send_photos(message: Message, prop: Property) -> None:
    photos = [p for p in prop.photos if p][:10]
    if not photos:
        return
    try:
        if len(photos) == 1:
            await message.answer_photo(photos[0])
        else:
            await message.answer_media_group([InputMediaPhoto(media=p) for p in photos])
    except TelegramBadRequest as exc:
        log.warning("bot.photos_failed", property_id=prop.id, error=str(exc))


def callback_message(callback: CallbackQuery) -> Message | None:
    return callback.message if isinstance(callback.message, Message) else None
