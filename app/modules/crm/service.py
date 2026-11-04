from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agents.service import AgentService
from app.modules.bookings.repository import BookingRepository
from app.modules.crm.models import Lead, LeadStatus, Ticket, TicketPriority, TicketStatus
from app.modules.crm.schemas import AgentStats, DashboardStats, TicketCreate
from app.modules.properties.repository import PropertyRepository
from app.modules.users.models import User
from app.shared.exceptions import NotFoundError
from app.shared.security import UserRole
from app.shared.timeutils import utcnow

_PRIORITY_ORDER = case(
    {TicketPriority.HIGH.value: 0, TicketPriority.NORMAL.value: 1, TicketPriority.LOW.value: 2},
    value=Ticket.priority,
    else_=3,
)


class TicketService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, client: User, data: TicketCreate) -> Ticket:
        ticket = Ticket(client_id=client.id, **data.model_dump())
        self.session.add(ticket)
        await self.session.flush()
        await self.session.refresh(ticket)
        return ticket

    async def get(self, ticket_id: int) -> Ticket:
        ticket = await self.session.get(Ticket, ticket_id)
        if ticket is None:
            raise NotFoundError("Ticket not found", ticket_id=ticket_id)
        return ticket

    async def list_open(self, assignee_id: int | None = None, limit: int = 20) -> Sequence[Ticket]:
        stmt = (
            select(Ticket)
            .where(Ticket.status != TicketStatus.RESOLVED)
            .order_by(_PRIORITY_ORDER, Ticket.created_at)
            .limit(limit)
        )
        if assignee_id is not None:
            stmt = stmt.where((Ticket.assignee_id == assignee_id) | Ticket.assignee_id.is_(None))
        return (await self.session.scalars(stmt)).all()

    async def take(self, ticket_id: int, staff: User) -> Ticket:
        ticket = await self.get(ticket_id)
        ticket.assignee_id = staff.id
        ticket.status = TicketStatus.IN_PROGRESS
        await self.session.flush()
        await self.session.refresh(ticket)
        return ticket

    async def resolve(self, ticket_id: int) -> Ticket:
        ticket = await self.get(ticket_id)
        ticket.status = TicketStatus.RESOLVED
        ticket.resolved_at = utcnow()
        await self.session.flush()
        return ticket


class LeadService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(self, client: User) -> Lead:
        lead = await self.session.scalar(select(Lead).where(Lead.client_id == client.id))
        if lead is None:
            lead = Lead(client_id=client.id)
            self.session.add(lead)
            await self.session.flush()
        return lead

    async def update_criteria(self, client: User, criteria: dict[str, Any]) -> Lead:
        lead = await self.get_or_create(client)
        lead.criteria = {**lead.criteria, **criteria}
        if lead.status == LeadStatus.NEW and criteria:
            lead.status = LeadStatus.QUALIFIED
        await self.session.flush()
        return lead

    async def mark_viewing(self, client: User) -> Lead:
        """Move the lead forward in the funnel, never backwards."""
        lead = await self.get_or_create(client)
        if lead.status in (LeadStatus.NEW, LeadStatus.QUALIFIED):
            lead.status = LeadStatus.VIEWING
        return lead

    async def set_status(self, client: User, status: LeadStatus) -> Lead:
        lead = await self.get_or_create(client)
        lead.status = status
        await self.session.flush()
        return lead


class StatsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def dashboard(self, days: int = 30) -> DashboardStats:
        end = utcnow()
        start = end - timedelta(days=days)
        bookings = BookingRepository(self.session)
        agents = await AgentService(self.session).list_all()
        by_agent = await bookings.stats_by_agent(start, end + timedelta(days=30))

        return DashboardStats(
            period_from=start,
            period_to=end,
            properties_by_status=await PropertyRepository(self.session).count_by_status(),
            bookings_by_status=await bookings.stats(start, end + timedelta(days=30)),
            agents=[
                AgentStats(agent_id=a.id, name=a.display_name, bookings=by_agent.get(a.id, {}))
                for a in agents
            ],
            tickets_by_status=await self._group_count(Ticket.status, Ticket.created_at, start),
            leads_by_status=await self._group_count(Lead.status, None, None),
            new_clients=await self._new_clients(start),
            waitlist_size=await bookings.waitlist_size(),
        )

    async def _group_count(self, column: Any, date_column: Any, since: datetime | None) -> dict[str, int]:
        stmt = select(column, func.count()).group_by(column)
        if date_column is not None and since is not None:
            stmt = stmt.where(date_column >= since)
        rows = await self.session.execute(stmt)
        return {str(k): v for k, v in rows.all()}

    async def _new_clients(self, since: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.CLIENT, User.created_at >= since)
        )
        return int(await self.session.scalar(stmt) or 0)
