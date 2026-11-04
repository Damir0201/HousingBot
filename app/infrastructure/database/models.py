"""Import every ORM model here so Alembic autogenerate sees the full metadata."""

from app.infrastructure.database.base import Base
from app.modules.agents.models import Agent
from app.modules.ai_assistant.models import FaqEntry
from app.modules.bookings.models import Booking, WaitlistEntry
from app.modules.crm.models import Lead, Ticket
from app.modules.excel_sync.models import SyncRun
from app.modules.properties.models import Property
from app.modules.users.models import User

__all__ = [
    "Agent",
    "Base",
    "Booking",
    "FaqEntry",
    "Lead",
    "Property",
    "SyncRun",
    "Ticket",
    "User",
    "WaitlistEntry",
]
