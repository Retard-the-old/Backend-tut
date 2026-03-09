"""Tests for payout and commission endpoints."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.commission import Commission, Payout
from app.models.user import User
from sqlalchemy import select


@pytest.mark.asyncio
async def test_my_payouts_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/payouts/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_my_commissions_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/payouts/me/commissions", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_my_commissions_returns_data(client: AsyncClient, auth_headers: dict, db: AsyncSession):
    """Insert a commission directly and verify the endpoint returns it."""
    # Get the user id
    profile = await client.get("/api/v1/users/me", headers=auth_headers)
    uid = profile.json()["id"]

    comm = Commission(
        earner_id=uid, source_user_id=uid,
        level=1, amount_aed=38.0, status="pending",
    )
    db.add(comm)
    await db.commit()

    resp = await client.get("/api/v1/payouts/me/commissions", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["amount_aed"] == 38.0
    assert data[0]["level"] == 1


@pytest.mark.asyncio
async def test_my_payouts_returns_data(client: AsyncClient, auth_headers: dict, db: AsyncSession):
    """Insert a payout directly and verify the endpoint returns it."""
    profile = await client.get("/api/v1/users/me", headers=auth_headers)
    uid = profile.json()["id"]

    payout = Payout(earner_id=uid, amount_aed=100.0, status="completed")
    db.add(payout)
    await db.commit()

    resp = await client.get("/api/v1/payouts/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["amount_aed"] == 100.0
    assert data[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_payouts_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/payouts/me")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_commissions_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/payouts/me/commissions")
    assert resp.status_code == 403
