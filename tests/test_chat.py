"""Tests for chat endpoints (require active subscription)."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch, AsyncMock
from app.models.subscription import Subscription
from app.models.user import User
from sqlalchemy import select, update


MOCK_LINK = {"id": "link_123", "payment_url": "https://pay.mamopay.com/test"}
MOCK_CLAUDE = {"content": "Hello! I can help you learn.", "usage": {"input_tokens": 10, "output_tokens": 20}}


async def _setup_active_user(client: AsyncClient, db: AsyncSession) -> dict:
    """Register, subscribe, activate, return auth headers."""
    reg = await client.post("/api/v1/auth/register", json={
        "email": "chatter@example.com", "password": "StrongPass1", "full_name": "Chat User",
    })
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.services.subscription_service.mamopay_client.create_payment_link",
               new_callable=AsyncMock, return_value=MOCK_LINK):
        sub_resp = await client.post("/api/v1/subscriptions/", headers=headers)
    sub_id = sub_resp.json()["subscription_id"]

    # Activate via webhook
    await client.post("/api/v1/webhooks/mamopay", json={
        "type": "payment.captured",
        "data": {"external_id": sub_id, "id": "charge_chat"},
    })
    return headers


@pytest.mark.asyncio
async def test_chat_requires_active_subscription(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/v1/chat/messages", headers=auth_headers, json={
        "content": "Hello",
    })
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_send_message_creates_session(client: AsyncClient, db: AsyncSession):
    headers = await _setup_active_user(client, db)

    with patch("app.services.chat_service.claude_client.chat",
               new_callable=AsyncMock, return_value=MOCK_CLAUDE):
        resp = await client.post("/api/v1/chat/messages", headers=headers, json={
            "content": "What is algebra?",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert data["user_message"]["role"] == "user"
    assert data["assistant_message"]["role"] == "assistant"
    assert data["assistant_message"]["content"] == "Hello! I can help you learn."


@pytest.mark.asyncio
async def test_send_message_to_existing_session(client: AsyncClient, db: AsyncSession):
    headers = await _setup_active_user(client, db)

    with patch("app.services.chat_service.claude_client.chat",
               new_callable=AsyncMock, return_value=MOCK_CLAUDE):
        r1 = await client.post("/api/v1/chat/messages", headers=headers, json={
            "content": "First message",
        })
        session_id = r1.json()["session_id"]

        r2 = await client.post("/api/v1/chat/messages", headers=headers, json={
            "content": "Follow up",
            "session_id": session_id,
        })
    assert r2.status_code == 200
    assert r2.json()["session_id"] == session_id


@pytest.mark.asyncio
async def test_send_message_invalid_session(client: AsyncClient, db: AsyncSession):
    headers = await _setup_active_user(client, db)

    with patch("app.services.chat_service.claude_client.chat",
               new_callable=AsyncMock, return_value=MOCK_CLAUDE):
        resp = await client.post("/api/v1/chat/messages", headers=headers, json={
            "content": "Hello",
            "session_id": "nonexistent-session-id",
        })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_sessions_empty(client: AsyncClient, db: AsyncSession):
    headers = await _setup_active_user(client, db)
    resp = await client.get("/api/v1/chat/sessions", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_sessions_after_chat(client: AsyncClient, db: AsyncSession):
    headers = await _setup_active_user(client, db)

    with patch("app.services.chat_service.claude_client.chat",
               new_callable=AsyncMock, return_value=MOCK_CLAUDE):
        await client.post("/api/v1/chat/messages", headers=headers, json={"content": "Hello"})

    resp = await client.get("/api/v1/chat/sessions", headers=headers)
    assert resp.status_code == 200
    sessions = resp.json()
    assert len(sessions) == 1
    assert sessions[0]["message_count"] == 2


@pytest.mark.asyncio
async def test_get_session_messages(client: AsyncClient, db: AsyncSession):
    headers = await _setup_active_user(client, db)

    with patch("app.services.chat_service.claude_client.chat",
               new_callable=AsyncMock, return_value=MOCK_CLAUDE):
        r = await client.post("/api/v1/chat/messages", headers=headers, json={"content": "Teach me"})
    session_id = r.json()["session_id"]

    resp = await client.get(f"/api/v1/chat/sessions/{session_id}/messages", headers=headers)
    assert resp.status_code == 200
    msgs = resp.json()
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_get_session_messages_not_found(client: AsyncClient, db: AsyncSession):
    headers = await _setup_active_user(client, db)
    resp = await client.get("/api/v1/chat/sessions/fake-id/messages", headers=headers)
    assert resp.status_code == 404
