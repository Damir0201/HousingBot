from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import AdminCb, TicketCb
from app.bot.filters import menu_button
from app.bot.keyboards import staff as kb
from app.bot.states import StaffStates
from app.bot.utils import callback_message, safe_edit
from app.modules.crm.models import Ticket, TicketStatus
from app.modules.crm.service import TicketService
from app.modules.notifications.service import Notifier
from app.modules.users.models import User
from app.shared.i18n import Translator
from app.shared.security import UserRole

router = Router(name="staff.tickets")


def ticket_card(ticket: Ticket, t: Translator) -> str:
    criteria = ticket.context.get("criteria") or {}
    text = t(
        "staff.ticket_card",
        id=ticket.id,
        category=t(f"ticket.category.{ticket.category}"),
        priority=t(f"ticket.priority.{ticket.priority}"),
        status=t(f"ticket.status.{ticket.status}"),
        client=escape(ticket.client.mention),
        phone=escape(ticket.client.phone or "—"),
        summary=escape(ticket.summary),
    )
    if criteria:
        text += "\n\n🔎 " + escape(", ".join(f"{k}: {v}" for k, v in criteria.items()))
    if ticket.assignee:
        text += "\n👷 " + escape(ticket.assignee.mention)
    return text


@router.callback_query(AdminCb.filter(F.section == "tickets"))
async def list_tickets(callback: CallbackQuery, session: AsyncSession, user: User, t: Translator) -> None:
    assignee = None if user.role == UserRole.OWNER else user.id
    tickets = await TicketService(session).list_open(assignee_id=assignee)
    await callback.answer()
    if not tickets:
        await safe_edit(callback, t("admin.tickets_empty"), kb.back_markup(t))
        return
    await safe_edit(callback, t("admin.tickets_title", count=len(tickets)), kb.back_markup(t))
    message = callback_message(callback)
    if message is None:
        return
    for ticket in tickets:
        await message.answer(
            ticket_card(ticket, t),
            reply_markup=kb.ticket_actions(ticket.id, t, taken=ticket.assignee_id is not None),
        )


@router.callback_query(TicketCb.filter(F.action == "take"))
async def take(
    callback: CallbackQuery, callback_data: TicketCb, session: AsyncSession, user: User, t: Translator
) -> None:
    ticket = await TicketService(session).take(callback_data.id, user)
    await safe_edit(callback, ticket_card(ticket, t), kb.ticket_actions(ticket.id, t, taken=True))
    await callback.answer(t("admin.ticket_taken"))
    transcript = ticket.context.get("transcript") or []
    message = callback_message(callback)
    if transcript and message:
        await message.answer("<b>" + t("admin.transcript") + "</b>\n" + escape("\n".join(transcript)[-3500:]))


@router.callback_query(TicketCb.filter(F.action == "reply"))
async def reply_prompt(
    callback: CallbackQuery, callback_data: TicketCb, state: FSMContext, t: Translator
) -> None:
    await state.set_state(StaffStates.ticket_reply)
    await state.update_data(ticket_id=callback_data.id)
    await callback.answer()
    if message := callback_message(callback):
        await message.answer(t("admin.ticket_reply_prompt", id=callback_data.id))


@router.message(StaffStates.ticket_reply, F.text, ~menu_button())
async def reply_send(
    message: Message, state: FSMContext, session: AsyncSession, user: User, t: Translator, bot: Bot
) -> None:
    data = await state.get_data()
    await state.clear()
    service = TicketService(session)
    ticket = await service.get(int(data["ticket_id"]))
    if ticket.status == TicketStatus.OPEN:
        ticket = await service.take(ticket.id, user)
    delivered = await Notifier(bot).operator_reply(ticket, escape(message.text or ""))
    await message.answer(t("admin.reply_sent") if delivered else t("admin.reply_failed"))


@router.callback_query(TicketCb.filter(F.action == "resolve"))
async def resolve(
    callback: CallbackQuery, callback_data: TicketCb, session: AsyncSession, t: Translator, bot: Bot
) -> None:
    ticket = await TicketService(session).resolve(callback_data.id)
    await Notifier(bot).ticket_resolved(ticket)
    await safe_edit(callback, ticket_card(ticket, t))
    await callback.answer(t("admin.ticket_resolved"))
