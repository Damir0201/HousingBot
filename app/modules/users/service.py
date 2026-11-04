from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.shared.exceptions import NotFoundError
from app.shared.i18n import Language
from app.shared.security import STAFF_ROLES, UserRole


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = UserRepository(session)

    async def get_or_create(self, telegram_id: int, *, username: str | None, full_name: str) -> User:
        user = await self.repo.get_by_telegram_id(telegram_id)
        is_owner = telegram_id in get_settings().owner_ids
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                full_name=full_name,
                role=UserRole.OWNER if is_owner else UserRole.CLIENT,
            )
            self.repo.add(user)
            await self.session.flush()
            return user

        # keep profile fresh and owners in sync with config
        if user.username != username:
            user.username = username
        if full_name and user.full_name != full_name:
            user.full_name = full_name
        if is_owner and user.role != UserRole.OWNER:
            user.role = UserRole.OWNER
        return user

    async def get(self, user_id: int) -> User:
        user = await self.repo.get(user_id)
        if user is None:
            raise NotFoundError("User not found", user_id=user_id)
        return user

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        return await self.repo.get_by_telegram_id(telegram_id)

    async def set_language(self, user: User, language: Language) -> None:
        user.language = language

    async def set_phone(self, user: User, phone: str) -> None:
        user.phone = phone

    async def set_role(self, user: User, role: UserRole) -> None:
        user.role = role

    async def staff(self) -> Sequence[User]:
        return await self.repo.list_by_roles(*STAFF_ROLES)

    async def owners(self) -> Sequence[User]:
        return await self.repo.list_by_roles(UserRole.OWNER)
