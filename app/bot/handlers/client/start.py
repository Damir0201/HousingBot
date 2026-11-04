from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import LangCb
from app.bot.filters import TextKey
from app.bot.keyboards import client as kb
from app.bot.utils import callback_message
from app.modules.users.models import User
from app.modules.users.service import UserService
from app.shared.i18n import Language, Translator
from app.shared.security import is_staff

router = Router(name="client.start")


async def send_welcome(message: Message, user: User, t: Translator) -> None:
    await message.answer(
        t("start.welcome", name=f", {escape(user.full_name)}" if user.full_name else ""),
        reply_markup=kb.main_menu(t, is_staff(user.role)),
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user: User, t: Translator) -> None:
    await state.clear()
    if user.language is None:
        await message.answer(t("start.choose_language"), reply_markup=kb.language())
        return
    await send_welcome(message, user, t)


@router.message(Command("language"))
@router.message(TextKey("menu.language"))
async def choose_language(message: Message, state: FSMContext, t: Translator) -> None:
    await state.clear()
    await message.answer(t("start.choose_language"), reply_markup=kb.language())


@router.callback_query(LangCb.filter())
async def set_language(
    callback: CallbackQuery, callback_data: LangCb, user: User, session: AsyncSession
) -> None:
    try:
        language = Language(callback_data.code)
    except ValueError:
        await callback.answer()
        return
    await UserService(session).set_language(user, language)
    t = Translator(language)
    await callback.answer(t("start.language_set"))
    message = callback_message(callback)
    if message:
        await message.edit_text(t("start.language_set"))
        await send_welcome(message, user, t)


@router.message(Command("help"))
async def cmd_help(message: Message, t: Translator) -> None:
    await message.answer(t("start.help"))
