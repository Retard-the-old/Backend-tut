"""
app/services/mamopay_sync.py

Background job that runs every hour and syncs MamoPay payments with Tutorii subscriptions.
Ensures no user who paid gets stuck as inactive due to webhook failures.
"""
import asyncio
import logging
import httpx
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import AsyncSessionLocal
from app.models.user import User
from app.models.subscription import Subscription, Payment
from app.core.config import settings

logger = logging.getLogger(__name__)

SYNC_INTERVAL_SECONDS = 3600  # Run every hour


def _extract_email(charge: dict) -> str:
    """Extract customer email from a MamoPay charge object, trying all known field locations."""
    return (
        charge.get("customer_email")
        or charge.get("email")
        or (charge.get("customer") or {}).get("email")
        or (charge.get("customer_details") or {}).get("email")
        or (charge.get("payer") or {}).get("email")
        or ""
    ).lower().strip()


async def sync_mamopay_payments():
    """
    Fetches all recent captured payments from MamoPay.
    For each captured payment, finds the matching Tutorii user by email
    and activates their subscription if not already active.
    """
    logger.info("MamoPay sync job starting...")

    try:
        all_charges = []
        page = 1
        async with httpx.AsyncClient(timeout=15) as client:
            while True:
                resp = await client.get(
                    f"{settings.MAMOPAY_BASE_URL}/charges",
                    headers={"Authorization": f"Bearer {settings.MAMOPAY_API_KEY}"},
                    params={"page": page, "per_page": 50}
                )
                resp.raise_for_status()
                data = resp.json()
                charges = data.get("data", [])
                all_charges.extend(charges)

                meta = data.get("pagination_meta", {})
                if page >= meta.get("total_pages", 1):
                    break
                page += 1

        # Filter to only captured payments from last 48 hours
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        recent_captured = []
        for charge in all_charges:
            if charge.get("status") != "captured":
                continue
            try:
                date_str = charge.get("created_date", "")
                parts = date_str.split("-")
                if len(parts) >= 6:
                    charge_dt = datetime(
                        int(parts[0]), int(parts[1]), int(parts[2]),
                        int(parts[3]), int(parts[4]), int(parts[5]),
                        tzinfo=timezone.utc
                    )
                    if charge_dt >= cutoff:
                        recent_captured.append(charge)
            except Exception:
                recent_captured.append(charge)  # Include if can't parse date

        logger.info(f"MamoPay sync: found {len(recent_captured)} recent captured payments")

        if not recent_captured:
            return

        async with AsyncSessionLocal() as db:
            activated_count = 0
            for charge in recent_captured:
                try:
                    activated = await process_charge(charge, db)
                    if activated:
                        activated_count += 1
                except Exception as e:
                    logger.error(f"Error processing charge {charge.get('id')}: {e}")

            if activated_count > 0:
                logger.info(f"MamoPay sync: activated {activated_count} subscriptions")
            else:
                logger.info("MamoPay sync: all paid users already active")

    except Exception as e:
        logger.error(f"MamoPay sync job failed: {e}")


async def process_charge(charge: dict, db: AsyncSession) -> bool:
    """
    Process a single captured charge.
    Returns True if a subscription was activated, False otherwise.
    """
    charge_id = charge.get("id")
    email = _extract_email(charge)
    amount = float(charge.get("amount", 95))

    if not email:
        return False

    # Check if this payment was already processed
    existing_payment = await db.execute(
        select(Payment).where(Payment.mamopay_charge_id == charge_id)
    )
    if existing_payment.scalars().first():
        return False

    # Find user by email
    user_result = await db.execute(
        select(User).where(User.email == email)
    )
    user = user_result.scalar_one_or_none()

    if not user:
        logger.warning(f"MamoPay sync: payment {charge_id} for {email} — no Tutorii account found")
        return False

    # Check if already active
    sub_result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    sub = sub_result.scalars().first()

    if sub and sub.status == "active":
        # Record payment if not already done
        payment = Payment(
            subscription_id=sub.id,
            user_id=user.id,
            amount_aed=amount,
            status="succeeded",
            mamopay_charge_id=charge_id,
        )
        db.add(payment)
        await db.commit()
        return False

    # Activate subscription
    now = datetime.now(timezone.utc)
    if sub:
        sub.status = "active"
        sub.cancelled_at = None
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=30)
    else:
        sub = Subscription(
            user_id=user.id,
            status="active",
            plan_price_aed=amount,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        db.add(sub)
        await db.flush()

    payment = Payment(
        subscription_id=sub.id,
        user_id=user.id,
        amount_aed=amount,
        status="succeeded",
        mamopay_charge_id=charge_id,
    )
    db.add(payment)
    await db.commit()

    logger.info(f"MamoPay sync: activated subscription for {email} (charge {charge_id})")
    return True


async def start_sync_scheduler():
    """Runs the MamoPay sync job on startup and then every hour."""
    logger.info("MamoPay sync scheduler started")
    while True:
        try:
            await sync_mamopay_payments()
        except Exception as e:
            logger.error(f"Sync scheduler error: {e}")
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)
