"""Typed callback data factories (no hand-written 'action:id' strings)."""

from aiogram.filters.callback_data import CallbackData


class LangCb(CallbackData, prefix="lang"):
    code: str


class PropCb(CallbackData, prefix="p"):
    action: str  # details | book | waitlist
    id: int


class DayCb(CallbackData, prefix="d"):
    property_id: int
    day: str  # ISO date
    booking_id: int = 0  # != 0 -> rescheduling an existing booking


class SlotCb(CallbackData, prefix="sl"):
    property_id: int
    ts: int  # unix timestamp of slot start
    booking_id: int = 0


class BookingCb(CallbackData, prefix="b"):
    action: str  # cancel | reschedule | late | done | noshow | staff_cancel
    id: int


class SearchCb(CallbackData, prefix="s"):
    field: str  # district | budget | rooms | term
    value: str


class AdminCb(CallbackData, prefix="a"):
    section: str  # menu | stats | props | schedule | tickets | agents | excel_export | excel_import
    page: int = 0
    day: int = 0  # day offset for schedule


class AdmPropCb(CallbackData, prefix="ap"):
    action: str  # view | status
    id: int
    value: str = ""


class TicketCb(CallbackData, prefix="t"):
    action: str  # take | reply | resolve
    id: int


class AgentCb(CallbackData, prefix="ag"):
    action: str  # off
    id: int
