"""Cross-module use cases for properties.

Kept apart from `PropertyService` so that `properties` doesn't import `bookings`
at module level (bookings already depends on properties)."""

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bookings.service import BookingService
from app.modules.properties.models import UNAVAILABLE_STATUSES, Property, PropertyStatus
from app.modules.properties.repository import PropertyRepository
from app.shared.exceptions import NotFoundError
from app.shared.logging import get_logger

log = get_logger(__name__)


@dataclass
class StatusChangeResult:
    property: Property
    old_status: PropertyStatus
    cancelled_booking_ids: list[int] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.old_status != self.property.status

    @property
    def became_available(self) -> bool:
        return self.changed and self.property.status == PropertyStatus.AVAILABLE


async def change_property_status(
    session: AsyncSession, property_id: int, new_status: PropertyStatus
) -> StatusChangeResult:
    """Change status atomically. If the property is rented/archived, every upcoming
    viewing and waitlist entry is cancelled in the same transaction.

    The caller must commit and then call `dispatch_status_side_effects(result)`
    to send notifications (never notify before the data is committed)."""
    prop = await PropertyRepository(session).get_for_update(property_id)
    if prop is None:
        raise NotFoundError("Property not found", property_id=property_id)

    result = StatusChangeResult(property=prop, old_status=prop.status)
    if prop.status == new_status:
        return result

    prop.status = new_status
    if new_status in UNAVAILABLE_STATUSES:
        cancelled = await BookingService(session).cancel_for_property(
            prop.id, reason=f"property_{new_status}"
        )
        result.cancelled_booking_ids = [b.id for b in cancelled]
    await session.flush()
    log.info(
        "property.status_changed",
        property_id=prop.id,
        old=result.old_status,
        new=new_status,
        cancelled=len(result.cancelled_booking_ids),
    )
    return result


def dispatch_status_side_effects(result: StatusChangeResult) -> None:
    """Enqueue background notifications. Call only AFTER commit."""
    from app.modules.notifications import tasks

    if result.cancelled_booking_ids:
        tasks.notify_property_unavailable.delay(result.property.id, result.cancelled_booking_ids)
