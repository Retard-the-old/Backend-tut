from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.core.dependencies import get_current_user, require_active_subscription, require_admin
from app.models.user import User
from app.schemas.course import CourseResponse, CourseCreate, LessonResponse, LessonCreate, ProgressUpdate, ProgressResponse
from app.services.course_service import list_courses, get_course, create_course, get_lessons, create_lesson, update_progress, get_user_progress

router = APIRouter(prefix="/courses", tags=["courses"])

@router.get("/", response_model=list[CourseResponse])
async def list_all(db: AsyncSession = Depends(get_db)):
    courses = await list_courses(db, published_only=True)
    return [CourseResponse.model_validate(c) for c in courses]

@router.get("/{course_id}", response_model=CourseResponse)
async def get_one(course_id: str, db: AsyncSession = Depends(get_db)):
    return CourseResponse.model_validate(await get_course(course_id, db))

@router.post("/", response_model=CourseResponse, status_code=201)
async def create(data: CourseCreate, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return CourseResponse.model_validate(await create_course(data, db))

@router.get("/{course_id}/lessons", response_model=list[LessonResponse])
async def list_lessons(course_id: str, user: User = Depends(require_active_subscription), db: AsyncSession = Depends(get_db)):
    lessons = await get_lessons(course_id, db)
    return [LessonResponse.model_validate(l) for l in lessons]

@router.post("/{course_id}/lessons", response_model=LessonResponse, status_code=201)
async def add_lesson(course_id: str, data: LessonCreate, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return LessonResponse.model_validate(await create_lesson(course_id, data, db))

@router.put("/{course_id}/lessons/{lesson_id}/progress", response_model=ProgressResponse)
async def track_progress(course_id: str, lesson_id: str, data: ProgressUpdate, user: User = Depends(require_active_subscription), db: AsyncSession = Depends(get_db)):
    p = await update_progress(user.id, lesson_id, course_id, data, db)
    return ProgressResponse.model_validate(p)

@router.get("/{course_id}/progress", response_model=list[ProgressResponse])
async def my_progress(course_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    items = await get_user_progress(user.id, course_id, db)
    return [ProgressResponse.model_validate(p) for p in items]
