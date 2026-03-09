from __future__ import annotations
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
from app.models.subscription import Subscription, Payment
from app.models.user import User
from app.clients.mamopay import mamopay_client
from app.core.config import settings
from app.schemas.subscription import CreateSubscriptionResponse, SubscriptionResponse
from app.services.email_service import send_subscription_cancelled

async def create_subscription(user: User, db: AsyncSession) -> CreateSubscriptionResponse:
    existing = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id, Subscription.status.in_(["active", "pending"]))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Active subscription already exists")

    sub = Subscription(user_id=user.id, plan_price_aed=settings.SUBSCRIPTION_PRICE_AED, status="pending")
    db.add(sub)
    await db.flush()

    link_data = await mamopay_client.create_payment_link(
        amount=settings.SUBSCRIPTION_PRICE_AED,
        title=f"Tutorii Monthly - {user.full_name}",
        description="Tutorii monthly tutoring subscription",
        customer_email=user.email, customer_name=user.full_name,
        external_id=sub.id, is_recurring=True,
    )
    sub.mamopay_subscription_id = link_data.get("id", "")
    sub.mamopay_payment_link = link_data.get("payment_url", link_data.get("link_url", ""))
    return CreateSubscriptionResponse(subscription_id=sub.id, payment_link=sub.mamopay_payment_link or "")

async def activate_subscription(subscription_id: str, charge_id: str, db: AsyncSession) -> None:
    result = await db.execute(select(Subscription).where(Subscription.id == subscription_id))
    sub = result.scalar_one_or_none()
    if sub is None:
        return
    now = datetime.now(timezone.utc)
    sub.status = "active"
    sub.current_period_start = now
    sub.current_period_end = now + timedelta(days=30)
    payment = Payment(
        subscription_id=sub.id, user_id=sub.user_id,
        amount_aed=sub.plan_price_aed, status="succeeded", mamopay_charge_id=charge_id,
    )
    db.add(payment)
    await db.flush()

async def cancel_subscription(user: User, db: AsyncSession) -> SubscriptionResponse:
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id, Subscription.status == "active")
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active subscription found")
    sub.status = "cancelled"
    sub.cancelled_at = datetime.now(timezone.utc)
    await send_subscription_cancelled(user.email, user.full_name)
    if sub.mamopay_subscription_id:
        try:
            await mamopay_client.deactivate_payment_link(sub.mamopay_subscription_id)
        except Exception:
            pass
    return SubscriptionResponse.model_validate(sub)

async def get_user_subscription(user: User, db: AsyncSession) -> SubscriptionResponse | None:
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id).order_by(Subscription.created_at.desc())
    )
    sub = result.scalar_one_or_none()
    return SubscriptionResponse.model_validate(sub) if sub else None
