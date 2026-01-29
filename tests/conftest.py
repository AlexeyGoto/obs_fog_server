"""
Pytest configuration and fixtures.
"""
import asyncio
import os
from collections.abc import AsyncGenerator, Generator

# Set test environment before importing app modules
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"
os.environ["DEBUG"] = "true"
os.environ["JWT_SECRET"] = "test_secret_key_for_testing_only"
os.environ["ENVIRONMENT"] = "development"
os.environ["APPROVAL_REQUIRED"] = "false"
os.environ["SESSION_SECURE"] = "false"
os.environ["REDIS_URL"] = ""  # Disable Redis for tests (in-memory rate limiting)
os.environ["TELEGRAM_REQUIRED"] = "false"  # Disable Telegram binding for tests

# Clear settings cache to pick up test environment
from app.core.config import get_settings
get_settings.cache_clear()

# Disable rate limiter for tests
from app.core.rate_limit import limiter
limiter.enabled = False

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Now import app modules after environment is set
from app.models.base import Base


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///./test.db",
        echo=False,
        poolclass=NullPool,
    )

    # Import all models to register them
    from app.models import (
        Base,
        ClipJob,
        Payment,
        PC,
        SteamAccount,
        SteamLease,
        StreamSession,
        User,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client."""
    from app.core.database import get_db
    from app.main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def test_user_data() -> dict:
    """Sample user registration data."""
    return {
        "email": "test@example.com",
        "password": "testpassword123",
        "password_confirm": "testpassword123",
    }


@pytest.fixture
def test_admin_data() -> dict:
    """Sample admin user data."""
    return {
        "email": "admin@example.com",
        "password": "adminpassword123",
        "password_confirm": "adminpassword123",
    }


@pytest.fixture
def test_pc_data() -> dict:
    """Sample PC creation data."""
    return {"name": "Test PC"}
