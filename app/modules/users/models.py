from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, str_enum
from app.shared.i18n import Language
from app.shared.security import UserRole


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    full_name: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str | None] = mapped_column(String(32))
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole), default=UserRole.CLIENT, index=True)
    # NULL until the user explicitly picks a language on /start
    language: Mapped[Language | None] = mapped_column(str_enum(Language, length=8))
    is_blocked: Mapped[bool] = mapped_column(default=False)

    @property
    def mention(self) -> str:
        return f"@{self.username}" if self.username else self.full_name or str(self.telegram_id)
