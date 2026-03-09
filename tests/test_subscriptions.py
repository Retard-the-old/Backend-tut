"""Tests for subscription endpoints."""
import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock


MOCK_LINK = {"id": "link_123", "payment_url": "https://pay.mamopay.com/test"}


@pytest.mark.asyncio
async def test_create_subscription(client: AsyncClient, auth_headers: dict):
    with patch("app.services.subscription_service.mamopay_client.create_payment_link",
               new_callable=AsyncMock, return_value=MOCK_LINK):
        resp = await client.post("/api/v1/subscriptions/", headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert "subscription_id" in data
        assert data["payment_link"] == "https://pay.mamopay.com/test"


@pytest.mark.asyncio
async def test_create_duplicate_subscription(client: AsyncClient, auth_headers: dict):
    with patch("app.services.subscription_service.mamopay_client.create_payment_link",
               new_callable=AsyncMock, return_value=MOCK_LINK):
        await client.post("/api/v1/subscriptions/", headers=auth_headers)
        resp = await client.post("/api/v1/subscriptions/", headers=auth_headers)
        assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_subscription(client: AsyncClient, auth_headers: dict):
    with patch("app.services.subscription_service.mamopay_client.create_payment_link",
               new_callable=AsyncMock, return_value=MOCK_LINK):
        await client.post("/api/v1/subscriptions/", headers=auth_headers)
    resp = await client.get("/api/v1/subscriptions/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_get_subscription_none(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/subscriptions/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() is None
