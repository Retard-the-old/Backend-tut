"""Tests for course endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_courses_empty(client: AsyncClient):
    resp = await client.get("/api/v1/courses/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_course_requires_admin(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/v1/courses/", headers=auth_headers, json={
        "title": "Test Course", "slug": "test-course",
    })
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_and_list_course(client: AsyncClient, admin_headers: dict):
    resp = await client.post("/api/v1/courses/", headers=admin_headers, json={
        "title": "Python Basics", "slug": "python-basics",
        "description": "Learn Python", "is_published": True,
    })
    assert resp.status_code == 201
    assert resp.json()["title"] == "Python Basics"

    # Now list
    resp2 = await client.get("/api/v1/courses/")
    assert resp2.status_code == 200
    assert len(resp2.json()) == 1


@pytest.mark.asyncio
async def test_get_course(client: AsyncClient, admin_headers: dict):
    create = await client.post("/api/v1/courses/", headers=admin_headers, json={
        "title": "Math 101", "slug": "math-101", "is_published": True,
    })
    course_id = create.json()["id"]
    resp = await client.get(f"/api/v1/courses/{course_id}")
    assert resp.status_code == 200
    assert resp.json()["slug"] == "math-101"


@pytest.mark.asyncio
async def test_get_course_not_found(client: AsyncClient):
    resp = await client.get("/api/v1/courses/nonexistent-id")
    assert resp.status_code == 404
