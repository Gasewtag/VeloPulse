"""Async database engine and session management."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from velopulse.core.config import get_settings

logger = logging.getLogger("velopulse.db.session")
settings = get_settings()

# Asynchronous SQLAlchemy Engine with connection pool tuning (DoD specification)
engine: AsyncEngine = create_async_engine(
    settings.async_postgres_dsn,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    echo=settings.POSTGRES_ECHO,
)

# Async session factory
async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency provider yielding transactional async database sessions."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for standalone async database transactions (workers, scripts)."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Gracefully close and dispose the connection pool."""
    logger.info("Disposing database connection pool")
    await engine.dispose()
