from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from job_aggregator.config import settings

def _async_url(url: str) -> str:
    """Ensure the URL uses the asyncpg driver (Railway provides postgresql://).

    ``postgres://`` is mapped too: SQLAlchemy has no "postgres" dialect. URLs that
    already name a driver (``postgresql+asyncpg://``) are returned unchanged.
    """
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    return url


engine = create_async_engine(_async_url(settings.database_url), echo=False, pool_size=5, max_overflow=10)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    from job_aggregator.db.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
