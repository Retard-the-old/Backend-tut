from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.subscription import SubscriptionResponse, CreateSubscriptionResponse
from app.services.subscription_service import (
    create_subscription, cancel_subscription, get_user_subscription,
    verify_and_activate, verify_payment_and_register,
)
from pydantic import BaseModel


router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


class VerifyAndRegisterRequest(BaseModel):
    email: str
    full_name: str
    password: str
    phone: str = ""
    referral_code: str | None = None


@router.post("/", response_model=CreateSubscriptionResponse, status_code=201)
async def subscribe(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await create_subscription(user, db)


@router.get("/me", response_model=SubscriptionResponse | None)
async def my_subscription(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await get_user_subscription(user, db)


@router.post("/cancel", response_model=SubscriptionResponse)
async def cancel(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await cancel_subscription(user, db)


@router.post("/verify-payment")
async def verify_payment(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticated. Queries MamoPay charges by the logged-in user's email.
    Activates subscription if a captured payment is found.
    Called when user clicks "I've paid".
    """
    return await verify_and_activate(user, db)


@router.post("/verify-payment-and-register")
async def verify_payment_and_register_endpoint(
    data: VerifyAndRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    No auth required. Verifies MamoPay payment by email,
    then creates account + activates subscription + returns tokens.
    """
    return await verify_payment_and_register(data.dict(), db)
