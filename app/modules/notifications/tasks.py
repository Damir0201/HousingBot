from typing import Literal

from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter

from app.infrastructure.database.session import task_session
from app.infrastructure.telegram.bot import bot_session
from app.modules.bookings.service import BookingService
from app.modules.crm.service import TicketService
from app.modules.notifications.service import Notifier
from app.modules.properties.service import PropertyService
from app.modules.users.service import UserService
from app.shared.logging import get_logger
from app.worker import celery_app, run_async

log = get_logger(__name__)

BookingEvent = Literal["created", "cancelled_by_client", "cancelled_by_staff", "rescheduled", "extended"]

RETRY_KW = {
    "autoretry_for": (TelegramNetworkError, TelegramRetryAfter),
    "retry_backoff": True,
    "max_retries": 5,
}


@celery_app.task(name="notifications.send_due_reminders")
def send_due_reminders() -> int:
    """Beat: every minute. Idempotent thanks to `reminder_sent` + SKIP LOCKED."""

    async def _run() -> int:
        async with task_session() as session, bot_session() as bot:
            bookings = await BookingService(session).claim_due_reminders()
            await session.commit()  # mark first: better to miss a reminder than spam twice
            notifier = Notifier(bot)
            for booking in bookings:
                await notifier.reminder(booking)
            return len(bookings)

    sent = run_async(_run())
    if sent:
        log.info("reminders.sent", count=sent)
    return sent


@celery_app.task(name="notifications.booking_event", **RETRY_KW)
def notify_booking_event(booking_id: int, event: BookingEvent) -> None:
    async def _run() -> None:
        async with task_session() as session, bot_session() as bot:
            booking = await BookingService(session).get(booking_id)
            notifier = Notifier(bot)
            match event:
                case "created":
                    await notifier.booking_created(booking)
                case "cancelled_by_client":
                    await notifier.booking_cancelled(booking, by_client=True)
                case "cancelled_by_staff":
                    await notifier.booking_cancelled(booking, by_client=False)
                case "rescheduled":
                    await notifier.booking_rescheduled(booking)
                case "extended":
                    await notifier.booking_extended(booking)

    run_async(_run())


@celery_app.task(name="notifications.property_unavailable", **RETRY_KW)
def notify_property_unavailable(property_id: int, booking_ids: list[int]) -> None:
    """Task #4: tell clients & agents that viewings are cancelled and offer alternatives."""

    async def _run() -> None:
        async with task_session() as session, bot_session() as bot:
            props = PropertyService(session)
            bookings = BookingService(session)
            prop = await props.get(property_id)
            alternatives = list(await props.similar(prop, limit=3))
            notifier = Notifier(bot)
            for booking_id in booking_ids:
                await notifier.property_unavailable(await bookings.get(booking_id), alternatives)

    run_async(_run())


@celery_app.task(name="notifications.ticket_created", **RETRY_KW)
def notify_ticket_created(ticket_id: int) -> None:
    async def _run() -> None:
        async with task_session() as session, bot_session() as bot:
            ticket = await TicketService(session).get(ticket_id)
            staff = list(await UserService(session).staff())
            await Notifier(bot).ticket_created(ticket, staff)

    run_async(_run())
