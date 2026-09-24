"""Tests for database session lifecycle and dependency injectors."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from velopulse.db.session import dispose_engine, get_db_session, get_session_context


@pytest.mark.asyncio
async def test_get_db_session_dependency() -> None:
    """Test get_db_session yields an active session and commits successfully."""
    session_gen = get_db_session()
    session: AsyncSession = await anext(session_gen)
    try:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1
    finally:
        with pytest.raises(StopAsyncIteration):
            await anext(session_gen)


@pytest.mark.asyncio
async def test_get_session_context_manager() -> None:
    """Test get_session_context context manager functions correctly."""
    async with get_session_context() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1


@pytest.mark.asyncio
async def test_get_db_session_rollback_on_exception() -> None:
    """Verify get_db_session rolls back when an exception is thrown."""
    session_gen = get_db_session()
    await anext(session_gen)
    with pytest.raises(RuntimeError, match="Forced error"):
        await session_gen.athrow(RuntimeError("Forced error"))


@pytest.mark.asyncio
async def test_get_session_context_rollback_on_exception() -> None:
    """Verify get_session_context rolls back when an exception occurs in block."""
    with pytest.raises(ValueError, match="Block failure"):
        async with get_session_context():
            raise ValueError("Block failure")


@pytest.mark.asyncio
async def test_dispose_engine() -> None:
    """Test engine disposal executes without exceptions."""
    await dispose_engine()
