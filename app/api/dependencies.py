from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.infrastructure.database.session import get_session_factory
from app.shared.exceptions import PermissionDeniedError
from app.shared.security import secure_compare


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Per-request unit of work: commits on success, rolls back on exception."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if not secure_compare(x_api_key, settings.api_key.get_secret_value()):
        raise PermissionDeniedError("Invalid or missing X-API-Key")


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
ApiKeyAuth = Depends(require_api_key)
