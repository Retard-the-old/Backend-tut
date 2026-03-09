"""Tests for authentication endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "new@example.com",
        "password": "StrongPass1",
        "full_name": "New User",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    payload = {"email": "dup@example.com", "password": "StrongPass1", "full_name": "User"}
    await client.post("/api/v1/auth/register", json=payload)
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_invalid_referral_code(client: AsyncClient):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "ref@example.com",
        "password": "StrongPass1",
        "full_name": "Ref User",
        "referral_code": "NONEXIST",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_register_with_valid_referral(client: AsyncClient):
    # Register referrer
    r1 = await client.post("/api/v1/auth/register", json={
        "email": "referrer@example.com", "password": "StrongPass1", "full_name": "Referrer",
    })
    # Get referrer profile to find their referral code
    token = r1.json()["access_token"]
    profile = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    code = profile.json()["referral_code"]

    # Register with referral code
    r2 = await client.post("/api/v1/auth/register", json={
        "email": "referred@example.com", "password": "StrongPass1",
        "full_name": "Referred", "referral_code": code,
    })
    assert r2.status_code == 201


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "login@example.com", "password": "StrongPass1", "full_name": "Login User",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": "login@example.com", "password": "StrongPass1",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "wrong@example.com", "password": "StrongPass1", "full_name": "Wrong",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": "wrong@example.com", "password": "BadPassword1",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_email(client: AsyncClient):
    resp = await client.post("/api/v1/auth/login", json={
        "email": "nobody@example.com", "password": "Whatever1",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient):
    reg = await client.post("/api/v1/auth/register", json={
        "email": "refresh@example.com", "password": "StrongPass1", "full_name": "Refresh",
    })
    refresh_token = reg.json()["refresh_token"]
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_refresh_invalid_token(client: AsyncClient):
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": "garbage"})
    assert resp.status_code == 401
