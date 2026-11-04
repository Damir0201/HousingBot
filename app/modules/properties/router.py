from fastapi import APIRouter, Query, status

from app.api.dependencies import ApiKeyAuth, DbSession
from app.modules.bookings import tasks as booking_tasks
from app.modules.properties.models import PropertyStatus
from app.modules.properties.schemas import (
    PropertyCreate,
    PropertyRead,
    PropertySearchCriteria,
    PropertyStatusUpdate,
    PropertyUpdate,
)
from app.modules.properties.service import PropertyService
from app.modules.properties.workflows import change_property_status, dispatch_status_side_effects

router = APIRouter(prefix="/properties", tags=["properties"], dependencies=[ApiKeyAuth])


@router.get("", response_model=list[PropertyRead])
async def list_properties(
    session: DbSession,
    status_filter: PropertyStatus | None = Query(None, alias="status"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[PropertyRead]:
    props = await PropertyService(session).list(status=status_filter, offset=offset, limit=limit)
    return [PropertyRead.model_validate(p) for p in props]


@router.post("/search", response_model=list[PropertyRead])
async def search_properties(session: DbSession, criteria: PropertySearchCriteria) -> list[PropertyRead]:
    props = await PropertyService(session).search(criteria)
    return [PropertyRead.model_validate(p) for p in props]


@router.get("/{property_id}", response_model=PropertyRead)
async def get_property(property_id: int, session: DbSession) -> PropertyRead:
    prop = await PropertyService(session).get(property_id)
    return PropertyRead.model_validate(prop)


@router.post("", response_model=PropertyRead, status_code=status.HTTP_201_CREATED)
async def create_property(data: PropertyCreate, session: DbSession) -> PropertyRead:
    prop = await PropertyService(session).create(data)
    return PropertyRead.model_validate(prop)


@router.patch("/{property_id}", response_model=PropertyRead)
async def update_property(property_id: int, data: PropertyUpdate, session: DbSession) -> PropertyRead:
    prop = await PropertyService(session).update(property_id, data)
    return PropertyRead.model_validate(prop)


@router.patch("/{property_id}/status", response_model=PropertyRead)
async def update_property_status(
    property_id: int, data: PropertyStatusUpdate, session: DbSession
) -> PropertyRead:
    result = await change_property_status(session, property_id, data.status)
    await session.commit()
    dispatch_status_side_effects(result)
    if result.became_available:
        booking_tasks.process_waitlist.delay(result.property.id)
    return PropertyRead.model_validate(result.property)
