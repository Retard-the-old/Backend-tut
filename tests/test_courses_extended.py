"""Tests for course lessons and progress tracking."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch, AsyncMock

MOCK_LINK = {"id": "link_123", "payment_url": "https://pay.mamopay.com/test"}


async def _active_user_headers(client: AsyncClient) -> dict:
    """Register, subscribe and activate a user."""
    reg = await client.post("/api/v1/auth/register", json={
        "email": "student@example.com", "password": "StrongPass1", "full_name": "Student",
    })
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.services.subscription_service.mamopay_client.create_payment_link",
               new_callable=AsyncMock, return_value=MOCK_LINK):
        sub = await client.post("/api/v1/subscriptions/", headers=headers)
    sub_id = sub.json()["subscription_id"]
    await client.post("/api/v1/webhooks/mamopay", json={
        "type": "payment.captured",
        "data": {"external_id": sub_id, "id": "charge_student"},
    })
    return headers


@pytest.mark.asyncio
async def test_add_lesson_to_course(client: AsyncClient, admin_headers: dict):
    course = await client.post("/api/v1/courses/", headers=admin_headers, json={
        "title": "Python", "slug": "python", "is_published": True,
    })
    cid = course.json()["id"]

    resp = await client.post(f"/api/v1/courses/{cid}/lessons", headers=admin_headers, json={
        "title": "Variables", "content_md": "# Variables\nLearn about variables.",
        "duration_minutes": 15, "sort_order": 1, "is_published": True,
    })
    assert resp.status_code == 201
    assert resp.json()["title"] == "Variables"
    assert resp.json()["course_id"] == cid


@pytest.mark.asyncio
async def test_list_lessons_requires_subscription(client: AsyncClient, auth_headers: dict, admin_headers: dict):
    course = await client.post("/api/v1/courses/", headers=admin_headers, json={
        "title": "Math", "slug": "math", "is_published": True,
    })
    cid = course.json()["id"]

    # Regular user without active subscription
    resp = await client.get(f"/api/v1/courses/{cid}/lessons", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_lessons_with_subscription(client: AsyncClient, admin_headers: dict):
    headers = await _active_user_headers(client)

    course = await client.post("/api/v1/courses/", headers=admin_headers, json={
        "title": "Science", "slug": "science", "is_published": True,
    })
    cid = course.json()["id"]

    await client.post(f"/api/v1/courses/{cid}/lessons", headers=admin_headers, json={
        "title": "Atoms", "duration_minutes": 10, "is_published": True,
    })

    resp = await client.get(f"/api/v1/courses/{cid}/lessons", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_track_progress(client: AsyncClient, admin_headers: dict):
    headers = await _active_user_headers(client)

    course = await client.post("/api/v1/courses/", headers=admin_headers, json={
        "title": "History", "slug": "history", "is_published": True,
    })
    cid = course.json()["id"]

    lesson = await client.post(f"/api/v1/courses/{cid}/lessons", headers=admin_headers, json={
        "title": "WW2", "duration_minutes": 20, "is_published": True,
    })
    lid = lesson.json()["id"]

    resp = await client.put(
        f"/api/v1/courses/{cid}/lessons/{lid}/progress", headers=headers,
        json={"progress_pct": 50.0, "completed": False},
    )
    assert resp.status_code == 200
    assert resp.json()["progress_pct"] == 50.0
    assert resp.json()["completed"] is False


@pytest.mark.asyncio
async def test_complete_lesson_progress(client: AsyncClient, admin_headers: dict):
    headers = await _active_user_headers(client)

    course = await client.post("/api/v1/courses/", headers=admin_headers, json={
        "title": "Art", "slug": "art", "is_published": True,
    })
    cid = course.json()["id"]

    lesson = await client.post(f"/api/v1/courses/{cid}/lessons", headers=admin_headers, json={
        "title": "Colors", "duration_minutes": 5, "is_published": True,
    })
    lid = lesson.json()["id"]

    resp = await client.put(
        f"/api/v1/courses/{cid}/lessons/{lid}/progress", headers=headers,
        json={"progress_pct": 100.0, "completed": True},
    )
    assert resp.status_code == 200
    assert resp.json()["completed"] is True
    assert resp.json()["completed_at"] is not None


@pytest.mark.asyncio
async def test_get_my_progress(client: AsyncClient, admin_headers: dict):
    headers = await _active_user_headers(client)

    course = await client.post("/api/v1/courses/", headers=admin_headers, json={
        "title": "Music", "slug": "music", "is_published": True,
    })
    cid = course.json()["id"]

    lesson = await client.post(f"/api/v1/courses/{cid}/lessons", headers=admin_headers, json={
        "title": "Notes", "duration_minutes": 10, "is_published": True,
    })
    lid = lesson.json()["id"]

    await client.put(
        f"/api/v1/courses/{cid}/lessons/{lid}/progress", headers=headers,
        json={"progress_pct": 75.0, "completed": False},
    )

    resp = await client.get(f"/api/v1/courses/{cid}/progress", headers=headers)
    assert resp.status_code == 200
    progress = resp.json()
    assert len(progress) == 1
    assert progress[0]["progress_pct"] == 75.0


@pytest.mark.asyncio
async def test_add_lesson_requires_admin(client: AsyncClient, auth_headers: dict, admin_headers: dict):
    course = await client.post("/api/v1/courses/", headers=admin_headers, json={
        "title": "Geo", "slug": "geo", "is_published": True,
    })
    cid = course.json()["id"]

    resp = await client.post(f"/api/v1/courses/{cid}/lessons", headers=auth_headers, json={
        "title": "Maps", "duration_minutes": 5,
    })
    assert resp.status_code == 403
