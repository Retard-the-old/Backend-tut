from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User
from app.models.commission import Commission
from app.models.subscription import Payment
from app.core.config import settings
import logging
logger = logging.getLogger(__name__)

async def create_commissions_for_payment(payment: Payment, db: AsyncSession) -> list[Commission]:
    commissions: list[Commission] = []
    result = await db.execute(select(User).where(User.id == payment.user_id))
    payer = result.scalar_one_or_none()
    if payer is None or payer.referred_by_id is None:
        return commissions

    # L1 commission
    l1 = (await db.execute(select(User).where(User.id == payer.referred_by_id))).scalar_one_or_none()
    if l1:
        c1 = Commission(
            earner_id=l1.id, source_user_id=payer.id, payment_id=payment.id,
            level=1, amount_aed=settings.l1_commission_aed, status="pending",
        )
        db.add(c1)
        commissions.append(c1)
        logger.info("L1 commission %.2f AED -> %s", settings.l1_commission_aed, l1.email)

        # L2 commission
        if l1.referred_by_id:
            l2 = (await db.execute(select(User).where(User.id == l1.referred_by_id))).scalar_one_or_none()
            if l2:
                c2 = Commission(
                    earner_id=l2.id, source_user_id=payer.id, payment_id=payment.id,
                    level=2, amount_aed=settings.l2_commission_aed, status="pending",
                )
                db.add(c2)
                commissions.append(c2)
                logger.info("L2 commission %.2f AED -> %s", settings.l2_commission_aed, l2.email)

    await db.flush()
    return commissions
