from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, TimestampMixin, str_enum
from app.modules.agents.models import Agent
from app.modules.properties.models import Property
from app.modules.users.models import User


class BookingStatus(StrEnum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class WaitlistStatus(StrEnum):
    WAITING = "waiting"
    OFFERED = "offered"
    BOOKED = "booked"
    CANCELLED = "cancelled"


class Booking(TimestampMixin, Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="valid_period"),
        Index("ix_bookings_status_starts_at", "status", "starts_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="RESTRICT"), index=True)
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime]
    status: Mapped[BookingStatus] = mapped_column(str_enum(BookingStatus), default=BookingStatus.SCHEDULED)
    cancel_reason: Mapped[str | None] = mapped_column(String(255))
    reminder_sent: Mapped[bool] = mapped_column(default=False)
    extended_minutes: Mapped[int] = mapped_column(default=0)
    reschedule_count: Mapped[int] = mapped_column(default=0)

    @property
    def is_active(self) -> bool:
        return self.status == BookingStatus.SCHEDULED

    property: Mapped[Property] = relationship(lazy="joined")
    client: Mapped[User] = relationship(lazy="joined")
    agent: Mapped[Agent] = relationship(lazy="joined")


# The core guarantee of task #3: one agent can never have two overlapping viewings.
# Enforced by PostgreSQL itself (requires the btree_gist extension), so concurrent
# bookings from different bot workers can't race past an application-level check.
Booking.__table__.append_constraint(
    ExcludeConstraint(
        (Booking.__table__.c.agent_id, "="),
        (func.tstzrange(Booking.__table__.c.starts_at, Booking.__table__.c.ends_at), "&&"),
        name="ex_bookings_agent_no_overlap",
        using="gist",
        where=text("status = 'scheduled'"),
    )
)


class WaitlistEntry(TimestampMixin, Base):
    __tablename__ = "waitlist_entries"
    __table_args__ = (Index("ix_waitlist_property_status", "property_id", "status", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"))
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    preferred_date: Mapped[date | None]
    status: Mapped[WaitlistStatus] = mapped_column(str_enum(WaitlistStatus), default=WaitlistStatus.WAITING)
    offered_at: Mapped[datetime | None]

    property: Mapped[Property] = relationship(lazy="joined")
    client: Mapped[User] = relationship(lazy="joined")
