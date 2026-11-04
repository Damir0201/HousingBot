from datetime import time

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, TimestampMixin
from app.modules.users.models import User


class Agent(TimestampMixin, Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    display_name: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    # Personal working hours; NULL -> agency defaults from settings
    work_start: Mapped[time | None]
    work_end: Mapped[time | None]

    user: Mapped[User] = relationship(lazy="joined")
