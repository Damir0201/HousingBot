from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.bookings.models import BookingStatus, WaitlistStatus


class SlotRead(BaseModel):
    starts_at: datetime
    ends_at: datetime


class BookingCreate(BaseModel):
    client_telegram_id: int
    property_id: int
    starts_at: datetime


class BookingReschedule(BaseModel):
    starts_at: datetime


class BookingCancel(BaseModel):
    reason: str = Field("cancelled_by_staff", max_length=255)


class BookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    property_id: int
    client_id: int
    agent_id: int
    starts_at: datetime
    ends_at: datetime
    status: BookingStatus
    cancel_reason: str | None
    extended_minutes: int
    reschedule_count: int


class WaitlistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    property_id: int
    client_id: int
    preferred_date: date | None
    status: WaitlistStatus
    created_at: datetime
