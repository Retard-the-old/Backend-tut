from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.database import get_db
from app.core.dependencies import require_admin
from app.core.config import settings
from app.models.user import User
from app.models.subscription import Subscription, Payment
from app.models.commission import Commission, Payout
from app.models.course import Course
from app.schemas.admin import DashboardStats, UserRoleUpdate
from app.schemas.user import UserResponse
from app.schemas.payout import PayoutResponse
from app.services.payout_service import process_weekly_payouts

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/dashboard", response_model=DashboardStats)
async def dashboard(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    active_subs = (await db.execute(select(func.count()).where(Subscription.status == "active"))).scalar() or 0
    revenue = float((await db.execute(select(func.coalesce(func.sum(Payment.amount_aed), 0.0)).where(Payment.status == "succeeded"))).scalar())
    pending_comms = float((await db.execute(select(func.coalesce(func.sum(Commission.amount_aed), 0.0)).where(Commission.status == "pending"))).scalar())
    total_payouts = float((await db.execute(select(func.coalesce(func.sum(Payout.amount_aed), 0.0)).where(Payout.status == "completed"))).scalar())
    courses = (await db.execute(select(func.count(Course.id)))).scalar() or 0
    return DashboardStats(
        total_users=total_users, active_subscribers=active_subs,
        total_revenue_aed=revenue, pending_commissions_aed=pending_comms,
        total_payouts_aed=total_payouts, total_courses=courses,
    )

@router.get("/users")
async def list_users(skip: int = 0, limit: int = 200, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).order_by(User.created_at.desc()).offset(skip).limit(limit))
    users = result.scalars().all()
    user_ids = [u.id for u in users]

    # Get subscriptions for all users in one query
    subs_result = await db.execute(select(Subscription).where(Subscription.user_id.in_(user_ids)))
    subs_map = {s.user_id: s for s in subs_result.scalars().all()}

    return [
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role,
            "referral_code": u.referral_code,
            "referred_by_id": u.referred_by_id,
            "is_active": u.is_active,
            "payout_iban": u.payout_iban,
            "payout_name": getattr(u, "payout_name", None),
            "created_at": u.created_at.isoformat(),
            "subscription_status": subs_map[u.id].status if u.id in subs_map else "inactive",
            "referral_count": 0,
            "total_earned": 0,
            "pending_payout": 0,
            "referred_by_name": None,
        }
        for u in users
    ]

@router.patch("/users/{user_id}/role", response_model=UserResponse)
async def update_role(user_id: str, data: UserRoleUpdate, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    if data.role not in ("user", "admin", "support"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.role = data.role
    await db.flush()
    return UserResponse.model_validate(user)

@router.post("/payouts/trigger")
async def trigger_payouts(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    results = await process_weekly_payouts(db)
    return {"payouts_processed": len(results), "details": results}

@router.get("/payouts", response_model=list[dict])
async def list_payouts(limit: int = 200, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Payout, User).join(User, Payout.earner_id == User.id)
        .order_by(Payout.created_at.desc()).limit(limit)
    )
    rows = result.all()
    return [
        {
            "id": str(p.id),
            "user": u.full_name or u.email,
            "email": u.email,
            "iban": u.payout_iban or "",
            "iban_name": u.payout_name or "",
            "amount": float(p.amount_aed),
            "status": p.status,
            "failure_reason": p.failure_reason,
            "date": p.paid_at.strftime("%b %d, %Y") if p.paid_at else p.created_at.strftime("%b %d, %Y"),
            "created_at": p.created_at.isoformat(),
        }
        for p, u in rows
    ]

@router.post("/users/{user_id}/subscription/activate")
async def admin_activate_subscription(user_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from app.models.subscription import Subscription
    from datetime import datetime, timezone, timedelta
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    now = datetime.now(timezone.utc)
    sub_result = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    sub = sub_result.scalars().first()
    if sub:
        sub.status = "active"
        sub.cancelled_at = None
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=30)
    else:
        sub = Subscription(
            user_id=user_id,
            status="active",
            plan_price_aed=settings.SUBSCRIPTION_PRICE_AED,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        db.add(sub)
    await db.flush()
    return {"success": True, "user_id": user_id, "status": "active"}

@router.post("/users/{user_id}/subscription/cancel")
async def admin_cancel_subscription(user_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from app.models.subscription import Subscription
    from datetime import datetime, timezone
    sub_result = await db.execute(select(Subscription).where(Subscription.user_id == user_id, Subscription.status == "active"))
    sub = sub_result.scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=404, detail="No active subscription found")
    sub.status = "cancelled"
    sub.cancelled_at = datetime.now(timezone.utc)
    await db.flush()
    return {"success": True, "user_id": user_id, "status": "cancelled"}

@router.post("/users/create")
async def create_user(data: dict, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from app.models.user import User as UserModel
    from passlib.context import CryptContext
    import secrets, string
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    email = data.get("email", "").lower().strip()
    full_name = data.get("full_name", "").strip()
    password = data.get("password", "").strip()
    role = data.get("role", "user")

    if not email or not full_name or not password:
        raise HTTPException(status_code=400, detail="email, full_name and password are required")

    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    # Generate referral code
    chars = string.ascii_uppercase + string.digits
    ref_code = "".join(secrets.choice(chars) for _ in range(8))

    user = User(
        email=email,
        full_name=full_name,
        hashed_password=pwd_context.hash(password),
        role=role,
        referral_code=ref_code,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "referral_code": user.referral_code, "role": user.role}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from app.models.commission import Commission, Payout
    from app.models.subscription import Subscription, Payment

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "admin":
        raise HTTPException(status_code=403, detail="Cannot delete admin users")

    # Delete related records in order
    await db.execute(select(Commission).where(Commission.earner_id == user_id))
    comms = (await db.execute(select(Commission).where(Commission.earner_id == user_id))).scalars().all()
    for c in comms: await db.delete(c)

    payouts = (await db.execute(select(Payout).where(Payout.earner_id == user_id))).scalars().all()
    for p in payouts: await db.delete(p)

    payments = (await db.execute(select(Payment).where(Payment.user_id == user_id))).scalars().all()
    for p in payments: await db.delete(p)

    subs = (await db.execute(select(Subscription).where(Subscription.user_id == user_id))).scalars().all()
    for s in subs: await db.delete(s)

    await db.delete(user)
    await db.commit()
    return {"deleted": True, "user_id": user_id}
