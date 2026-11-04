from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.properties.models import Property, PropertyStatus
from app.modules.properties.repository import PropertyRepository
from app.modules.properties.schemas import PropertyCreate, PropertySearchCriteria, PropertyUpdate
from app.shared.exceptions import NotFoundError, ValidationError


class PropertyService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PropertyRepository(session)

    async def get(self, property_id: int) -> Property:
        prop = await self.repo.get(property_id)
        if prop is None:
            raise NotFoundError("Property not found", property_id=property_id)
        return prop

    async def list(
        self, *, status: PropertyStatus | None = None, offset: int = 0, limit: int = 50
    ) -> Sequence[Property]:
        return await self.repo.list(status=status, offset=offset, limit=limit)

    async def search(self, criteria: PropertySearchCriteria) -> Sequence[Property]:
        return await self.repo.search(criteria)

    async def similar(self, prop: Property, limit: int = 3) -> Sequence[Property]:
        return await self.repo.similar(prop, limit)

    async def create(self, data: PropertyCreate) -> Property:
        if await self.repo.get_by_code(data.code):
            raise ValidationError("Property code already exists", code=data.code)
        prop = Property(**data.model_dump())
        self.repo.add(prop)
        await self.session.flush()
        return prop

    async def update(self, property_id: int, data: PropertyUpdate) -> Property:
        """Field updates only. Status changes go through `workflows.change_property_status`
        because they have side effects (cancelling viewings, notifications)."""
        prop = await self.get(property_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(prop, field, value)
        await self.session.flush()
        return prop

    async def add_photo(self, property_id: int, photo_id: str) -> Property:
        prop = await self.get(property_id)
        current = list(prop.photos or [])
        if photo_id not in current and len(current) < 10:
            prop.photos = [*current, photo_id]
            await self.session.flush()
        return prop

    async def clear_photos(self, property_id: int) -> Property:
        prop = await self.get(property_id)
        prop.photos = []
        await self.session.flush()
        return prop
