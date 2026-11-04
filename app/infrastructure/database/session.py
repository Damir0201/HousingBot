from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings


def build_engine(*, null_pool: bool = False, url: str | None = None) -> AsyncEngine:
    settings = get_settings()
    kwargs: dict[str, object] = {"echo": settings.database_echo, "pool_pre_ping": True}
    if null_pool:
        # Celery tasks run each coroutine in a fresh event loop -> pooled connections
        # bound to a dead loop would break. NullPool opens a connection per task.
        kwargs = {"echo": settings.database_echo, "poolclass": NullPool}
    else:
        kwargs.update(pool_size=10, max_overflow=20)
    return create_async_engine(url or settings.database_url, **kwargs)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@lru_cache
def get_engine() -> AsyncEngine:
    return build_engine()


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return build_session_factory(get_engine())


@asynccontextmanager
async def task_session() -> AsyncIterator[AsyncSession]:
    """Session for Celery tasks: own engine without pool, commit on success."""
    engine = build_engine(null_pool=True)
    factory = build_session_factory(engine)
    try:
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    finally:
        await engine.dispose()
