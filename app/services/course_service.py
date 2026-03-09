from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from app.models.course import Course, Lesson, LessonProgress
from app.schemas.course import CourseCreate, LessonCreate, ProgressUpdate

async def list_courses(db: AsyncSession, published_only: bool = True) -> list[Course]:
    q = select(Course).order_by(Course.sort_order)
    if published_only:
        q = q.where(Course.is_published == True)
    return list((await db.execute(q)).scalars().all())

async def get_course(course_id: str, db: AsyncSession) -> Course:
    result = await db.execute(select(Course).where(Course.id == course_id).options(selectinload(Course.lessons)))
    course = result.scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course

async def create_course(data: CourseCreate, db: AsyncSession) -> Course:
    course = Course(**data.model_dump())
    db.add(course)
    await db.flush()
    return course

async def get_lessons(course_id: str, db: AsyncSession) -> list[Lesson]:
    return list((await db.execute(
        select(Lesson).where(Lesson.course_id == course_id).order_by(Lesson.sort_order)
    )).scalars().all())

async def create_lesson(course_id: str, data: LessonCreate, db: AsyncSession) -> Lesson:
    await get_course(course_id, db)
    lesson = Lesson(course_id=course_id, **data.model_dump())
    db.add(lesson)
    await db.flush()
    return lesson

async def update_progress(user_id: str, lesson_id: str, course_id: str, data: ProgressUpdate, db: AsyncSession) -> LessonProgress:
    result = await db.execute(select(LessonProgress).where(LessonProgress.user_id == user_id, LessonProgress.lesson_id == lesson_id))
    progress = result.scalar_one_or_none()
    if progress is None:
        progress = LessonProgress(user_id=user_id, lesson_id=lesson_id, course_id=course_id)
        db.add(progress)
    progress.progress_pct = data.progress_pct
    progress.completed = data.completed
    if data.completed and progress.completed_at is None:
        progress.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return progress

async def get_user_progress(user_id: str, course_id: str, db: AsyncSession) -> list[LessonProgress]:
    return list((await db.execute(
        select(LessonProgress).where(LessonProgress.user_id == user_id, LessonProgress.course_id == course_id)
    )).scalars().all())
