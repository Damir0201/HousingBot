from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.properties.models import PropertyStatus, PropertyType


class PropertySearchCriteria(BaseModel):
    """Shared by the bot, REST API and LLM tool `search_properties`.
    Strict validation means a hallucinating LLM can't produce a broken query."""

    model_config = ConfigDict(extra="ignore")

    budget_min: Decimal | None = Field(None, ge=0, description="Minimum monthly rent, EUR")
    budget_max: Decimal | None = Field(None, ge=0, description="Maximum monthly rent, EUR")
    districts: list[str] = Field(default_factory=list, description="Preferred districts / neighbourhoods")
    city: str | None = None
    property_types: list[PropertyType] = Field(default_factory=list)
    rooms_min: int | None = Field(None, ge=0, le=20)
    rooms_max: int | None = Field(None, ge=0, le=20)
    rental_period: Literal["short", "long"] | None = Field(
        None, description="Desired stay period: 'short' (short-term) or 'long' (long-term)"
    )
    term_months: int | None = Field(None, ge=1, le=120, description="Desired rental term in months")
    move_in_date: date | None = None
    furnished: bool | None = None
    pets_allowed: bool | None = None
    utilities_included: bool | None = None
    exclude_ids: list[int] = Field(default_factory=list)
    limit: int = Field(5, ge=1, le=20)

    @model_validator(mode="after")
    def _swap_ranges(self) -> "PropertySearchCriteria":
        if self.budget_min and self.budget_max and self.budget_min > self.budget_max:
            self.budget_min, self.budget_max = self.budget_max, self.budget_min
        if self.rooms_min and self.rooms_max and self.rooms_min > self.rooms_max:
            self.rooms_min, self.rooms_max = self.rooms_max, self.rooms_min
        return self

    def is_empty(self) -> bool:
        return not self.model_dump(exclude_defaults=True, exclude={"limit", "exclude_ids"})


class PropertyBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=32)
    title: str = Field(..., min_length=1, max_length=255)
    property_type: PropertyType
    status: PropertyStatus = PropertyStatus.AVAILABLE
    city: str = ""
    district: str = ""
    address: str = ""
    rooms: int = Field(1, ge=0, le=50)
    area_m2: Decimal | None = Field(None, ge=0)
    floor: int | None = None
    price_month: Decimal = Field(..., ge=0)
    deposit: Decimal | None = Field(None, ge=0)
    min_term_months: int = Field(1, ge=1)
    max_term_months: int | None = Field(None, ge=1)
    available_from: date | None = None
    furnished: bool = False
    pets_allowed: bool = False
    utilities_included: bool = False
    description: str = ""
    features: dict[str, Any] = Field(default_factory=dict)
    photos: list[str] = Field(default_factory=list)


class PropertyCreate(PropertyBase):
    pass


class PropertyUpdate(BaseModel):
    title: str | None = None
    property_type: PropertyType | None = None
    city: str | None = None
    district: str | None = None
    address: str | None = None
    rooms: int | None = Field(None, ge=0, le=50)
    area_m2: Decimal | None = None
    floor: int | None = None
    price_month: Decimal | None = Field(None, ge=0)
    deposit: Decimal | None = None
    min_term_months: int | None = Field(None, ge=1)
    max_term_months: int | None = None
    available_from: date | None = None
    furnished: bool | None = None
    pets_allowed: bool | None = None
    utilities_included: bool | None = None
    description: str | None = None
    features: dict[str, Any] | None = None
    photos: list[str] | None = None


class PropertyStatusUpdate(BaseModel):
    status: PropertyStatus


class PropertyRead(PropertyBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int
    created_at: datetime
    updated_at: datetime


class PropertyBrief(BaseModel):
    """Compact representation returned to the LLM (saves tokens)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    title: str
    property_type: PropertyType
    district: str
    rooms: int
    price_month: Decimal
    min_term_months: int
    furnished: bool
    pets_allowed: bool
    available_from: date | None
