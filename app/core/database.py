"""
Async SQLAlchemy database setup with PostgreSQL/SQLite.
Uses asyncpg driver for PostgreSQL, aiosqlite for SQLite.
"""
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, StaticPool

from app.core.config import settings


def _create_engine():
    """Create async engine based on database type."""
    url = settings.database_url

    if settings.is_sqlite:
        # SQLite: use StaticPool for async compatibility
        return create_async_engine(
            url,
            echo=settings.debug,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
    else:
        # PostgreSQL: use connection pooling
        return create_async_engine(
            url,
            echo=settings.debug,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_pre_ping=True,
        )


# Create async engine
engine = _create_engine()

# Session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting async database session.
    Yields a session and ensures proper cleanup.
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database session.
    For use in background tasks and scripts.
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize database - create tables if they don't exist.
    For production, use Alembic migrations instead.
    """
    from app.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()
