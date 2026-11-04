from fastapi import APIRouter, Query

from app.api.dependencies import ApiKeyAuth, DbSession
from app.modules.crm.schemas import DashboardStats, TicketRead
from app.modules.crm.service import StatsService, TicketService

router = APIRouter(prefix="/crm", tags=["crm"], dependencies=[ApiKeyAuth])


@router.get("/stats", response_model=DashboardStats)
async def dashboard_stats(
    session: DbSession,
    days: int = Query(30, ge=1, le=365),
) -> DashboardStats:
    return await StatsService(session).dashboard(days=days)


@router.get("/tickets", response_model=list[TicketRead])
async def list_open_tickets(
    session: DbSession,
    limit: int = Query(20, ge=1, le=100),
) -> list[TicketRead]:
    tickets = await TicketService(session).list_open(limit=limit)
    return [TicketRead.model_validate(t) for t in tickets]


@router.post("/tickets/{ticket_id}/resolve", response_model=TicketRead)
async def resolve_ticket(ticket_id: int, session: DbSession) -> TicketRead:
    ticket = await TicketService(session).resolve(ticket_id)
    return TicketRead.model_validate(ticket)
