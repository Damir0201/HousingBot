import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import Base
from app.infrastructure.database.session import build_engine, build_session_factory
from app.modules.agents.service import AgentService
from app.modules.bookings.service import BookingService
from app.modules.properties.models import PropertyStatus, PropertyType
from app.modules.properties.schemas import PropertyCreate
from app.modules.properties.service import PropertyService
from app.modules.properties.workflows import change_property_status
from app.modules.users.service import UserService

pytestmark = pytest.mark.integration


@pytest.fixture
async def db_session() -> AsyncSession:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    engine = build_engine(null_pool=True, url=url)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = build_session_factory(engine)
    async with factory() as session:
        yield session

    await engine.dispose()


async def test_booking_and_rented_cancels_upcoming_viewings(db_session: AsyncSession) -> None:
    users = UserService(db_session)
    agent_user = await users.get_or_create(1001, username="agent1", full_name="Agent One")
    client_user = await users.get_or_create(2001, username="client1", full_name="Client One")
    await AgentService(db_session).register(agent_user, "Agent One")

    prop = await PropertyService(db_session).create(
        PropertyCreate(
            code="MIL-01",
            title="Navigli Loft",
            property_type=PropertyType.STUDIO,
            city="Milan",
            district="Navigli",
            rooms=1,
            price_month=Decimal("950"),
        )
    )

    bookings = BookingService(db_session)
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    booking = await bookings.book(client=client_user, property_id=prop.id, starts_at=tomorrow)
    assert booking.is_active

    result = await change_property_status(db_session, prop.id, PropertyStatus.RENTED)
    assert result.cancelled_booking_ids == [booking.id]
