from aiogram.filters import Filter
from aiogram.types import Message, TelegramObject

from app.modules.users.models import User
from app.shared.i18n import Language, Translator
from app.shared.security import UserRole


class RoleFilter(Filter):
    """Allow the handler only for users with one of the given roles."""

    def __init__(self, *roles: UserRole) -> None:
        self.roles = frozenset(roles)

    async def __call__(self, event: TelegramObject, user: User | None = None) -> bool:
        return user is not None and user.role in self.roles


class TextKey(Filter):
    """Match a reply-keyboard button in ANY supported language,
    so menu buttons keep working right after the user switches language."""

    def __init__(self, *keys: str) -> None:
        self.texts = frozenset(Translator(lang)(key) for key in keys for lang in Language)

    async def __call__(self, message: Message) -> bool:
        return message.text in self.texts


MENU_KEYS = ("menu.search", "menu.bookings", "menu.support", "menu.language", "menu.admin")


def menu_button() -> TextKey:
    """Use as `~menu_button()` in free-text FSM states so menu buttons still work."""
    return TextKey(*MENU_KEYS)
