from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_assistant.models import FaqEntry
from app.shared.i18n import Language


class FaqService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(self, query: str, language: Language, limit: int = 3) -> Sequence[FaqEntry]:
        words = [w for w in query.lower().split() if len(w) > 3][:6]
        stmt = select(FaqEntry).where(FaqEntry.is_active, FaqEntry.language == language)
        if words:
            stmt = stmt.where(
                or_(
                    *(FaqEntry.question.ilike(f"%{w}%") for w in words),
                    *(FaqEntry.answer.ilike(f"%{w}%") for w in words),
                )
            )
        return (await self.session.scalars(stmt.limit(limit))).all()
