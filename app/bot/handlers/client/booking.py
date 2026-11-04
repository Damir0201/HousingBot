from datetime import UTC, date, datetime
from functools import partial
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.callbacks import BookingCb, DayCb, PropCb, SlotCb
from app.bot.filters import TextKey, menu_button
from app.bot.keyboards import client as kb
from app.bot.middlewares import AfterCommit
from app.bot.states import BookingStates
from app.bot.utils import callback_message, safe_edit
from app.modules.bookings import tasks as booking_tasks
from app.modules.bookings.service import BookingService
from app.modules.crm.service import LeadService
from app.modules.notifications import tasks as notify
from app.modules.properties.service import PropertyService
from app.modules.users.models import User
from app.modules.users.service import UserService
from app.shared.exceptions import DomikError, PropertyUnavailableError
from app.shared.i18n import Translator
from app.shared.security import is_staff
from app.shared.timeutils import fmt_time

router = Router(name="client.booking")


# ------------------------------------------------------------------ new booking
@router.callback_query(PropCb.filter(F.action == "book"))
async def choose_day(
    callback: CallbackQuery, callback_data: PropCb, session: AsyncSession, t: Translator
) -> None:
    prop = await PropertyService(session).get(callback_data.id)
    if not prop.is_bookable:
        raise PropertyUnavailableError()
    days = BookingService(session).bookable_days()
    await safe_edit(callback, t("booking.choose_day", title=escape(prop.title)), kb.days(prop.id, days, t))
    await callback.answer()


@router.callback_query(DayCb.filter())
async def choose_slot(
    callback: CallbackQuery, callback_data: DayCb, session: AsyncSession, user: User, t: Translator
) -> None:
    day = date.fromisoformat(callback_data.day)
    slots = await BookingService(session).available_slots(callback_data.property_id, day, client_id=user.id)
    label = texts.day_label(day, t)
    if not slots:
        await safe_edit(
            callback,
            t("booking.no_slots", day=label),
            kb.no_slots(callback_data.property_id, t, callback_data.booking_id),
        )
    else:
        await safe_edit(
            callback,
            t("booking.choose_time", day=label),
            kb.slots(callback_data.property_id, slots, t, callback_data.booking_id),
        )
    await callback.answer()


@router.callback_query(SlotCb.filter())
async def pick_slot(
    callback: CallbackQuery,
    callback_data: SlotCb,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    t: Translator,
    after_commit: AfterCommit,
) -> None:
    starts_at = datetime.fromtimestamp(callback_data.ts, tz=UTC)
    service = BookingService(session)

    if callback_data.booking_id:  # reschedule flow
        old = await service.get(callback_data.booking_id)
        property_id = old.property_id
        booking = await service.reschedule(callback_data.booking_id, starts_at, user)
        after_commit.append(partial(notify.notify_booking_event.delay, booking.id, "rescheduled"))
        after_commit.append(partial(booking_tasks.process_waitlist.delay, property_id))
        await safe_edit(
            callback,
            t("booking.rescheduled", **texts.booking_vars(booking)),
            kb.booking_actions(booking.id, t),
        )
        await callback.answer()
        return

    await callback.answer()
    message = callback_message(callback)
    if message is None:
        return
    if not user.phone:
        await state.set_state(BookingStates.waiting_contact)
        await state.update_data(property_id=callback_data.property_id, ts=callback_data.ts)
        await message.answer(t("booking.ask_contact"), reply_markup=kb.share_contact(t))
        return
    await _create_booking(message, session, user, t, after_commit, callback_data.property_id, starts_at)


@router.message(BookingStates.waiting_contact, F.contact)
async def got_contact(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    t: Translator,
    after_commit: AfterCommit,
) -> None:
    contact = message.contact
    if contact is None or (contact.user_id and message.from_user and contact.user_id != message.from_user.id):
        await message.answer(t("booking.own_contact_only"), reply_markup=kb.share_contact(t))
        return
    await UserService(session).set_phone(user, contact.phone_number)
    data = await state.get_data()
    await state.clear()
    await message.answer(t("booking.contact_saved"), reply_markup=kb.main_menu(t, is_staff(user.role)))
    starts_at = datetime.fromtimestamp(int(data["ts"]), tz=UTC)
    await _create_booking(message, session, user, t, after_commit, int(data["property_id"]), starts_at)


