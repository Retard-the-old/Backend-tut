"""Shared test fixtures for Tutorii backend tests.

Uses an in-memory SQLite database for speed. For full integration tests
against PostgreSQL, set TEST_DATABASE_URL in your env.
"""
from __future__ import annotations
import asyncio, os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from unittest.mock import AsyncMock, patch

# Override settings before importing app
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///file::memory:?cache=shared"
os.environ["SECRET_KEY"] = "test-secret-key-for-unit-tests-only-64chars-padding-here-1234567"
os.environ["MAMOPAY_API_KEY"] = "sk_test_fake"
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-fake"
os.environ["AWS_SES_ACCESS_KEY_ID"] = "AKIATEST"
os.environ["AWS_SES_SECRET_ACCESS_KEY"] = "testsecret"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"
os.environ["CELERY_BROKER_URL"] = "redis://localhost:6379/15"
os.environ["CELERY_RESULT_BACKEND"] = "redis://localhost:6379/15"

from app.db.database import Base, get_db
from app.core.config import settings
from main import app

# Test database engine (SQLite async)
test_engine = create_async_engine("sqlite+aiosqlite:///file::memory:?cache=shared", echo=False)
TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create all tables before each test, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _override_get_db():
    async with TestSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = _override_get_db


@pytest_asyncio.fixture
async def client():
    """Async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db():
    """Direct database session for test setup/assertions."""
    async with TestSession() as session:
        yield session
        await session.commit()


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient):
    """Register a test user and return auth headers."""
    resp = await client.post("/api/v1/auth/register", json={
        "email": "test@example.com",
        "password": "TestPass123",
        "full_name": "Test User",
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_headers(client: AsyncClient, db: AsyncSession):
    """Register a user, promote to admin, return auth headers."""
    resp = await client.post("/api/v1/auth/register", json={
        "email": "admin@example.com",
        "password": "AdminPass123",
        "full_name": "Admin User",
    })
    token = resp.json()["access_token"]
    # Promote to admin
    from app.models.user import User
    from sqlalchemy import select, update
    await db.execute(update(User).where(User.email == "admin@example.com").values(role="admin"))
    await db.commit()
    return {"Authorization": f"Bearer {token}"}
