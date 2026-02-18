import os

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

settings = get_settings()

if os.getenv("DB_ASYNC_NULLPOOL", "0") == "1":
    engine: AsyncEngine = create_async_engine(
        settings.database_url,
        future=True,
        echo=settings.app_env == "local",
        poolclass=NullPool,
    )
else:
    engine = create_async_engine(
        settings.database_url,
        future=True,
        echo=settings.app_env == "local",
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
    )
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        yield session