@router.message(BookingStates.waiting_contact, ~menu_button())
async def contact_expected(message: Message, t: Translator) -> None:
    await message.answer(t("booking.ask_contact"), reply_markup=kb.share_contact(t))


async def _create_booking(
    message: Message,
    session: AsyncSession,
    user: User,
    t: Translator,
    after_commit: AfterCommit,
    property_id: int,
    starts_at: datetime,
) -> None:
    service = BookingService(session)
    try:
        booking = await service.book(client=user, property_id=property_id, starts_at=starts_at)
    except DomikError as exc:
        # keep the rest of the transaction (e.g. saved phone) and let the user pick again
        await message.answer(t(exc.i18n_key))
        if not isinstance(exc, PropertyUnavailableError):
            await message.answer(
                t("booking.pick_another"), reply_markup=kb.days(property_id, service.bookable_days(), t)
            )
        return
    await LeadService(session).mark_viewing(user)
    after_commit.append(partial(notify.notify_booking_event.delay, booking.id, "created"))
    await message.answer(
        t("booking.confirmed", **texts.booking_vars(booking)), reply_markup=kb.booking_actions(booking.id, t)
    )


# ------------------------------------------------------------------ waitlist
@router.callback_query(PropCb.filter(F.action == "waitlist"))
async def join_waitlist(
    callback: CallbackQuery, callback_data: PropCb, session: AsyncSession, user: User, t: Translator
) -> None:
    entry = await BookingService(session).join_waitlist(user, callback_data.id)
    await safe_edit(callback, t("booking.waitlist_joined", title=escape(entry.property.title)))
    await callback.answer()


# ------------------------------------------------------------------ my bookings
@router.message(Command("bookings"))
@router.message(TextKey("menu.bookings"))
async def my_bookings(
    message: Message, state: FSMContext, session: AsyncSession, user: User, t: Translator
) -> None:
    await state.clear()
    bookings = await BookingService(session).upcoming_for_client(user.id)
    if not bookings:
        await message.answer(t("booking.none"))
        return
    for booking in bookings:
        await message.answer(texts.booking_line(booking, t), reply_markup=kb.booking_actions(booking.id, t))


@router.callback_query(BookingCb.filter(F.action == "cancel"))
async def cancel(
    callback: CallbackQuery,
    callback_data: BookingCb,
    session: AsyncSession,
    user: User,
    t: Translator,
    after_commit: AfterCommit,
) -> None:
    booking = await BookingService(session).cancel(callback_data.id, user, "cancelled_by_client")
    after_commit.append(partial(notify.notify_booking_event.delay, booking.id, "cancelled_by_client"))
    after_commit.append(partial(booking_tasks.process_waitlist.delay, booking.property_id))
    await safe_edit(callback, t("booking.cancelled", title=escape(booking.property.title)))
    await callback.answer()


@router.callback_query(BookingCb.filter(F.action == "reschedule"))
async def reschedule(
    callback: CallbackQuery, callback_data: BookingCb, session: AsyncSession, user: User, t: Translator
) -> None:
    service = BookingService(session)
    booking = await service.get(callback_data.id)
    if booking.client_id != user.id or not booking.is_active:
        await callback.answer(t("errors.booking_state"), show_alert=True)
        return
    await safe_edit(
        callback,
        t("booking.choose_new_day", title=escape(booking.property.title)),
        kb.days(booking.property_id, service.bookable_days(), t, booking_id=booking.id),
    )
    await callback.answer()


@router.callback_query(BookingCb.filter(F.action == "late"))
async def running_late(
    callback: CallbackQuery,
    callback_data: BookingCb,
    session: AsyncSession,
    user: User,
    t: Translator,
    after_commit: AfterCommit,
) -> None:
    booking = await BookingService(session).extend(callback_data.id, user)
    after_commit.append(partial(notify.notify_booking_event.delay, booking.id, "extended"))
    await callback.answer(t("booking.extended", end=fmt_time(booking.ends_at)), show_alert=True)
