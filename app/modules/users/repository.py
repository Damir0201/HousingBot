from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User
from app.shared.security import UserRole


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        return await self.session.scalar(select(User).where(User.telegram_id == telegram_id))

    async def list_by_roles(self, *roles: UserRole) -> Sequence[User]:
        result = await self.session.scalars(select(User).where(User.role.in_(roles)).order_by(User.id))
        return result.all()

    def add(self, user: User) -> None:
        self.session.add(user)
