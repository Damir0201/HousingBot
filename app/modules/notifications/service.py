from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup

from app.bot import texts
from app.bot.keyboards import client as client_kb
from app.bot.keyboards import staff as staff_kb
from app.config import get_settings
from app.modules.bookings.models import Booking, WaitlistEntry
from app.modules.crm.models import Ticket
from app.modules.properties.models import Property
from app.modules.users.models import User
from app.shared.i18n import Translator
from app.shared.logging import get_logger

log = get_logger(__name__)


class Notifier:
    """All outgoing (not reply-to-user) Telegram messages, localized per recipient."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.settings = get_settings()

    @staticmethod
    def t(user: User) -> Translator:
        return Translator(user.language)

    async def send(self, user: User, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> bool:
        try:
            await self.bot.send_message(user.telegram_id, text, reply_markup=reply_markup)
            return True
        except TelegramForbiddenError:
            log.info("notify.user_blocked_bot", user_id=user.id)
        except TelegramRetryAfter:
            raise  # let Celery retry with backoff
        except TelegramAPIError as exc:
            log.warning("notify.failed", user_id=user.id, error=str(exc))
        return False

    # ---------------------------------------------------------------- bookings
    async def booking_created(self, booking: Booking) -> None:
        agent = booking.agent.user
        await self.send(agent, self.t(agent)("staff.booking_new", **texts.booking_vars(booking)))

    async def booking_cancelled(self, booking: Booking, *, by_client: bool) -> None:
        agent = booking.agent.user
        await self.send(agent, self.t(agent)("staff.booking_cancelled", **texts.booking_vars(booking)))
        if not by_client:
            t = self.t(booking.client)
            await self.send(booking.client, t("booking.cancelled_by_staff", **texts.booking_vars(booking)))

    async def booking_rescheduled(self, booking: Booking) -> None:
        agent = booking.agent.user
        await self.send(agent, self.t(agent)("staff.booking_rescheduled", **texts.booking_vars(booking)))

    async def booking_extended(self, booking: Booking) -> None:
        agent = booking.agent.user
        await self.send(agent, self.t(agent)("staff.booking_extended", **texts.booking_vars(booking)))

    async def reminder(self, booking: Booking) -> None:
        minutes = self.settings.reminder_minutes_before
        t = self.t(booking.client)
        await self.send(
            booking.client,
            t("booking.reminder", minutes=minutes, **texts.booking_vars(booking)),
            client_kb.booking_actions(booking.id, t),
        )
        agent = booking.agent.user
        await self.send(
            agent, self.t(agent)("staff.reminder", minutes=minutes, **texts.booking_vars(booking))
        )

    async def property_unavailable(self, booking: Booking, alternatives: list[Property]) -> None:
        t = self.t(booking.client)
        await self.send(booking.client, t("booking.property_unavailable", **texts.booking_vars(booking)))
        if alternatives:
            await self.send(booking.client, t("booking.alternatives"))
            for prop in alternatives:
                await self.send(
                    booking.client, texts.property_card(prop, t), client_kb.property_card(prop.id, t)
                )
        agent = booking.agent.user
        await self.send(agent, self.t(agent)("staff.booking_cancelled", **texts.booking_vars(booking)))

    async def waitlist_offer(self, entry: WaitlistEntry, days: list) -> None:
        t = self.t(entry.client)
        await self.send(
            entry.client,
            t("booking.waitlist_offer", title=escape(entry.property.title)),
            client_kb.days(entry.property_id, days, t),
        )

    # ---------------------------------------------------------------- support
    async def ticket_created(self, ticket: Ticket, staff: list[User]) -> None:
        for member in staff:
            t = self.t(member)
            await self.send(
                member,
                t(
                    "staff.ticket_new",
                    id=ticket.id,
                    category=escape(str(ticket.category)),
                    priority=escape(str(ticket.priority)),
                    client=escape(ticket.client.mention),
                    summary=escape(ticket.summary),
                ),
                staff_kb.ticket_actions(ticket.id, t, taken=False),
            )

    async def operator_reply(self, ticket: Ticket, text: str) -> bool:
        t = self.t(ticket.client)
        return await self.send(ticket.client, t("support.operator_reply", id=ticket.id, text=escape(text)))

    async def ticket_resolved(self, ticket: Ticket) -> None:
        t = self.t(ticket.client)
        await self.send(ticket.client, t("support.resolved", id=ticket.id))
