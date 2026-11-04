from aiogram import F, Router
from aiogram.filters import ExceptionTypeFilter
from aiogram.types import CallbackQuery, ErrorEvent, Message

from app.shared.exceptions import DomikError
from app.shared.i18n import Translator
from app.shared.logging import get_logger

log = get_logger(__name__)

router = Router(name="errors")


@router.error(ExceptionTypeFilter(DomikError), F.update.callback_query.as_("callback"))
async def domain_error_callback(
    event: ErrorEvent, callback: CallbackQuery, t: Translator | None = None
) -> None:
    exc = event.exception
    assert isinstance(exc, DomikError)
    translator = t or Translator(None)
    log.info("bot.domain_error", error=type(exc).__name__, message=str(exc))
    await callback.answer(translator(exc.i18n_key), show_alert=True)


@router.error(ExceptionTypeFilter(DomikError), F.update.message.as_("message"))
async def domain_error_message(event: ErrorEvent, message: Message, t: Translator | None = None) -> None:
    exc = event.exception
    assert isinstance(exc, DomikError)
    translator = t or Translator(None)
    log.info("bot.domain_error", error=type(exc).__name__, message=str(exc))
    await message.answer(translator(exc.i18n_key))


@router.error()
async def unexpected_error(event: ErrorEvent, t: Translator | None = None) -> None:
    log.error("bot.unhandled_error", exc_info=event.exception)
    translator = t or Translator(None)
    update = event.update
    try:
        if update.callback_query:
            await update.callback_query.answer(translator("errors.generic"), show_alert=True)
        elif update.message:
            await update.message.answer(translator("errors.generic"))
    except Exception:  # never fail inside the error handler
        log.warning("bot.error_reply_failed")
