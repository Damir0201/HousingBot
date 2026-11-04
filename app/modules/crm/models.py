from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, TimestampMixin, str_enum
from app.modules.users.models import User


class TicketStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


class TicketCategory(StrEnum):
    GENERAL = "general"
    BOOKING = "booking"
    PROPERTY = "property"
    CONTRACT = "contract"
    PAYMENT = "payment"
    COMPLAINT = "complaint"
    OTHER = "other"


class TicketPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class LeadStatus(StrEnum):
    NEW = "new"
    QUALIFIED = "qualified"
    VIEWING = "viewing"
    NEGOTIATION = "negotiation"
    WON = "won"
    LOST = "lost"


class Ticket(TimestampMixin, Base):
    """Support request escalated to a human operator."""

    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    category: Mapped[TicketCategory] = mapped_column(str_enum(TicketCategory), default=TicketCategory.GENERAL)
    priority: Mapped[TicketPriority] = mapped_column(str_enum(TicketPriority), default=TicketPriority.NORMAL)
    status: Mapped[TicketStatus] = mapped_column(
        str_enum(TicketStatus), default=TicketStatus.OPEN, index=True
    )
    summary: Mapped[str] = mapped_column(Text)
    # criteria, last dialog messages, related property ids... — everything the operator needs
    context: Mapped[dict[str, Any]] = mapped_column(default=dict)
    resolved_at: Mapped[datetime | None]

    client: Mapped[User] = relationship(foreign_keys=[client_id], lazy="joined")
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id], lazy="joined")


class Lead(TimestampMixin, Base):
    """Sales funnel card: one per client, holds the latest search criteria."""

    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    status: Mapped[LeadStatus] = mapped_column(str_enum(LeadStatus), default=LeadStatus.NEW, index=True)
    criteria: Mapped[dict[str, Any]] = mapped_column(default=dict)
    source: Mapped[str] = mapped_column(String(32), default="telegram")
    notes: Mapped[str] = mapped_column(Text, default="")

    client: Mapped[User] = relationship(lazy="joined")
