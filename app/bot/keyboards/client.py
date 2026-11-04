from collections.abc import Sequence
from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from app.bot.callbacks import BookingCb, DayCb, LangCb, PropCb, SearchCb, SlotCb
from app.bot.texts import day_label
from app.modules.bookings.scheduling import Interval
from app.shared.i18n import LANGUAGE_NAMES, Translator
from app.shared.timeutils import fmt_time

BUDGET_OPTIONS = ["0-500", "500-800", "800-1200", "1200-2000", "2000-"]
ROOMS_OPTIONS = ["1", "2", "3", "4"]
TERM_OPTIONS = ["short", "long"]


def language() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for lang, name in LANGUAGE_NAMES.items():
        b.button(text=name, callback_data=LangCb(code=lang.value))
    b.adjust(1)
    return b.as_markup()


def main_menu(t: Translator, is_staff: bool = False) -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.button(text=t("menu.search"))
    b.button(text=t("menu.bookings"))
    b.button(text=t("menu.support"))
    b.button(text=t("menu.language"))
    if is_staff:
        b.button(text=t("menu.admin"))
    b.adjust(2, 2, 1)
    return b.as_markup(resize_keyboard=True, input_field_placeholder=t("menu.placeholder"))


def share_contact(t: Translator) -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.button(text=t("btn.share_contact"), request_contact=True)
    return b.as_markup(resize_keyboard=True, one_time_keyboard=True)


def property_card(property_id: int, t: Translator) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=t("btn.book"), callback_data=PropCb(action="book", id=property_id))
    b.button(text=t("btn.details"), callback_data=PropCb(action="details", id=property_id))
    b.adjust(2)
    return b.as_markup()


def days(property_id: int, days: Sequence[date], t: Translator, booking_id: int = 0) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for day in days:
        b.button(
            text=day_label(day, t),
            callback_data=DayCb(property_id=property_id, day=day.isoformat(), booking_id=booking_id),
        )
    b.adjust(3)
    return b.as_markup()


def _back_to_days(property_id: int, booking_id: int) -> InlineKeyboardButton | None:
    data = (
        BookingCb(action="reschedule", id=booking_id) if booking_id else PropCb(action="book", id=property_id)
    )
    return InlineKeyboardButton(text="⬅️", callback_data=data.pack())


def slots(
    property_id: int, slots: Sequence[Interval], t: Translator, booking_id: int = 0
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for slot in slots:
        b.button(
            text=fmt_time(slot.start),
            callback_data=SlotCb(
                property_id=property_id, ts=int(slot.start.timestamp()), booking_id=booking_id
            ),
        )
    b.adjust(4)
    back = _back_to_days(property_id, booking_id)
    if back:
        b.row(back)
    return b.as_markup()


def no_slots(property_id: int, t: Translator, booking_id: int = 0) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if not booking_id:
        b.button(text=t("btn.waitlist"), callback_data=PropCb(action="waitlist", id=property_id))
    b.adjust(1)
    back = _back_to_days(property_id, booking_id)
    if back:
        b.row(back)
    return b.as_markup()


def booking_actions(booking_id: int, t: Translator) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=t("btn.late"), callback_data=BookingCb(action="late", id=booking_id))
    b.button(text=t("btn.reschedule"), callback_data=BookingCb(action="reschedule", id=booking_id))
    b.button(text=t("btn.cancel_booking"), callback_data=BookingCb(action="cancel", id=booking_id))
    b.adjust(1, 2)
    return b.as_markup()


# ------------------------------------------------------------------ search wizard
def search_any(t: Translator, field: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=t("search.any"), callback_data=SearchCb(field=field, value="any"))
    return b.as_markup()


def search_budget(t: Translator) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for value in BUDGET_OPTIONS:
        low, high = value.split("-")
        label = f"{low}–{high} €" if high else f"{low}+ €"
        b.button(text=label, callback_data=SearchCb(field="budget", value=value))
    b.button(text=t("search.any"), callback_data=SearchCb(field="budget", value="any"))
    b.adjust(3)
    return b.as_markup()


def search_rooms(t: Translator) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for value in ROOMS_OPTIONS:
        b.button(
            text=f"{value}+" if value == ROOMS_OPTIONS[-1] else value,
            callback_data=SearchCb(field="rooms", value=value),
        )
    b.button(text=t("search.any"), callback_data=SearchCb(field="rooms", value="any"))
    b.adjust(4, 1)
    return b.as_markup()


def search_term(t: Translator) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for value in TERM_OPTIONS:
        b.button(text=t(f"search.term_{value}"), callback_data=SearchCb(field="term", value=value))
    b.button(text=t("search.any"), callback_data=SearchCb(field="term", value="any"))
    b.adjust(2, 1)
    return b.as_markup()
