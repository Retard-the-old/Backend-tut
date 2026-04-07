from fastapi import APIRouter, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.db.database import get_db
from app.models.subscription import Subscription, Payment
from app.models.user import User
from fastapi import Depends
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _extract_email(payload: dict) -> str:
    """Extract customer email from a MamoPay webhook payload, trying all known field locations."""
    return (
        payload.get("customer_email")
        or payload.get("email")
        or (payload.get("customer") or {}).get("email")
        or (payload.get("customer_details") or {}).get("email")
        or (payload.get("payer") or {}).get("email")
        or payload.get("billing_email")
        or ""
    ).lower().strip()


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

    SUCCESS_STATUSES = {"charge.succeeded", "subscription.succeeded", "paid", "succeeded",
                        "success", "PAID", "captured", "SUCCESS"}
    is_success = (
        event_type in SUCCESS_STATUSES
        or payload.get("status") in SUCCESS_STATUSES
    )

    if not is_success:
        logger.info(f"Non-success webhook ignored: event_type={event_type}")
        return {"received": True}

    # Idempotency guard — if we've already processed this charge_id, skip entirely
    if charge_id:
        existing_payment = await db.execute(
            select(Payment).where(Payment.mamopay_charge_id == charge_id)
        )
        if existing_payment.scalars().first():
            logger.info(f"Webhook charge_id={charge_id} already processed — skipping")
            return {"received": True, "skipped": "already_processed"}

    customer_email = _extract_email(payload)
    logger.info(f"Payment success: charge_id={charge_id}, email={customer_email}, amount={amount}")

    now = datetime.now(timezone.utc)

    # Find user by email
    user = None
    if customer_email:
        user_result = await db.execute(
            select(User).where(User.email == customer_email)
        )
        user = user_result.scalar_one_or_none()

    if not user:
        logger.warning(f"No user found for email={customer_email}")
        logger.warning(f"Full payload: {payload}")
        return {"received": True, "warning": "user not found"}

    # Lock the subscription row for this user to prevent race conditions
    # from simultaneous webhooks (SELECT FOR UPDATE)
    sub_result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .with_for_update()
    )
    sub = sub_result.scalars().first()

    if sub and sub.status == "active":
        # Already active — just record the payment if needed and return
        logger.info(f"User {user.id} already active, recording payment only")
        if charge_id:
            payment = Payment(
                subscription_id=sub.id,
                user_id=user.id,
                amount_aed=amount or 95.0,
                status="succeeded",
                mamopay_charge_id=charge_id,
            )
            db.add(payment)
            await db.commit()
        return {"received": True, "subscription_activated": False, "note": "already_active"}

    if sub:
        sub.status = "active"
        sub.cancelled_at = None
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=30)
    else:
        sub = Subscription(
            user_id=user.id,
            status="active",
            plan_price_aed=amount or 95.0,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        db.add(sub)

    await db.flush()

    # Record payment
    if charge_id:
        payment = Payment(
            subscription_id=sub.id,
            user_id=user.id,
            amount_aed=amount or 95.0,
            status="succeeded",
            mamopay_charge_id=charge_id,
        )
        db.add(payment)

    await db.commit()
    await db.refresh(sub)

    logger.info(f"Subscription activated for user_id={user.id}, email={customer_email}")
    return {"received": True, "subscription_activated": True, "user_email": customer_email}
