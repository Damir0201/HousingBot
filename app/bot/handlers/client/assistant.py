from functools import partial

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters import TextKey, menu_button
from app.bot.keyboards import client as kb
from app.bot.middlewares import AfterCommit
from app.bot.states import SupportStates
from app.bot.utils import send_property_cards
from app.config import get_settings
from app.infrastructure.llm.client import LLMClient
from app.modules.ai_assistant.memory import ConversationMemory
from app.modules.ai_assistant.service import AssistantService
from app.modules.crm.schemas import TicketCreate
from app.modules.crm.service import TicketService
from app.modules.notifications import tasks as notify
from app.modules.properties.service import PropertyService
from app.modules.users.models import User
from app.shared.exceptions import NotFoundError
from app.shared.i18n import Translator
from app.shared.security import is_staff

router = Router(name="client.assistant")

MAX_USER_TEXT = 2000


# ------------------------------------------------------------------ manual support request
@router.message(Command("support"))
@router.message(TextKey("menu.support"))
async def support(message: Message, state: FSMContext, t: Translator) -> None:
    await state.set_state(SupportStates.waiting_message)
    await message.answer(t("support.ask"))


@router.message(SupportStates.waiting_message, F.text, ~menu_button())
async def support_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    t: Translator,
    after_commit: AfterCommit,
) -> None:
    await state.clear()
    ticket = await TicketService(session).create(
        user,
        TicketCreate(
            summary=(message.text or "")[:4000], context={"source": "manual", "language": t.language}
        ),
    )
    after_commit.append(partial(notify.notify_ticket_created.delay, ticket.id))
    await message.answer(t("support.ticket_created", id=ticket.id))


# ------------------------------------------------------------------ AI dialog (catch-all)
@router.message(Command("reset"))
async def reset(message: Message, state: FSMContext, user: User, t: Translator, redis: Redis) -> None:
    await state.clear()
    await ConversationMemory(redis).clear(user.id)
    await message.answer(t("ai.reset"))


@router.message(StateFilter(None), F.text)
async def chat(
    message: Message,
    session: AsyncSession,
    user: User,
    t: Translator,
    llm: LLMClient | None,
    redis: Redis,
    after_commit: AfterCommit,
) -> None:
    if message.bot is None or not message.text:
        return
    memory = ConversationMemory(redis, get_settings().llm_history_limit)
    service = AssistantService(session, llm, memory)

    async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
        reply = await service.reply(user, message.text[:MAX_USER_TEXT])

    if reply.ticket_id:
        after_commit.append(partial(notify.notify_ticket_created.delay, reply.ticket_id))

    if reply.text:
        # LLM output is untrusted -> plain text, no HTML parsing
        await message.answer(reply.text, parse_mode=None)
    elif reply.fallback:
        await message.answer(t("ai.fallback"), reply_markup=kb.main_menu(t, is_staff(user.role)))

    props = []
    properties = PropertyService(session)
    for property_id in reply.property_ids:
        try:
            prop = await properties.get(property_id)
        except NotFoundError:
            continue
        if prop.is_bookable:
            props.append(prop)
    await send_property_cards(message, props, t)


@router.message(StateFilter(None))
async def unsupported(message: Message, t: Translator) -> None:
    await message.answer(t("ai.text_only"))
