from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.modules.agents.models import Agent
from app.modules.agents.service import AgentService
from app.modules.bookings import scheduling
from app.modules.bookings.models import Booking, BookingStatus, WaitlistEntry, WaitlistStatus
from app.modules.bookings.repository import BookingRepository
from app.modules.properties.models import Property
from app.modules.users.models import User
from app.shared.exceptions import (
    BookingStateError,
    ExtensionConflictError,
    NotFoundError,
    PermissionDeniedError,
    PropertyUnavailableError,
    SlotUnavailableError,
)
from app.shared.security import UserRole
from app.shared.timeutils import utcnow

Interval = scheduling.Interval


class BookingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = BookingRepository(session)
        self.settings = get_settings()
        self.tz = self.settings.tz
        self.slot = timedelta(minutes=self.settings.booking_slot_minutes)
        self.buffer = timedelta(minutes=self.settings.booking_buffer_minutes)

    # ------------------------------------------------------------------ queries
    async def get(self, booking_id: int) -> Booking:
        booking = await self.repo.get(booking_id)
        if booking is None:
            raise NotFoundError("Booking not found", booking_id=booking_id)
        return booking

    def bookable_days(self) -> list[date]:
        today = utcnow().astimezone(self.tz).date()
        return [today + timedelta(days=i) for i in range(self.settings.booking_days_ahead)]

    async def available_slots(
        self, property_id: int, day: date, client_id: int | None = None
    ) -> list[Interval]:
        await self._bookable_property(property_id)
        schedules = await self._schedules(day)
        client_busy: list[Interval] = []
        if client_id is not None:
            start, end = self._day_bounds(day)
            client_busy = [
                Interval(b.starts_at, b.ends_at)
                for b in await self.repo.client_scheduled_between(client_id, start, end)
            ]
        return scheduling.available_slots(
            day,
            schedules,
            slot_minutes=self.settings.booking_slot_minutes,
            buffer=self.buffer,
            tz=self.tz,
            now=utcnow(),
            client_busy=client_busy,
        )

    async def upcoming_for_client(self, client_id: int) -> Sequence[Booking]:
        return await self.repo.upcoming_for_client(client_id, utcnow())

    async def day_schedule(self, day: date, agent_id: int | None = None) -> Sequence[Booking]:
        start, end = self._day_bounds(day)
        return await self.repo.in_period(start, end, agent_id)

    # ------------------------------------------------------------------ commands
    async def book(self, *, client: User, property_id: int, starts_at: datetime) -> Booking:
        prop = await self._bookable_property(property_id, lock=True)
        starts_at = starts_at.astimezone(self.tz)
        slot = Interval(starts_at, starts_at + self.slot)
        day = starts_at.date()

        if await self.repo.active_for_client_property(client.id, prop.id, utcnow()):
            raise BookingStateError("Client already has a viewing for this property")
        await self._ensure_valid_slot(slot, day, client.id)

        for agent_id in await self._candidate_agents(slot, day):
            booking = Booking(
                property_id=prop.id,
                client_id=client.id,
                agent_id=agent_id,
                starts_at=slot.start,
                ends_at=slot.end,
            )
            if await self._try_flush(booking):
                await self._close_waitlist_entry(client.id, prop.id, WaitlistStatus.BOOKED)
                await self.session.refresh(booking)
                return booking
        raise SlotUnavailableError("No free agent for the slot")

    async def reschedule(self, booking_id: int, new_start: datetime, actor: User | None) -> Booking:
        booking = await self.get(booking_id)
        await self._ensure_can_manage(booking, actor)
        self._ensure_active(booking)
        await self._bookable_property(booking.property_id, lock=True)

        new_start = new_start.astimezone(self.tz)
        slot = Interval(new_start, new_start + self.slot)
        day = new_start.date()
        await self._ensure_valid_slot(slot, day, booking.client_id, exclude_booking_id=booking.id)

        candidates = await self._candidate_agents(slot, day, exclude_booking_id=booking.id)
        # keep the same agent when possible
        if booking.agent_id in candidates:
            candidates.remove(booking.agent_id)
            candidates.insert(0, booking.agent_id)

        for agent_id in candidates:
            try:
                async with self.session.begin_nested():
                    booking.agent_id = agent_id
                    booking.starts_at, booking.ends_at = slot.start, slot.end
                    booking.reminder_sent = False
                    booking.extended_minutes = 0
                    booking.reschedule_count += 1
                    await self.session.flush()
            except IntegrityError:
                continue  # savepoint rolled back -> attributes expire and reload
            await self.session.refresh(booking)
            return booking
        raise SlotUnavailableError("No free agent for the new slot")

    async def extend(self, booking_id: int, actor: User | None, minutes: int | None = None) -> Booking:
        """'I'm running late': push the end of the viewing if the agent's next slot allows."""
        minutes = minutes or self.settings.late_extension_minutes
        booking = await self.get(booking_id)
        await self._ensure_can_manage(booking, actor)
        self._ensure_active(booking)
        try:
            async with self.session.begin_nested():
                booking.ends_at = booking.ends_at + timedelta(minutes=minutes)
                booking.extended_minutes += minutes
                await self.session.flush()
        except IntegrityError as exc:
            raise ExtensionConflictError("Agent has another viewing right after") from exc
        await self.session.refresh(booking)
        return booking

    async def cancel(
        self, booking_id: int, actor: User | None, reason: str = "cancelled_by_client"
    ) -> Booking:
        booking = await self.get(booking_id)
        await self._ensure_can_manage(booking, actor)
        self._ensure_active(booking)
        booking.status = BookingStatus.CANCELLED
        booking.cancel_reason = reason
        await self.session.flush()
        return booking

    async def set_outcome(self, booking_id: int, actor: User | None, status: BookingStatus) -> Booking:
        if status not in (BookingStatus.COMPLETED, BookingStatus.NO_SHOW):
            raise BookingStateError("Outcome must be completed or no_show")
        booking = await self.get(booking_id)
        if actor is not None and actor.role == UserRole.CLIENT:
            raise PermissionDeniedError("Only staff can set outcome")
        await self._ensure_can_manage(booking, actor)
        self._ensure_active(booking)
        booking.status = status
        await self.session.flush()
        return booking

    async def cancel_for_property(self, property_id: int, reason: str) -> list[Booking]:
        bookings = list(await self.repo.upcoming_for_property(property_id, utcnow()))
        for booking in bookings:
            booking.status = BookingStatus.CANCELLED
            booking.cancel_reason = reason
        for entry in await self.repo.waiting_for_property(property_id):
            entry.status = WaitlistStatus.CANCELLED
        await self.session.flush()
        return bookings

    # ------------------------------------------------------------------ waitlist
    async def join_waitlist(
        self, client: User, property_id: int, preferred_date: date | None = None
    ) -> WaitlistEntry:
        await self._bookable_property(property_id)
        entry = await self.repo.waitlist_entry(client.id, property_id)
        if entry is None:
            entry = WaitlistEntry(client_id=client.id, property_id=property_id, preferred_date=preferred_date)
            self.session.add(entry)
            await self.session.flush()
            await self.session.refresh(entry)
        return entry

    async def offer_next_in_waitlist(self, property_id: int) -> WaitlistEntry | None:
        """Pick the first waiting client (FIFO) and mark them as offered."""
        entry = await self.repo.next_waiting(property_id)
        if entry is None:
            return None
        entry.status = WaitlistStatus.OFFERED
        entry.offered_at = utcnow()
        await self.session.flush()
        return entry

    # ------------------------------------------------------------------ reminders
    async def claim_due_reminders(self) -> list[Booking]:
        """Return bookings needing a reminder and mark them, idempotently (SKIP LOCKED)."""
        now = utcnow()
        until = now + timedelta(minutes=self.settings.reminder_minutes_before)
        bookings = list(await self.repo.due_reminders(now, until))
        for booking in bookings:
            booking.reminder_sent = True
        await self.session.flush()
        return bookings

    # ------------------------------------------------------------------ internals
    def _day_bounds(self, day: date) -> tuple[datetime, datetime]:
        start = datetime.combine(day, time.min, self.tz)
        return start, start + timedelta(days=1)

    async def _bookable_property(self, property_id: int, *, lock: bool = False) -> Property:
        stmt = select(Property).where(Property.id == property_id)
        if lock:
            # FOR SHARE serializes with change_property_status (FOR UPDATE):
            # nobody can book a property while it is being marked as rented.
            stmt = stmt.with_for_update(read=True)
        prop = await self.session.scalar(stmt)
        if prop is None:
            raise NotFoundError("Property not found", property_id=property_id)
        if not prop.is_bookable:
            raise PropertyUnavailableError("Property is not available", property_id=property_id)
        return prop

    async def _schedules(
        self, day: date, exclude_booking_id: int | None = None
    ) -> list[scheduling.AgentSchedule]:
        agents: Sequence[Agent] = await AgentService(self.session).list_active()
        start, end = self._day_bounds(day)
        busy: dict[int, list[Interval]] = defaultdict(list)
        for b in await self.repo.scheduled_between(start - self.buffer, end + self.buffer):
            if b.id != exclude_booking_id:
                busy[b.agent_id].append(Interval(b.starts_at, b.ends_at))
        return [
            scheduling.AgentSchedule(
                agent_id=a.id,
                work_start=a.work_start or self.settings.booking_work_start,
                work_end=a.work_end or self.settings.booking_work_end,
                busy=tuple(busy[a.id]),
            )
            for a in agents
        ]

    async def _candidate_agents(
        self, slot: Interval, day: date, exclude_booking_id: int | None = None
    ) -> list[int]:
        schedules = await self._schedules(day, exclude_booking_id)
        return scheduling.free_agents(slot, schedules, day, self.tz, self.buffer)

    async def _ensure_valid_slot(
        self, slot: Interval, day: date, client_id: int, exclude_booking_id: int | None = None
    ) -> None:
        now = utcnow()
        if slot.start <= now + timedelta(minutes=30):
            raise SlotUnavailableError("Slot is too soon")
        if day not in self.bookable_days():
            raise SlotUnavailableError("Day is outside of the booking window")
        minutes_from_midnight = slot.start.hour * 60 + slot.start.minute
        if minutes_from_midnight % self.settings.booking_slot_minutes or slot.start.second:
            raise SlotUnavailableError("Slot is not aligned to the grid")
        if await self.repo.client_scheduled_between(client_id, slot.start, slot.end, exclude_booking_id):
            raise SlotUnavailableError("Client already has a viewing at this time")

    async def _try_flush(self, booking: Booking) -> bool:
        try:
            async with self.session.begin_nested():
                self.session.add(booking)
                await self.session.flush()
        except IntegrityError:
            return False  # exclusion constraint: another worker took this agent's slot
        return True

    async def _close_waitlist_entry(self, client_id: int, property_id: int, status: WaitlistStatus) -> None:
        entry = await self.repo.waitlist_entry(client_id, property_id)
        if entry is not None:
            entry.status = status

    async def _ensure_can_manage(self, booking: Booking, actor: User | None) -> None:
        if actor is None or actor.role == UserRole.OWNER:  # None = system / API
            return
        if actor.role == UserRole.CLIENT and booking.client_id == actor.id:
            return
        if actor.role == UserRole.AGENT:
            agent = await AgentService(self.session).get_by_user(actor.id)
            if agent is not None and agent.id == booking.agent_id:
                return
        raise PermissionDeniedError("Not allowed to manage this booking")

    @staticmethod
    def _ensure_active(booking: Booking) -> None:
        if not booking.is_active:
            raise BookingStateError("Booking is not active", status=booking.status)
