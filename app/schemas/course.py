from __future__ import annotations
from pydantic import BaseModel
from datetime import datetime

class CourseResponse(BaseModel):
    id: str
    title: str
    slug: str
    description: str | None
    category: str | None
    thumbnail_url: str | None
    is_published: bool
    sort_order: int
    created_at: datetime
    model_config = {"from_attributes": True}

class CourseCreate(BaseModel):
    title: str
    slug: str
    description: str | None = None
    category: str | None = None
    thumbnail_url: str | None = None
    is_published: bool = False
    sort_order: int = 0

class LessonResponse(BaseModel):
    id: str
    course_id: str
    title: str
    content_md: str | None
    video_url: str | None
    duration_minutes: int
    sort_order: int
    is_published: bool
    model_config = {"from_attributes": True}

class LessonCreate(BaseModel):
    title: str
    content_md: str | None = None
    video_url: str | None = None
    duration_minutes: int = 0
    sort_order: int = 0
    is_published: bool = False

class LessonUpdate(BaseModel):
    title: str | None = None
    content_md: str | None = None
    video_url: str | None = None
    duration_minutes: int | None = None
    sort_order: int | None = None
    is_published: bool | None = None

class ProgressUpdate(BaseModel):
    progress_pct: float = 0.0
    completed: bool = False

class ProgressResponse(BaseModel):
    lesson_id: str
    course_id: str
    completed: bool
    progress_pct: float
    completed_at: datetime | None
    model_config = {"from_attributes": True}
