from fastapi import APIRouter, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import get_db
from app.models.subscription import Subscription, Payment
from app.models.user import User
from fastapi import Depends
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/mamopay")
async def mamopay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        payload = await request.json()
    except Exception:
        return {"received": True, "error": "invalid json"}

    logger.info(f"MamoPay webhook received: {payload}")

    event_type = payload.get("event") or payload.get("type") or payload.get("status")
    charge_id = payload.get("id") or payload.get("charge_id") or payload.get("payment_id")
    amount = float(payload.get("amount") or payload.get("amount_aed") or 0)

    is_success = event_type in (
        "charge.succeeded", "subscription.succeeded",
        "paid", "succeeded", "success", "PAID"
    ) or payload.get("status") in ("paid", "succeeded", "PAID", "success")

    if not is_success:
        logger.info(f"Non-success webhook ignored: event_type={event_type}")
        return {"received": True}

    # Find customer email
    customer_email = (
        payload.get("customer_email")
        or payload.get("email")
        or (payload.get("customer") or {}).get("email")
        or (payload.get("payer") or {}).get("email")
        or payload.get("billing_email")
    )

    logger.info(f"Payment success: charge_id={charge_id}, email={customer_email}, amount={amount}")

    now = datetime.now(timezone.utc)

    # Find user by email
    user = None
    if customer_email:
        user_result = await db.execute(
            select(User).where(User.email == customer_email.lower().strip())
        )
        user = user_result.scalar_one_or_none()

    if not user:
        logger.warning(f"No user found for email={customer_email}")
        logger.warning(f"Full payload: {payload}")
        return {"received": True, "warning": "user not found"}

    # Find or create subscription
    sub_result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    sub = sub_result.scalars().first()

    if sub:
        # Update existing
        sub.status = "active"
        sub.cancelled_at = None
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=30)
    else:
        # Create new
        sub = Subscription(
            user_id=user.id,
            status="active",
            plan_price_aed=amount or 20.0,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        db.add(sub)

    # Commit subscription first
    await db.commit()
    await db.refresh(sub)

    # Record payment
    if charge_id:
        existing = await db.execute(
            select(Payment).where(Payment.mamopay_charge_id == charge_id)
        )
        if not existing.scalars().first():
            payment = Payment(
                subscription_id=sub.id,
                user_id=user.id,
                amount_aed=amount or 20.0,
                status="succeeded",
                mamopay_charge_id=charge_id,
            )
            db.add(payment)
            await db.commit()

    logger.info(f"Subscription activated for user_id={user.id}, email={customer_email}")
    return {"received": True, "subscription_activated": True, "user_email": customer_email}
