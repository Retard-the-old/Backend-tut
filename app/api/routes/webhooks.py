from fastapi import APIRouter, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import get_db
from app.models.subscription import Subscription, Payment
from app.models.commission import Commission
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
    When a payment succeeds, activates the user's subscription.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    logger.info(f"MamoPay webhook received: {payload}")

    # MamoPay sends different event types — handle charge.succeeded
    event_type = payload.get("event") or payload.get("type") or payload.get("status")
    charge_id = payload.get("id") or payload.get("charge_id") or payload.get("payment_id")
    
    # Check for successful payment - MamoPay event types
    is_success = event_type in (
        "charge.succeeded",
        "subscription.succeeded",
        "paid", "succeeded", "success", "PAID"
    ) or payload.get("status") in ("paid", "succeeded", "PAID", "success")

    if not is_success:
        logger.info(f"Non-success webhook ignored: event_type={event_type}")
        return {"received": True}

    # Get subscription link ID from payload to find the user
    link_id = (
        payload.get("payment_link_id")
        or payload.get("link_id")
        or payload.get("payment_link")
        or payload.get("metadata", {}).get("subscription_id")
        or payload.get("reference")
    )

    amount = float(payload.get("amount") or payload.get("amount_aed") or 0)

    logger.info(f"Payment success: charge_id={charge_id}, link_id={link_id}, amount={amount}")

    # Find the subscription by mamopay_payment_link or mamopay_subscription_id
    sub = None
    if link_id:
        result = await db.execute(
            select(Subscription).where(
                (Subscription.mamopay_payment_link.contains(link_id)) |
                (Subscription.mamopay_subscription_id == link_id)
            )
        )
        sub = result.scalars().first()

    # If not found by link, try to find by charge_id in payments
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

    if not sub:
        logger.warning(f"No subscription found for webhook: link_id={link_id}, charge_id={charge_id}")
        # Still return 200 so MamoPay doesn't retry endlessly
        return {"received": True, "warning": "subscription not found"}

    # Activate the subscription
    now = datetime.now(timezone.utc)
    sub.status = "active"
    sub.cancelled_at = None
    sub.current_period_start = now
    sub.current_period_end = now + timedelta(days=30)

    # Record the payment
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

    logger.info(f"Subscription activated for user_id={sub.user_id}")
    return {"received": True, "subscription_activated": True}
