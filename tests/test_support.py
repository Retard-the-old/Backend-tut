"""Tests for support endpoints."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch, AsyncMock
from app.models.user import User
from sqlalchemy import select, update


MOCK_LINK = {"id": "link_123", "payment_url": "https://pay.mamopay.com/test"}


async def _support_headers(client: AsyncClient, db: AsyncSession) -> dict:
    """Register a support user and return auth headers."""
    reg = await client.post("/api/v1/auth/register", json={
        "email": "support@example.com", "password": "StrongPass1", "full_name": "Support Agent",
    })
    token = reg.json()["access_token"]
    await db.execute(update(User).where(User.email == "support@example.com").values(role="support"))
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


async def _create_target_user(client: AsyncClient) -> tuple[str, str]:
    """Register a regular user, return (user_id, token)."""
    reg = await client.post("/api/v1/auth/register", json={
        "email": "target@example.com", "password": "StrongPass1", "full_name": "Target User",
    })
    token = reg.json()["access_token"]
    profile = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    return profile.json()["id"], token


@pytest.mark.asyncio
async def test_support_requires_role(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/support/users/some-id", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_support_lookup_user(client: AsyncClient, db: AsyncSession):
    support_h = await _support_headers(client, db)
    uid, _ = await _create_target_user(client)

    resp = await client.get(f"/api/v1/support/users/{uid}", headers=support_h)
    assert resp.status_code == 200
    assert resp.json()["email"] == "target@example.com"


@pytest.mark.asyncio
async def test_support_lookup_user_not_found(client: AsyncClient, db: AsyncSession):
    support_h = await _support_headers(client, db)
    resp = await client.get("/api/v1/support/users/nonexistent-id", headers=support_h)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_support_lookup_subscription_none(client: AsyncClient, db: AsyncSession):
    support_h = await _support_headers(client, db)
    uid, _ = await _create_target_user(client)

    resp = await client.get(f"/api/v1/support/users/{uid}/subscription", headers=support_h)
    assert resp.status_code == 200
    assert resp.json() is None


@pytest.mark.asyncio
async def test_support_lookup_subscription_exists(client: AsyncClient, db: AsyncSession):
    support_h = await _support_headers(client, db)
    uid, token = await _create_target_user(client)
    target_h = {"Authorization": f"Bearer {token}"}

    with patch("app.services.subscription_service.mamopay_client.create_payment_link",
               new_callable=AsyncMock, return_value=MOCK_LINK):
        await client.post("/api/v1/subscriptions/", headers=target_h)

    resp = await client.get(f"/api/v1/support/users/{uid}/subscription", headers=support_h)
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_support_deactivate_user(client: AsyncClient, db: AsyncSession):
    support_h = await _support_headers(client, db)
    uid, _ = await _create_target_user(client)

    resp = await client.post(f"/api/v1/support/users/{uid}/deactivate", headers=support_h)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_support_deactivate_not_found(client: AsyncClient, db: AsyncSession):
    support_h = await _support_headers(client, db)
    resp = await client.post("/api/v1/support/users/fake-id/deactivate", headers=support_h)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_can_access_support_routes(client: AsyncClient, admin_headers: dict, db: AsyncSession):
    """Admins should also be able to use support endpoints."""
    uid, _ = await _create_target_user(client)
    resp = await client.get(f"/api/v1/support/users/{uid}", headers=admin_headers)
    assert resp.status_code == 200
