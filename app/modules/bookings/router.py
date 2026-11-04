from datetime import date

from fastapi import APIRouter, Query, status

from app.api.dependencies import ApiKeyAuth, DbSession
from app.modules.bookings import tasks as booking_tasks
from app.modules.bookings.schemas import (
    BookingCancel,
    BookingCreate,
    BookingRead,
    BookingReschedule,
    SlotRead,
)
from app.modules.bookings.service import BookingService
from app.modules.crm.service import LeadService
from app.modules.notifications import tasks as notify
from app.modules.users.service import UserService

router = APIRouter(prefix="/bookings", tags=["bookings"], dependencies=[ApiKeyAuth])


@router.get("/slots", response_model=list[SlotRead])
async def available_slots(
    session: DbSession,
    property_id: int = Query(..., gt=0),
    day: date = Query(...),
) -> list[SlotRead]:
    slots = await BookingService(session).available_slots(property_id, day)
    return [SlotRead(starts_at=s.start, ends_at=s.end) for s in slots]


@router.get("", response_model=list[BookingRead])
async def day_schedule(
    session: DbSession,
    day: date = Query(...),
    agent_id: int | None = Query(None),
) -> list[BookingRead]:
    bookings = await BookingService(session).day_schedule(day, agent_id)
    return [BookingRead.model_validate(b) for b in bookings]


@router.get("/{booking_id}", response_model=BookingRead)
async def get_booking(booking_id: int, session: DbSession) -> BookingRead:
    booking = await BookingService(session).get(booking_id)
    return BookingRead.model_validate(booking)


@router.post("", response_model=BookingRead, status_code=status.HTTP_201_CREATED)
async def create_booking(data: BookingCreate, session: DbSession) -> BookingRead:
    client = await UserService(session).get_or_create(data.client_telegram_id, username=None, full_name="")
    booking = await BookingService(session).book(
        client=client, property_id=data.property_id, starts_at=data.starts_at
    )
    await LeadService(session).mark_viewing(client)
    await session.commit()
    notify.notify_booking_event.delay(booking.id, "created")
    return BookingRead.model_validate(booking)


@router.post("/{booking_id}/reschedule", response_model=BookingRead)
async def reschedule_booking(booking_id: int, data: BookingReschedule, session: DbSession) -> BookingRead:
    service = BookingService(session)
    booking = await service.reschedule(booking_id, data.starts_at, actor=None)
    await session.commit()
    notify.notify_booking_event.delay(booking.id, "rescheduled")
    booking_tasks.process_waitlist.delay(booking.property_id)
    return BookingRead.model_validate(booking)


@router.post("/{booking_id}/extend", response_model=BookingRead)
async def extend_booking(
    booking_id: int,
    session: DbSession,
    minutes: int | None = Query(None, ge=5, le=120),
) -> BookingRead:
    booking = await BookingService(session).extend(booking_id, actor=None, minutes=minutes)
    await session.commit()
    notify.notify_booking_event.delay(booking.id, "extended")
    return BookingRead.model_validate(booking)


@router.post("/{booking_id}/cancel", response_model=BookingRead)
async def cancel_booking(
    booking_id: int,
    session: DbSession,
    data: BookingCancel | None = None,
) -> BookingRead:
    reason = data.reason if data else "cancelled_by_staff"
    booking = await BookingService(session).cancel(booking_id, actor=None, reason=reason)
    await session.commit()
    notify.notify_booking_event.delay(booking.id, "cancelled_by_staff")
    booking_tasks.process_waitlist.delay(booking.property_id)
    return BookingRead.model_validate(booking)
