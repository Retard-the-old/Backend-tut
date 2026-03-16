from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import get_db
from app.core.dependencies import get_current_user, require_active_subscription, require_admin
from app.models.user import User
from app.models.course import Course, Lesson
from app.schemas.course import CourseResponse, CourseCreate, LessonResponse, LessonCreate, LessonUpdate, ProgressUpdate, ProgressResponse
from app.services.course_service import list_courses, get_course, create_course, get_lessons, create_lesson, update_progress, get_user_progress

router = APIRouter(prefix="/courses", tags=["courses"])

@router.get("/", response_model=list[CourseResponse])
async def list_all(db: AsyncSession = Depends(get_db)):
    courses = await list_courses(db, published_only=False)
    return [CourseResponse.model_validate(c) for c in courses]

@router.get("/{course_id}", response_model=CourseResponse)
async def get_one(course_id: str, db: AsyncSession = Depends(get_db)):
    return CourseResponse.model_validate(await get_course(course_id, db))

@router.post("/", response_model=CourseResponse, status_code=201)
async def create(data: CourseCreate, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return CourseResponse.model_validate(await create_course(data, db))

@router.patch("/{course_id}", response_model=CourseResponse)
async def patch_course(course_id: str, data: dict, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    for field, value in data.items():
        if hasattr(course, field):
            setattr(course, field, value)
    await db.flush()
    return CourseResponse.model_validate(course)

@router.delete("/{course_id}", status_code=204)
async def delete_course(course_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    await db.delete(course)

@router.get("/{course_id}/lessons", response_model=list[LessonResponse])
async def list_lessons(course_id: str, user: User = Depends(require_active_subscription), db: AsyncSession = Depends(get_db)):
    lessons = await get_lessons(course_id, db)
    return [LessonResponse.model_validate(l) for l in lessons]

@router.post("/{course_id}/lessons", response_model=LessonResponse, status_code=201)
async def add_lesson(course_id: str, data: LessonCreate, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return LessonResponse.model_validate(await create_lesson(course_id, data, db))

@router.patch("/{course_id}/lessons/{lesson_id}", response_model=LessonResponse)
async def patch_lesson(course_id: str, lesson_id: str, data: LessonUpdate, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Lesson).where(Lesson.id == lesson_id, Lesson.course_id == course_id))
    lesson = result.scalar_one_or_none()
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(lesson, field, value)
    await db.flush()
    return LessonResponse.model_validate(lesson)

@router.delete("/{course_id}/lessons/{lesson_id}", status_code=204)
async def delete_lesson(course_id: str, lesson_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Lesson).where(Lesson.id == lesson_id, Lesson.course_id == course_id))
    lesson = result.scalar_one_or_none()
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    await db.delete(lesson)

@router.put("/{course_id}/lessons/{lesson_id}/progress", response_model=ProgressResponse)
async def track_progress(course_id: str, lesson_id: str, data: ProgressUpdate, user: User = Depends(require_active_subscription), db: AsyncSession = Depends(get_db)):
    p = await update_progress(user.id, lesson_id, course_id, data, db)
    return ProgressResponse.model_validate(p)

@router.get("/{course_id}/progress", response_model=list[ProgressResponse])
async def my_progress(course_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    items = await get_user_progress(user.id, course_id, db)
    return [ProgressResponse.model_validate(p) for p in items]
