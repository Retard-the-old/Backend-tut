from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.subscription import Subscription
from app.schemas.user import UserResponse
from app.schemas.subscription import SubscriptionResponse

router = APIRouter(prefix="/support", tags=["support"])

async def require_support_or_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("admin", "support"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Support or admin access required")
    return user

@router.get("/users/{user_id}", response_model=UserResponse)
async def lookup_user(user_id: str, staff: User = Depends(require_support_or_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse.model_validate(user)

@router.get("/users/{user_id}/subscription", response_model=SubscriptionResponse | None)
async def lookup_subscription(user_id: str, staff: User = Depends(require_support_or_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Subscription).where(Subscription.user_id == user_id).order_by(Subscription.created_at.desc()))
    sub = result.scalar_one_or_none()
    return SubscriptionResponse.model_validate(sub) if sub else None

@router.post("/users/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(user_id: str, staff: User = Depends(require_support_or_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.is_active = False
    await db.flush()
    return UserResponse.model_validate(user)
