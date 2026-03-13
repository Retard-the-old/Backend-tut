from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import get_db
from app.core.dependencies import get_current_user
from app.core.validators import validate_iban, validate_full_name
from app.models.user import User
from app.models.subscription import Subscription
from app.models.commission import Commission
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

@router.get("/me/referrals/list")
async def get_referral_list(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Get L1 referrals (people who used this user's referral code)
    l1_result = await db.execute(select(User).where(User.referred_by_id == user.id))
    l1_users = l1_result.scalars().all()
    l1_ids = [u.id for u in l1_users]

    # Get subscriptions for L1 users
    l1_subs = {}
    if l1_ids:
        subs_result = await db.execute(select(Subscription).where(Subscription.user_id.in_(l1_ids)))
        for sub in subs_result.scalars().all():
            l1_subs[sub.user_id] = sub.status

    # Get commissions earned per L1 user
    l1_commissions = {}
    if l1_ids:
        comms_result = await db.execute(
            select(Commission).where(Commission.earner_id == user.id, Commission.source_user_id.in_(l1_ids))
        )
        for c in comms_result.scalars().all():
            l1_commissions[c.source_user_id] = l1_commissions.get(c.source_user_id, 0) + c.amount_aed

    l1_list = [
        {
            "id": u.id,
            "name": u.full_name,
            "email": u.email,
            "joined_at": u.created_at.isoformat(),
            "subscription_status": l1_subs.get(u.id, "inactive"),
            "commission_earned": round(l1_commissions.get(u.id, 0), 2),
        }
        for u in l1_users
    ]

    # Get L2 referrals (people referred by L1 users)
    l2_list = []
    if l1_ids:
        l2_result = await db.execute(select(User).where(User.referred_by_id.in_(l1_ids)))
        l2_users = l2_result.scalars().all()
        l2_ids = [u.id for u in l2_users]

        # Map L1 user id to name for display
        l1_name_map = {u.id: u.full_name for u in l1_users}

        # Get commissions earned per L2 user
        l2_commissions = {}
        if l2_ids:
            l2_comms_result = await db.execute(
                select(Commission).where(Commission.earner_id == user.id, Commission.source_user_id.in_(l2_ids))
            )
            for c in l2_comms_result.scalars().all():
                l2_commissions[c.source_user_id] = l2_commissions.get(c.source_user_id, 0) + c.amount_aed

        l2_list = [
            {
                "id": u.id,
                "name": u.full_name,
                "email": u.email,
                "joined_at": u.created_at.isoformat(),
                "referred_by_name": l1_name_map.get(u.referred_by_id, ""),
                "commission_earned": round(l2_commissions.get(u.id, 0), 2),
            }
            for u in l2_users
        ]

    return {"level1": l1_list, "level2": l2_list}
