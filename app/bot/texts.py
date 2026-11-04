"""Presentation helpers shared by handlers and the notification service."""

from datetime import date
from html import escape

from app.modules.bookings.models import Booking
from app.modules.properties.models import Property
from app.shared.i18n import Translator
from app.shared.timeutils import fmt_dt, fmt_time


def money(value: object) -> str:
    try:
        return f"{float(value):,.0f}".replace(",", " ")  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "—"


def property_card(prop: Property, t: Translator) -> str:
    flags = []
    if prop.furnished:
        flags.append(t("property.flag.furnished"))
    if prop.pets_allowed:
        flags.append(t("property.flag.pets"))
    if prop.utilities_included:
        flags.append(t("property.flag.utilities"))
    term_label = t("search.term_short") if prop.min_term_months <= 3 else t("search.term_long")
    return t(
        "property.card",
        title=escape(prop.title),
        district=escape(prop.district or "—"),
        city=escape(prop.city or ""),
        type=t(f"property.type.{prop.property_type}"),
        rooms=prop.rooms,
        area=f"{prop.area_m2:g} m²" if prop.area_m2 else "—",
        price=money(prop.price_month),
        deposit=money(prop.deposit) if prop.deposit else "—",
        min_term=term_label,
        available=prop.available_from.strftime("%d.%m.%Y") if prop.available_from else t("property.now"),
        flags=" · ".join(flags),
    ).strip()


def booking_line(booking: Booking, t: Translator) -> str:
    return t(
        "booking.item",
        title=escape(booking.property.title),
        time=fmt_dt(booking.starts_at),
        agent=escape(booking.agent.display_name),
    )


def booking_vars(booking: Booking) -> dict[str, object]:
    return {
        "title": escape(booking.property.title),
        "address": escape(booking.property.address or booking.property.district or "—"),
        "time": fmt_dt(booking.starts_at),
        "end": fmt_time(booking.ends_at),
        "agent": escape(booking.agent.display_name),
        "client": escape(booking.client.mention),
        "phone": escape(booking.client.phone or "—"),
    }


def day_label(day: date, t: Translator) -> str:
    return f"{t(f'days.{day.weekday()}')} {day.strftime('%d.%m')}"
