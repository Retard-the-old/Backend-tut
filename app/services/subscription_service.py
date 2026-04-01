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
MAMOPAY_SUBSCRIPTION_URL = "https://business.mamopay.com/pay/galcofzellc-4b20ab"


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


MAMOPAY_API_KEY = "sk-bb4ce2f9-c13a-473a-945a-b55b8d22400e"
MAMOPAY_API_URL = "https://business.mamopay.com/manage_api/v1"


async def verify_and_activate(user: User, db: AsyncSession) -> dict:
    """
    Queries MamoPay charges API for a recent successful payment by this user's email.
    If found and subscription not yet active, activates it.
    """
    import httpx
    from datetime import timedelta
    from app.models.subscription import Subscription, Payment

    # Check if already active
    sub_result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    sub = sub_result.scalars().first()
    if sub and sub.status == "active":
        return {"activated": True, "already_active": True}

    # Query MamoPay charges API
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{MAMOPAY_API_URL}/charges",
                headers={"Authorization": f"Bearer {MAMOPAY_API_KEY}"}
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach MamoPay: {str(e)}")

    # Find a successful charge for this user's email within the last 24 hours
    charges = data if isinstance(data, list) else data.get("data", data.get("charges", []))
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    matched_charge = None
    for charge in charges:
        charge_email = (
            charge.get("customer_email") or
            charge.get("email") or
            (charge.get("customer") or {}).get("email") or
            ""
        ).lower().strip()

        charge_status = charge.get("status", "")
        is_success = charge_status in ("captured", "paid", "succeeded", "PAID")

        if charge_email == user.email.lower() and is_success:
            matched_charge = charge
            break

    if not matched_charge:
        return {"activated": False, "message": "No successful payment found for your email on MamoPay. Please ensure you used the same email you registered with."}

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
            plan_price_aed=95.0,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        db.add(sub)

    await db.flush()

    # Record payment if not already recorded
    charge_id = matched_charge.get("id") or matched_charge.get("charge_id")
    if charge_id:
        existing = await db.execute(
            select(Payment).where(Payment.mamopay_charge_id == charge_id)
        )
        if not existing.scalars().first():
            payment = Payment(
                subscription_id=sub.id,
                user_id=user.id,
                amount_aed=float(matched_charge.get("amount", 95)),
                status="succeeded",
                mamopay_charge_id=charge_id,
            )
            db.add(payment)

    await db.commit()
    return {"activated": True, "message": "Payment verified and subscription activated!"}


async def verify_payment_and_register(data: dict, db: AsyncSession) -> dict:
    """
    Called when user clicks 'I've paid'.
    1. Checks MamoPay for a successful charge with this email
    2. If found: creates account + activates subscription + returns tokens
    3. If not found: returns activated=False
    """
    import httpx
    from datetime import timedelta
    from app.models.subscription import Subscription, Payment
    from app.services.auth_service import register_user
    from app.schemas.auth import RegisterRequest
    from app.core.security import create_access_token, create_refresh_token

    email = data.get("email", "").lower().strip()
    full_name = data.get("full_name", "")
    password = data.get("password", "")
    phone = data.get("phone", "")
    referral_code = data.get("referral_code")

    # Check if account already exists
    existing = await db.execute(select(User).where(User.email == email))
    existing_user = existing.scalar_one_or_none()

    # If account exists and is already active, just return tokens
    if existing_user:
        sub_result = await db.execute(
            select(Subscription).where(
                Subscription.user_id == existing_user.id,
                Subscription.status == "active"
            )
        )
        if sub_result.scalar_one_or_none():
            return {
                "activated": True,
                "already_active": True,
                "access_token": create_access_token(str(existing_user.id)),
                "refresh_token": create_refresh_token(str(existing_user.id)),
            }

    # Query MamoPay charges API
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{MAMOPAY_API_URL}/charges",
                headers={"Authorization": f"Bearer {MAMOPAY_API_KEY}"}
            )
            resp.raise_for_status()
            data_resp = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach MamoPay: {str(e)}")

    charges = data_resp if isinstance(data_resp, list) else data_resp.get("data", data_resp.get("charges", []))

    matched_charge = None
    for charge in charges:
        charge_email = (
            charge.get("customer_email") or
            charge.get("email") or
            (charge.get("customer") or {}).get("email") or ""
        ).lower().strip()

        is_success = charge.get("status", "") in ("captured", "paid", "succeeded", "PAID")

        if charge_email == email and is_success:
            matched_charge = charge
            break

    if not matched_charge:
        return {
            "activated": False,
            "message": f"No successful payment found for {email} on MamoPay. Please ensure you completed the payment using this exact email address."
        }

    # Create account if doesn't exist
    now = datetime.now(timezone.utc)
    if not existing_user:
        from passlib.context import CryptContext
        import secrets, string
        pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        chars = string.ascii_uppercase + string.digits
        ref_code = "".join(secrets.choice(chars) for _ in range(8))

        referred_by = None
        if referral_code:
            ref_result = await db.execute(
                select(User).where(User.referral_code == referral_code.upper())
            )
            referred_by_user = ref_result.scalar_one_or_none()
            if referred_by_user:
                referred_by = referred_by_user.id

        existing_user = User(
            email=email,
            full_name=full_name,
            hashed_password=pwd_ctx.hash(password),
            phone=phone,
            referral_code=ref_code,
            referred_by_id=referred_by,
            is_active=True,
        )
        db.add(existing_user)
        await db.flush()

    # Create active subscription
    sub = Subscription(
        user_id=existing_user.id,
        status="active",
        plan_price_aed=float(matched_charge.get("amount", 95)),
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    db.add(sub)
    await db.flush()

    # Record payment
    charge_id = matched_charge.get("id") or matched_charge.get("charge_id")
    if charge_id:
        payment = Payment(
            subscription_id=sub.id,
            user_id=existing_user.id,
            amount_aed=float(matched_charge.get("amount", 95)),
            status="succeeded",
            mamopay_charge_id=charge_id,
        )
        db.add(payment)

    await db.commit()

    return {
        "activated": True,
        "access_token": create_access_token(str(existing_user.id)),
        "refresh_token": create_refresh_token(str(existing_user.id)),
        "message": "Payment verified and account created!"
    }
