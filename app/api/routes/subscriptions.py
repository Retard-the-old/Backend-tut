from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.subscription import SubscriptionResponse, CreateSubscriptionResponse
from app.services.subscription_service import create_subscription, cancel_subscription, get_user_subscription

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

@router.post("/", response_model=CreateSubscriptionResponse, status_code=201)
async def subscribe(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_subscription(user, db)

@router.get("/me", response_model=SubscriptionResponse | None)
async def my_subscription(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await get_user_subscription(user, db)

@router.post("/cancel", response_model=SubscriptionResponse)
async def cancel(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await cancel_subscription(user, db)
