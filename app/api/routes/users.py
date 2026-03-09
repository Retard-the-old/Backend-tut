from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.core.dependencies import get_current_user
from app.core.validators import validate_iban, validate_full_name
from app.models.user import User
from app.schemas.user import UserResponse, UserUpdate, ReferralStats
from app.services.referral_service import get_referral_stats

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return UserResponse.model_validate(user)

@router.patch("/me", response_model=UserResponse)
async def update_me(data: UserUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if data.payout_iban is not None:
        data.payout_iban = validate_iban(data.payout_iban)
    if data.full_name is not None:
        data.full_name = validate_full_name(data.full_name)
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.payout_iban is not None:
        user.payout_iban = data.payout_iban
    if data.payout_name is not None:
        user.payout_name = data.payout_name
    await db.flush()
    return UserResponse.model_validate(user)

@router.get("/me/referrals", response_model=ReferralStats)
async def get_my_referrals(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await get_referral_stats(user, db)
