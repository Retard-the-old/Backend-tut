"""Tests for admin endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_dashboard_requires_admin(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/admin/dashboard", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_dashboard_success(client: AsyncClient, admin_headers: dict):
    resp = await client.get("/api/v1/admin/dashboard", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_users" in data
    assert "active_subscribers" in data
    assert "total_revenue_aed" in data


@pytest.mark.asyncio
async def test_list_users(client: AsyncClient, admin_headers: dict):
    resp = await client.get("/api/v1/admin/users", headers=admin_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_update_role(client: AsyncClient, admin_headers: dict):
    # Register a normal user
    reg = await client.post("/api/v1/auth/register", json={
        "email": "promote@example.com", "password": "StrongPass1", "full_name": "Promo User",
    })
    # Get their user ID
    token = reg.json()["access_token"]
    profile = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    uid = profile.json()["id"]

    resp = await client.patch(f"/api/v1/admin/users/{uid}/role", headers=admin_headers, json={"role": "support"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "support"


@pytest.mark.asyncio
async def test_update_role_invalid(client: AsyncClient, admin_headers: dict):
    reg = await client.post("/api/v1/auth/register", json={
        "email": "badrole@example.com", "password": "StrongPass1", "full_name": "Bad Role",
    })
    token = reg.json()["access_token"]
    profile = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    uid = profile.json()["id"]

    resp = await client.patch(f"/api/v1/admin/users/{uid}/role", headers=admin_headers, json={"role": "superadmin"})
    assert resp.status_code == 400
