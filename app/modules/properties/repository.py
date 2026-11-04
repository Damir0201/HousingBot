from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.properties.models import Property, PropertyStatus
from app.modules.properties.schemas import PropertySearchCriteria


class PropertyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, property_id: int) -> Property | None:
        return await self.session.get(Property, property_id)

    async def get_for_update(self, property_id: int) -> Property | None:
        return await self.session.scalar(select(Property).where(Property.id == property_id).with_for_update())

    async def get_by_code(self, code: str) -> Property | None:
        return await self.session.scalar(select(Property).where(Property.code == code))

    async def get_by_codes(self, codes: Sequence[str]) -> dict[str, Property]:
        if not codes:
            return {}
        result = await self.session.scalars(select(Property).where(Property.code.in_(codes)))
        return {p.code: p for p in result}

    async def list(
        self, *, status: PropertyStatus | None = None, offset: int = 0, limit: int = 50
    ) -> Sequence[Property]:
        stmt = select(Property).order_by(Property.id).offset(offset).limit(limit)
        if status:
            stmt = stmt.where(Property.status == status)
        return (await self.session.scalars(stmt)).all()

    async def all(self) -> Sequence[Property]:
        return (await self.session.scalars(select(Property).order_by(Property.code))).all()

    async def count_by_status(self) -> dict[str, int]:
        rows = await self.session.execute(select(Property.status, func.count()).group_by(Property.status))
        return {str(status): count for status, count in rows.all()}

    async def search(self, criteria: PropertySearchCriteria) -> Sequence[Property]:
        stmt = self._search_stmt(criteria).order_by(Property.price_month).limit(criteria.limit)
        return (await self.session.scalars(stmt)).all()

    @staticmethod
    def _search_stmt(c: PropertySearchCriteria) -> Select[tuple[Property]]:
        stmt = select(Property).where(Property.status == PropertyStatus.AVAILABLE)
        if c.budget_min is not None:
            stmt = stmt.where(Property.price_month >= c.budget_min)
        if c.budget_max is not None:
            stmt = stmt.where(Property.price_month <= c.budget_max)
        if c.city:
            stmt = stmt.where(Property.city.ilike(c.city))
        if c.districts:
            stmt = stmt.where(or_(*(Property.district.ilike(f"%{d.strip()}%") for d in c.districts)))
        if c.property_types:
            stmt = stmt.where(Property.property_type.in_(c.property_types))
        if c.rooms_min is not None:
            stmt = stmt.where(Property.rooms >= c.rooms_min)
        if c.rooms_max is not None:
            stmt = stmt.where(Property.rooms <= c.rooms_max)
        if c.term_months is not None:
            stmt = stmt.where(Property.min_term_months <= c.term_months).where(
                or_(Property.max_term_months.is_(None), Property.max_term_months >= c.term_months)
            )
        if c.move_in_date is not None:
            stmt = stmt.where(
                or_(Property.available_from.is_(None), Property.available_from <= c.move_in_date)
            )
        for flag in ("furnished", "pets_allowed", "utilities_included"):
            value = getattr(c, flag)
            if value is not None:
                stmt = stmt.where(getattr(Property, flag).is_(value))
        if c.exclude_ids:
            stmt = stmt.where(Property.id.not_in(c.exclude_ids))
        return stmt

    async def similar(self, prop: Property, limit: int = 3) -> Sequence[Property]:
        """Alternatives: same type, ±20% price, same district first."""
        low, high = prop.price_month * Decimal("0.8"), prop.price_month * Decimal("1.2")
        stmt = (
            select(Property)
            .where(
                Property.status == PropertyStatus.AVAILABLE,
                Property.id != prop.id,
                Property.property_type == prop.property_type,
                Property.price_month.between(low, high),
            )
            .order_by((Property.district != prop.district), func.abs(Property.price_month - prop.price_month))
            .limit(limit)
        )
        return (await self.session.scalars(stmt)).all()

    def add(self, prop: Property) -> None:
        self.session.add(prop)
