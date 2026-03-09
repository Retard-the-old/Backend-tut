"""Tests for user endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/users/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "test@example.com"
    assert data["full_name"] == "Test User"
    assert data["role"] == "user"
    assert len(data["referral_code"]) == 8


@pytest.mark.asyncio
async def test_get_me_unauthorized(client: AsyncClient):
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 403  # no auth header


@pytest.mark.asyncio
async def test_update_me(client: AsyncClient, auth_headers: dict):
    resp = await client.patch("/api/v1/users/me", headers=auth_headers, json={
        "full_name": "Updated Name",
        "payout_iban": "AE070331234567890123456",
        "payout_name": "Updated Name",
    })
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Updated Name"
    assert resp.json()["payout_iban"] == "AE070331234567890123456"


@pytest.mark.asyncio
async def test_get_referral_stats(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/users/me/referrals", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_l1_referrals"] == 0
    assert data["total_l2_referrals"] == 0
    assert data["total_earned_aed"] == 0.0
