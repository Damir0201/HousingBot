from app.infrastructure.database.session import task_session
from app.infrastructure.telegram.bot import bot_session
from app.modules.bookings.service import BookingService
from app.modules.notifications.service import Notifier
from app.shared.logging import get_logger
from app.worker import celery_app, run_async

log = get_logger(__name__)


@celery_app.task(name="bookings.process_waitlist")
def process_waitlist(property_id: int) -> int | None:
    """A slot was freed (cancel/reschedule): offer it to the first client in the queue."""

    async def _run() -> int | None:
        async with task_session() as session, bot_session() as bot:
            service = BookingService(session)
            entry = await service.offer_next_in_waitlist(property_id)
            if entry is None:
                return None
            await session.commit()
            await Notifier(bot).waitlist_offer(entry, service.bookable_days()[:7])
            log.info("waitlist.offered", property_id=property_id, entry_id=entry.id)
            return entry.id

    return run_async(_run())
