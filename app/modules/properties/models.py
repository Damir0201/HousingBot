from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, str_enum


class PropertyType(StrEnum):
    APARTMENT = "apartment"
    STUDIO = "studio"
    ROOM = "room"
    HOUSE = "house"


class PropertyStatus(StrEnum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    RENTED = "rented"
    ARCHIVED = "archived"


# Statuses after which every upcoming viewing must be cancelled
UNAVAILABLE_STATUSES = frozenset({PropertyStatus.RENTED, PropertyStatus.ARCHIVED})


class Property(TimestampMixin, Base):
    __tablename__ = "properties"
    __table_args__ = (Index("ix_properties_search", "status", "district", "price_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, comment="Business key, used in Excel")
    title: Mapped[str] = mapped_column(String(255))
    property_type: Mapped[PropertyType] = mapped_column(str_enum(PropertyType))
    status: Mapped[PropertyStatus] = mapped_column(
        str_enum(PropertyStatus), default=PropertyStatus.AVAILABLE, index=True
    )
    city: Mapped[str] = mapped_column(String(64), default="")
    district: Mapped[str] = mapped_column(String(64), default="", index=True)
    address: Mapped[str] = mapped_column(String(255), default="")
    rooms: Mapped[int] = mapped_column(default=1)
    area_m2: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    floor: Mapped[int | None]
    price_month: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    deposit: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    min_term_months: Mapped[int] = mapped_column(default=1)
    max_term_months: Mapped[int | None]
    available_from: Mapped[date | None]
    furnished: Mapped[bool] = mapped_column(default=False)
    pets_allowed: Mapped[bool] = mapped_column(default=False)
    utilities_included: Mapped[bool] = mapped_column(default=False)
    description: Mapped[str] = mapped_column(Text, default="")
    features: Mapped[dict[str, Any]] = mapped_column(default=dict)
    photos: Mapped[list[str]] = mapped_column(default=list)
    version: Mapped[int] = mapped_column(default=1)

    __mapper_args__ = {"version_id_col": version}  # optimistic locking

    @property
    def is_bookable(self) -> bool:
        return self.status == PropertyStatus.AVAILABLE
