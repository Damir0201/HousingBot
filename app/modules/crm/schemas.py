from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.crm.models import LeadStatus, TicketCategory, TicketPriority, TicketStatus


class TicketCreate(BaseModel):
    category: TicketCategory = TicketCategory.GENERAL
    priority: TicketPriority = TicketPriority.NORMAL
    summary: str = Field(..., min_length=1, max_length=4000)
    context: dict[str, Any] = Field(default_factory=dict)


class TicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    assignee_id: int | None
    category: TicketCategory
    priority: TicketPriority
    status: TicketStatus
    summary: str
    context: dict[str, Any]
    created_at: datetime
    resolved_at: datetime | None


class LeadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    status: LeadStatus
    criteria: dict[str, Any]
    source: str
    notes: str
    updated_at: datetime


class AgentStats(BaseModel):
    agent_id: int
    name: str
    bookings: dict[str, int]


class DashboardStats(BaseModel):
    period_from: datetime
    period_to: datetime
    properties_by_status: dict[str, int]
    bookings_by_status: dict[str, int]
    agents: list[AgentStats]
    tickets_by_status: dict[str, int]
    leads_by_status: dict[str, int]
    new_clients: int
    waitlist_size: int
