from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.commission import Commission, Payout
from app.schemas.payout import PayoutResponse, CommissionResponse

router = APIRouter(prefix="/payouts", tags=["payouts"])

@router.get("/me", response_model=list[PayoutResponse])
async def my_payouts(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Payout).where(Payout.earner_id == user.id).order_by(Payout.created_at.desc()))
    return [PayoutResponse.model_validate(p) for p in result.scalars().all()]

@router.get("/me/commissions", response_model=list[CommissionResponse])
async def my_commissions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Commission).where(Commission.earner_id == user.id).order_by(Commission.created_at.desc()).limit(100))
    return [CommissionResponse.model_validate(c) for c in result.scalars().all()]
