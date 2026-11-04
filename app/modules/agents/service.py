from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agents.models import Agent
from app.modules.users.models import User
from app.shared.exceptions import NotFoundError
from app.shared.security import UserRole


class AgentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_active(self) -> Sequence[Agent]:
        result = await self.session.scalars(select(Agent).where(Agent.is_active).order_by(Agent.id))
        return result.all()

    async def list_all(self) -> Sequence[Agent]:
        result = await self.session.scalars(select(Agent).order_by(Agent.id))
        return result.all()

    async def get(self, agent_id: int) -> Agent:
        agent = await self.session.get(Agent, agent_id)
        if agent is None:
            raise NotFoundError("Agent not found", agent_id=agent_id)
        return agent

    async def get_by_user(self, user_id: int) -> Agent | None:
        return await self.session.scalar(select(Agent).where(Agent.user_id == user_id))

    async def register(self, user: User, display_name: str | None = None) -> Agent:
        """Promote a user to agent (idempotent)."""
        agent = await self.get_by_user(user.id)
        if agent is None:
            agent = Agent(user_id=user.id, display_name=display_name or user.full_name or user.mention)
            self.session.add(agent)
        agent.is_active = True
        if user.role == UserRole.CLIENT:
            user.role = UserRole.AGENT
        await self.session.flush()
        return agent

    async def deactivate(self, agent_id: int) -> Agent:
        agent = await self.get(agent_id)
        agent.is_active = False
        if agent.user.role == UserRole.AGENT:
            agent.user.role = UserRole.CLIENT
        return agent
