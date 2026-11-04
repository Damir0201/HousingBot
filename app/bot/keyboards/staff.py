from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import AdminCb, AdmPropCb, AgentCb, BookingCb, TicketCb
from app.modules.agents.models import Agent
from app.modules.bookings.models import Booking
from app.modules.properties.models import Property, PropertyStatus
from app.shared.i18n import Translator
from app.shared.timeutils import fmt_time

STATUS_ICONS = {
    PropertyStatus.AVAILABLE: "🟢",
    PropertyStatus.RESERVED: "🟡",
    PropertyStatus.RENTED: "🔴",
    PropertyStatus.ARCHIVED: "⚪",
}


def back(t: Translator, section: str = "menu") -> InlineKeyboardButton:
    return InlineKeyboardButton(text=t("btn.back"), callback_data=AdminCb(section=section).pack())


def back_markup(t: Translator, section: str = "menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[back(t, section)]])


def admin_menu(t: Translator, is_owner: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if is_owner:
        b.button(text=t("admin.btn.stats"), callback_data=AdminCb(section="stats"))
    b.button(text=t("admin.btn.schedule"), callback_data=AdminCb(section="schedule"))
    b.button(text=t("admin.btn.props"), callback_data=AdminCb(section="props"))
    b.button(text=t("admin.btn.tickets"), callback_data=AdminCb(section="tickets"))
    if is_owner:
        b.button(text=t("admin.btn.agents"), callback_data=AdminCb(section="agents"))
        b.button(text=t("admin.btn.excel_export"), callback_data=AdminCb(section="excel_export"))
        b.button(text=t("admin.btn.excel_import"), callback_data=AdminCb(section="excel_import"))
    b.adjust(2)
    return b.as_markup()


def properties_list(
    props: Sequence[Property], page: int, t: Translator, has_next: bool
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for prop in props:
        b.button(
            text=f"{STATUS_ICONS[prop.status]} {prop.code} · {prop.title[:30]}",
            callback_data=AdmPropCb(action="view", id=prop.id),
        )
    b.adjust(1)
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(text="⬅️", callback_data=AdminCb(section="props", page=page - 1).pack())
        )
    if has_next:
        nav.append(
            InlineKeyboardButton(text="➡️", callback_data=AdminCb(section="props", page=page + 1).pack())
        )
    if nav:
        b.row(*nav)
    b.row(back(t))
    return b.as_markup()


def property_actions(prop: Property, t: Translator) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for status in PropertyStatus:
        if status != prop.status:
            b.button(
                text=f"{STATUS_ICONS[status]} {t(f'property.status.{status}')}",
                callback_data=AdmPropCb(action="status", id=prop.id, value=status.value),
            )
    b.adjust(3)
    photo_buttons = [
        InlineKeyboardButton(
            text=t("admin.btn.add_photo", count=len(prop.photos or [])),
            callback_data=AdmPropCb(action="photo_add", id=prop.id).pack(),
        )
    ]
    if prop.photos:
        photo_buttons.append(
            InlineKeyboardButton(
                text=t("admin.btn.clear_photos"),
                callback_data=AdmPropCb(action="photo_clear", id=prop.id).pack(),
            )
        )
    b.row(*photo_buttons)
    b.row(back(t, "props"))
    return b.as_markup()


def property_back(property_id: int, t: Translator) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn.back"),
                    callback_data=AdmPropCb(action="view", id=property_id).pack(),
                )
            ]
        ]
    )


def schedule(bookings: Sequence[Booking], day_offset: int, t: Translator) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for booking in bookings:
        if not booking.is_active:
            continue
        b.row(
            InlineKeyboardButton(
                text=f"✅ {fmt_time(booking.starts_at)}",
                callback_data=BookingCb(action="done", id=booking.id).pack(),
            ),
            InlineKeyboardButton(text="🚫", callback_data=BookingCb(action="noshow", id=booking.id).pack()),
            InlineKeyboardButton(
                text="❌", callback_data=BookingCb(action="staff_cancel", id=booking.id).pack()
            ),
        )
    b.row(
        InlineKeyboardButton(text="⬅️", callback_data=AdminCb(section="schedule", day=day_offset - 1).pack()),
        InlineKeyboardButton(text="🔄", callback_data=AdminCb(section="schedule", day=day_offset).pack()),
        InlineKeyboardButton(text="➡️", callback_data=AdminCb(section="schedule", day=day_offset + 1).pack()),
    )
    b.row(back(t))
    return b.as_markup()


def ticket_actions(ticket_id: int, t: Translator, taken: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if not taken:
        b.button(text=t("admin.btn.take"), callback_data=TicketCb(action="take", id=ticket_id))
    b.button(text=t("admin.btn.reply"), callback_data=TicketCb(action="reply", id=ticket_id))
    b.button(text=t("admin.btn.resolve"), callback_data=TicketCb(action="resolve", id=ticket_id))
    b.adjust(3)
    return b.as_markup()


def agents_list(agents: Sequence[Agent], t: Translator) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for agent in agents:
        if agent.is_active:
            b.button(
                text=t("admin.btn.deactivate", name=agent.display_name),
                callback_data=AgentCb(action="off", id=agent.id),
            )
    b.adjust(1)
    b.row(back(t))
    return b.as_markup()
