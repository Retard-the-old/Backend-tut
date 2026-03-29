"""
Subscription service — uses a fixed MamoPay subscription link.
When user subscribes, they are redirected to the MamoPay page.
MamoPay handles recurring billing. Webhook activates the account on payment.
"""
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.subscription import SubscriptionResponse
from app.core.config import settings

# Fixed MamoPay subscription link — update this if you change the plan
MAMOPAY_SUBSCRIPTION_URL = "https://business.mamopay.com/pay/galcofzellc-a57db4"


async def create_subscription(user: User, db: AsyncSession) -> dict:
    """
    Returns the MamoPay payment link.
    Does NOT create a subscription record — that happens when webhook confirms payment.
    """
    # Check if already active
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id, Subscription.status == "active")
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have an active subscription"
        )

    return {
        "subscription_id": None,
        "payment_link": MAMOPAY_SUBSCRIPTION_URL,
        "status": "pending"
    }


async def cancel_subscription(user: User, db: AsyncSession) -> SubscriptionResponse:
    result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.status == "active"
        )
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found"
        )
    sub.status = "cancelled"
    from datetime import timezone
    sub.cancelled_at = datetime.now(timezone.utc)
    await db.flush()
    return SubscriptionResponse.model_validate(sub)


async def get_user_subscription(user: User, db: AsyncSession) -> SubscriptionResponse | None:
    result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id
        ).order_by(Subscription.created_at.desc())
    )
    sub = result.scalars().first()
    if sub is None:
        return None
    return SubscriptionResponse.model_validate(sub)
