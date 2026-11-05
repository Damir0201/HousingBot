from datetime import timedelta
from functools import partial
from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.callbacks import AdminCb, BookingCb
from app.bot.keyboards import staff as kb
from app.bot.middlewares import AfterCommit
from app.bot.utils import safe_edit
from app.config import get_settings
from app.modules.agents.service import AgentService
from app.modules.bookings import tasks as booking_tasks
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.bookings.service import BookingService
from app.modules.notifications import tasks as notify
from app.modules.users.models import User
from app.shared.i18n import Translator
from app.shared.security import UserRole
from app.shared.timeutils import fmt_time, utcnow

router = Router(name="staff.schedule")

STATUS_ICONS = {
    BookingStatus.SCHEDULED: "📅",
    BookingStatus.COMPLETED: "✅",
    BookingStatus.CANCELLED: "❌",
    BookingStatus.NO_SHOW: "🚫",
}


def _line(b: Booking, show_agent: bool) -> str:
    line = (
        f"{STATUS_ICONS[b.status]} <b>{fmt_time(b.starts_at)}–{fmt_time(b.ends_at)}</b> "
        f"{escape(b.property.title)}\n    👤 {escape(b.client.mention)} {escape(b.client.phone or '')}"
    )
    if show_agent:
        line += f"\n    🧑‍💼 {escape(b.agent.display_name)}"
    return line


async def _render_schedule(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    t: Translator,
    day_offset: int,
) -> bool:
    is_owner = user.role == UserRole.OWNER
    agent_id: int | None = None
    if not is_owner:
        agent = await AgentService(session).get_by_user(user.id)
        if agent is None:
            await callback.answer(t("admin.not_agent"), show_alert=True)
            return False
        agent_id = agent.id

    day = utcnow().astimezone(get_settings().tz).date() + timedelta(days=day_offset)
    bookings = await BookingService(session).day_schedule(day, agent_id)
    header = t("admin.schedule_title", day=texts.day_label(day, t))
    body = "\n\n".join(_line(b, is_owner) for b in bookings) or t("admin.schedule_empty")
    await safe_edit(callback, f"{header}\n\n{body}", kb.schedule(bookings, day_offset, t))
    return True


def _day_offset_for(booking: Booking) -> int:
    tz = get_settings().tz
    today = utcnow().astimezone(tz).date()
    return (booking.starts_at.astimezone(tz).date() - today).days


@router.callback_query(AdminCb.filter(F.section == "schedule"))
async def schedule(
    callback: CallbackQuery, callback_data: AdminCb, session: AsyncSession, user: User, t: Translator
) -> None:
    if await _render_schedule(callback, session, user, t, callback_data.day):
        await callback.answer()


@router.callback_query(BookingCb.filter(F.action.in_({"done", "noshow"})))
async def set_outcome(
    callback: CallbackQuery, callback_data: BookingCb, session: AsyncSession, user: User, t: Translator
) -> None:
    status = BookingStatus.COMPLETED if callback_data.action == "done" else BookingStatus.NO_SHOW
    booking = await BookingService(session).set_outcome(callback_data.id, user, status)
    await _render_schedule(callback, session, user, t, _day_offset_for(booking))
    await callback.answer(t("admin.saved"), show_alert=True)


@router.callback_query(BookingCb.filter(F.action == "reassign"))
async def reassign_booking(
    callback: CallbackQuery,
    callback_data: BookingCb,
    session: AsyncSession,
    user: User,
    t: Translator,
    after_commit: AfterCommit,
) -> None:
    booking = await BookingService(session).reassign_to_other_agent(callback_data.id, user)
    after_commit.append(partial(notify.notify_booking_event.delay, booking.id, "reassigned"))
    await callback.answer(
        t("admin.booking_reassigned", agent=booking.agent.display_name),
        show_alert=True,
    )
    if callback.message and callback.message.reply_markup:
        buttons = callback.message.reply_markup.inline_keyboard
        if len(buttons) == 1 and len(buttons[0]) == 1:
            await safe_edit(
                callback,
                t("staff.booking_reassigned", **texts.booking_vars(booking)),
                kb.booking_reassign(booking.id, t),
            )
            return
    await _render_schedule(callback, session, user, t, _day_offset_for(booking))


@router.callback_query(BookingCb.filter(F.action == "staff_cancel"))
async def staff_cancel(
    callback: CallbackQuery,
    callback_data: BookingCb,
    session: AsyncSession,
    user: User,
    t: Translator,
    after_commit: AfterCommit,
) -> None:
    booking = await BookingService(session).cancel(callback_data.id, user, "cancelled_by_staff")
    after_commit.append(partial(notify.notify_booking_event.delay, booking.id, "cancelled_by_staff"))
    after_commit.append(partial(booking_tasks.process_waitlist.delay, booking.property_id))
    await _render_schedule(callback, session, user, t, _day_offset_for(booking))
    await callback.answer(t("admin.booking_cancelled"), show_alert=True)
