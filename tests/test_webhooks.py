"""Tests for MamoPay webhook endpoint."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch, AsyncMock
from app.models.subscription import Subscription, Payment
from app.models.user import User
from sqlalchemy import select


MOCK_LINK = {"id": "link_123", "payment_url": "https://pay.mamopay.com/test"}


async def _create_user_with_subscription(client: AsyncClient, db: AsyncSession) -> tuple[str, str]:
    """Register a user, create a pending subscription, return (sub_id, user_id)."""
    reg = await client.post("/api/v1/auth/register", json={
        "email": "webhook@example.com", "password": "StrongPass1", "full_name": "Webhook User",
    })
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.services.subscription_service.mamopay_client.create_payment_link",
               new_callable=AsyncMock, return_value=MOCK_LINK):
        sub_resp = await client.post("/api/v1/subscriptions/", headers=headers)

    sub_id = sub_resp.json()["subscription_id"]
    profile = await client.get("/api/v1/users/me", headers=headers)
    user_id = profile.json()["id"]
    return sub_id, user_id


@pytest.mark.asyncio
async def test_webhook_payment_captured_activates_subscription(client: AsyncClient, db: AsyncSession):
    sub_id, user_id = await _create_user_with_subscription(client, db)

    resp = await client.post("/api/v1/webhooks/mamopay", json={
        "type": "payment.captured",
        "data": {"external_id": sub_id, "id": "charge_001"},
    })
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

    # Subscription should now be active
    sub = (await db.execute(select(Subscription).where(Subscription.id == sub_id))).scalar_one()
    assert sub.status == "active"
    assert sub.current_period_start is not None


@pytest.mark.asyncio
async def test_webhook_creates_payment_record(client: AsyncClient, db: AsyncSession):
    sub_id, user_id = await _create_user_with_subscription(client, db)

    await client.post("/api/v1/webhooks/mamopay", json={
        "type": "charge.succeeded",
        "data": {"external_id": sub_id, "id": "charge_002"},
    })

    payment = (await db.execute(
        select(Payment).where(Payment.mamopay_charge_id == "charge_002")
    )).scalar_one_or_none()
    assert payment is not None
    assert payment.status == "succeeded"
    assert payment.user_id == user_id


@pytest.mark.asyncio
async def test_webhook_unknown_event_returns_ok(client: AsyncClient):
    resp = await client.post("/api/v1/webhooks/mamopay", json={
        "type": "some.unknown.event",
        "data": {},
    })
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_webhook_missing_external_id_returns_ok(client: AsyncClient):
    resp = await client.post("/api/v1/webhooks/mamopay", json={
        "type": "payment.captured",
        "data": {"id": "charge_999"},
    })
    assert resp.status_code == 200
