"""Extended subscription tests — cancel flow and edge cases."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch, AsyncMock

MOCK_LINK = {"id": "link_123", "payment_url": "https://pay.mamopay.com/test"}


@pytest.mark.asyncio
async def test_cancel_no_active_subscription(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/v1/subscriptions/cancel", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_active_subscription(client: AsyncClient, auth_headers: dict):
    # Create and activate subscription
    with patch("app.services.subscription_service.mamopay_client.create_payment_link",
               new_callable=AsyncMock, return_value=MOCK_LINK):
        sub_resp = await client.post("/api/v1/subscriptions/", headers=auth_headers)
    sub_id = sub_resp.json()["subscription_id"]

    # Activate via webhook
    await client.post("/api/v1/webhooks/mamopay", json={
        "type": "payment.captured",
        "data": {"external_id": sub_id, "id": "charge_cancel"},
    })

    with patch("app.services.subscription_service.mamopay_client.deactivate_payment_link",
               new_callable=AsyncMock, return_value={}), \
         patch("app.services.email_service.ses_client.send_email",
               new_callable=AsyncMock):
        resp = await client.post("/api/v1/subscriptions/cancel", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    assert resp.json()["cancelled_at"] is not None


@pytest.mark.asyncio
async def test_cancel_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/subscriptions/cancel")
    assert resp.status_code == 403
