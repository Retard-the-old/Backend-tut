from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.user import User
from app.models.commission import Commission
from app.schemas.user import ReferralStats

async def get_referral_stats(user: User, db: AsyncSession) -> ReferralStats:
    l1_count = (await db.execute(select(func.count()).where(User.referred_by_id == user.id))).scalar() or 0

    l1_ids = [r[0] for r in (await db.execute(select(User.id).where(User.referred_by_id == user.id))).all()]
    l2_count = 0
    if l1_ids:
        l2_count = (await db.execute(select(func.count()).where(User.referred_by_id.in_(l1_ids)))).scalar() or 0

    total_earned = float((await db.execute(
        select(func.coalesce(func.sum(Commission.amount_aed), 0.0)).where(Commission.earner_id == user.id)
    )).scalar())

    pending = float((await db.execute(
        select(func.coalesce(func.sum(Commission.amount_aed), 0.0)).where(
            Commission.earner_id == user.id, Commission.status.in_(["pending", "approved"])
        )
    )).scalar())

    paid = float((await db.execute(
        select(func.coalesce(func.sum(Commission.amount_aed), 0.0)).where(
            Commission.earner_id == user.id, Commission.status == "paid"
        )
    )).scalar())

    return ReferralStats(
        referral_code=user.referral_code, total_l1_referrals=l1_count,
        total_l2_referrals=l2_count, total_earned_aed=total_earned,
        pending_aed=pending, paid_aed=paid,
    )
