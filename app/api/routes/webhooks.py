from fastapi import APIRouter, Request, HTTPException
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
    """
    Receives payment notifications from MamoPay.
    Identifies user by email, then activates their subscription.
    Works for both one-off payment links and shared subscription links.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

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

    # Find customer email from payload
    customer_email = (
        payload.get("customer_email")
        or payload.get("email")
        or (payload.get("customer") or {}).get("email")
        or (payload.get("payer") or {}).get("email")
        or payload.get("billing_email")
    )

    logger.info(f"Payment success: charge_id={charge_id}, email={customer_email}, amount={amount}")

    user = None
    sub = None

    # Step 1: Find user by email
    if customer_email:
        user_result = await db.execute(
            select(User).where(User.email == customer_email.lower().strip())
        )
        user = user_result.scalar_one_or_none()
        if user:
            sub_result = await db.execute(
                select(Subscription).where(Subscription.user_id == user.id)
            )
            sub = sub_result.scalars().first()

    # Step 2: Fallback by payment link ID
    if not sub:
        link_id = (
            payload.get("payment_link_id")
            or payload.get("link_id")
            or payload.get("payment_link")
            or payload.get("reference")
        )
        if link_id:
            result = await db.execute(
                select(Subscription).where(
                    (Subscription.mamopay_payment_link.contains(link_id)) |
                    (Subscription.mamopay_subscription_id == link_id)
                )
            )
            sub = result.scalars().first()

    # Step 3: Fallback by charge_id
    if not sub and charge_id:
        pay_result = await db.execute(
            select(Payment).where(Payment.mamopay_charge_id == charge_id)
        )
        existing_payment = pay_result.scalars().first()
        if existing_payment:
            sub_result = await db.execute(
                select(Subscription).where(Subscription.id == existing_payment.subscription_id)
            )
            sub = sub_result.scalars().first()

    # Step 4: Create subscription if user exists but has none
    if not sub and user:
        logger.info(f"Creating new subscription for user {user.email}")
        now = datetime.now(timezone.utc)
        sub = Subscription(
            user_id=user.id,
            status="active",
            plan_price_aed=amount or 95.0,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        db.add(sub)
        await db.flush()

    if not sub:
        logger.warning(f"Could not find or create subscription. email={customer_email}, charge_id={charge_id}")
        logger.warning(f"Full payload: {payload}")
        return {"received": True, "warning": "user not found — check email field in payload"}

    # Activate the subscription
    now = datetime.now(timezone.utc)
    sub.status = "active"
    sub.cancelled_at = None
    sub.current_period_start = now
    sub.current_period_end = now + timedelta(days=30)

    # Record payment to avoid double-processing
    if charge_id:
        existing = await db.execute(
            select(Payment).where(Payment.mamopay_charge_id == charge_id)
        )
        if not existing.scalars().first():
            payment = Payment(
                subscription_id=sub.id,
                user_id=sub.user_id,
                amount_aed=amount or sub.plan_price_aed,
                status="succeeded",
                mamopay_charge_id=charge_id,
            )
            db.add(payment)

    await db.commit()

    logger.info(f"Subscription activated for user_id={sub.user_id}, email={customer_email}")
    return {"received": True, "subscription_activated": True, "user_email": customer_email}
