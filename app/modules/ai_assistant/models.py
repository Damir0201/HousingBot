from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, str_enum
from app.shared.i18n import Language


class FaqEntry(TimestampMixin, Base):
    """Knowledge base for typical questions (deposit, contract, documents...).
    Fed to the LLM via the `search_faq` tool, so answers stay grounded."""

    __tablename__ = "faq_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    language: Mapped[Language] = mapped_column(str_enum(Language, length=8), index=True)
    question: Mapped[str] = mapped_column(String(500))
    answer: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(default=list)
    is_active: Mapped[bool] = mapped_column(default=True)
