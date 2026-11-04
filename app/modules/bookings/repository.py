from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bookings.models import Booking, BookingStatus, WaitlistEntry, WaitlistStatus


class BookingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, booking_id: int) -> Booking | None:
        return await self.session.get(Booking, booking_id)

    async def scheduled_between(self, start: datetime, end: datetime) -> Sequence[Booking]:
        stmt = select(Booking).where(
            Booking.status == BookingStatus.SCHEDULED,
            Booking.starts_at < end,
            Booking.ends_at > start,
        )
        return (await self.session.scalars(stmt)).all()

    async def client_scheduled_between(
        self, client_id: int, start: datetime, end: datetime, exclude_id: int | None = None
    ) -> Sequence[Booking]:
        stmt = select(Booking).where(
            Booking.client_id == client_id,
            Booking.status == BookingStatus.SCHEDULED,
            Booking.starts_at < end,
            Booking.ends_at > start,
        )
        if exclude_id:
            stmt = stmt.where(Booking.id != exclude_id)
        return (await self.session.scalars(stmt)).all()

    async def upcoming_for_client(self, client_id: int, now: datetime) -> Sequence[Booking]:
        stmt = (
            select(Booking)
            .where(
                Booking.client_id == client_id,
                Booking.status == BookingStatus.SCHEDULED,
                Booking.ends_at > now,
            )
            .order_by(Booking.starts_at)
        )
        return (await self.session.scalars(stmt)).all()

    async def active_for_client_property(
        self, client_id: int, property_id: int, now: datetime
    ) -> Booking | None:
        stmt = select(Booking).where(
            Booking.client_id == client_id,
            Booking.property_id == property_id,
            Booking.status == BookingStatus.SCHEDULED,
            Booking.ends_at > now,
        )
        return await self.session.scalar(stmt)

    async def in_period(
        self, start: datetime, end: datetime, agent_id: int | None = None
    ) -> Sequence[Booking]:
        stmt = (
            select(Booking)
            .where(Booking.starts_at >= start, Booking.starts_at < end)
            .order_by(Booking.starts_at)
        )
        if agent_id is not None:
            stmt = stmt.where(Booking.agent_id == agent_id)
        return (await self.session.scalars(stmt)).all()

    async def upcoming_for_property(self, property_id: int, now: datetime) -> Sequence[Booking]:
        stmt = (
            select(Booking)
            .where(
                Booking.property_id == property_id,
                Booking.status == BookingStatus.SCHEDULED,
                Booking.ends_at > now,
            )
            .with_for_update(of=Booking)
        )
        return (await self.session.scalars(stmt)).all()

    async def due_reminders(self, now: datetime, until: datetime) -> Sequence[Booking]:
        stmt = (
            select(Booking)
            .where(
                Booking.status == BookingStatus.SCHEDULED,
                Booking.reminder_sent.is_(False),
                Booking.starts_at > now,
                Booking.starts_at <= until,
            )
            .with_for_update(skip_locked=True, of=Booking)
        )
        return (await self.session.scalars(stmt)).all()

    async def stats(self, start: datetime, end: datetime) -> dict[str, int]:
        rows = await self.session.execute(
            select(Booking.status, func.count())
            .where(Booking.starts_at >= start, Booking.starts_at < end)
            .group_by(Booking.status)
        )
        return {str(status): count for status, count in rows.all()}

    async def stats_by_agent(self, start: datetime, end: datetime) -> dict[int, dict[str, int]]:
        rows = await self.session.execute(
            select(Booking.agent_id, Booking.status, func.count())
            .where(Booking.starts_at >= start, Booking.starts_at < end)
            .group_by(Booking.agent_id, Booking.status)
        )
        result: dict[int, dict[str, int]] = {}
        for agent_id, status, count in rows.all():
            result.setdefault(agent_id, {})[str(status)] = count
        return result

    # --- waitlist ---
    async def waitlist_entry(self, client_id: int, property_id: int) -> WaitlistEntry | None:
        stmt = select(WaitlistEntry).where(
            WaitlistEntry.client_id == client_id,
            WaitlistEntry.property_id == property_id,
            WaitlistEntry.status.in_([WaitlistStatus.WAITING, WaitlistStatus.OFFERED]),
        )
        return await self.session.scalar(stmt)

    async def next_waiting(self, property_id: int) -> WaitlistEntry | None:
        stmt = (
            select(WaitlistEntry)
            .where(WaitlistEntry.property_id == property_id, WaitlistEntry.status == WaitlistStatus.WAITING)
            .order_by(WaitlistEntry.created_at)
            .limit(1)
            .with_for_update(skip_locked=True, of=WaitlistEntry)
        )
        return await self.session.scalar(stmt)

    async def waiting_for_property(self, property_id: int) -> Sequence[WaitlistEntry]:
        stmt = select(WaitlistEntry).where(
            WaitlistEntry.property_id == property_id,
            WaitlistEntry.status.in_([WaitlistStatus.WAITING, WaitlistStatus.OFFERED]),
        )
        return (await self.session.scalars(stmt)).all()

    async def waitlist_size(self) -> int:
        stmt = (
            select(func.count())
            .select_from(WaitlistEntry)
            .where(WaitlistEntry.status == WaitlistStatus.WAITING)
        )
        return int(await self.session.scalar(stmt) or 0)
