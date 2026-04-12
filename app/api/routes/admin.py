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
from app.clients.mamopay import mamopay_client
from datetime import datetime, timezone, timedelta
import logging
import secrets
import string

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


def _audit(admin: User, action: str, detail: str):
    """Structured audit log line — appears in Railway logs and any log aggregator."""
    logger.warning(
        "ADMIN_AUDIT | admin=%s (%s) | action=%s | %s",
        admin.email, admin.id, action, detail
    )


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

    subs_result = await db.execute(select(Subscription).where(Subscription.user_id.in_(user_ids)))
    subs_map = {s.user_id: s for s in subs_result.scalars().all()}

    # Referral counts
    ref_counts_result = await db.execute(
        select(User.referred_by_id, func.count(User.id).label("cnt"))
        .where(User.referred_by_id.in_(user_ids))
        .group_by(User.referred_by_id)
    )
    ref_counts_map = {row.referred_by_id: row.cnt for row in ref_counts_result.all()}

    # Total earned (all paid commissions)
    total_earned_result = await db.execute(
        select(Commission.earner_id, func.sum(Commission.amount_aed).label("total"))
        .where(Commission.earner_id.in_(user_ids), Commission.status.in_(["paid", "approved"]))
        .group_by(Commission.earner_id)
    )
    total_earned_map = {row.earner_id: float(row.total) for row in total_earned_result.all()}

    # Pending payout
    pending_result = await db.execute(
        select(Commission.earner_id, func.sum(Commission.amount_aed).label("pending"))
        .where(Commission.earner_id.in_(user_ids), Commission.status == "pending")
        .group_by(Commission.earner_id)
    )
    pending_map = {row.earner_id: float(row.pending) for row in pending_result.all()}

    # Referred-by name lookup
    referred_by_ids = [u.referred_by_id for u in users if u.referred_by_id]
    referred_by_map = {}
    if referred_by_ids:
        rb_result = await db.execute(select(User).where(User.id.in_(referred_by_ids)))
        for rb in rb_result.scalars().all():
            referred_by_map[rb.id] = rb.full_name or rb.email

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
            "referral_count": ref_counts_map.get(u.id, 0),
            "total_earned": total_earned_map.get(u.id, 0.0),
            "pending_payout": pending_map.get(u.id, 0.0),
            "referred_by_name": referred_by_map.get(u.referred_by_id) if u.referred_by_id else None,
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
    old_role = user.role
    user.role = data.role
    await db.flush()
    _audit(admin, "ROLE_CHANGE", f"target={user.email} ({user_id}) | {old_role} -> {data.role}")
    return UserResponse.model_validate(user)


@router.post("/payouts/trigger")
async def trigger_payouts(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    results = await process_weekly_payouts(db)
    _audit(admin, "TRIGGER_PAYOUTS", f"payouts_processed={len(results)}")
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
            "mamopay_transfer_id": p.mamopay_transfer_id or "",
            "failure_reason": p.failure_reason,
            "date": p.paid_at.strftime("%b %d, %Y") if p.paid_at else p.created_at.strftime("%b %d, %Y"),
            "created_at": p.created_at.isoformat(),
        }
        for p, u in rows
    ]


@router.get("/payouts/{payout_id}/verify")
async def verify_payout(payout_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Payout).where(Payout.id == payout_id))
    payout = result.scalar_one_or_none()
    if payout is None:
        raise HTTPException(status_code=404, detail="Payout not found")
    if not payout.mamopay_transfer_id:
        raise HTTPException(status_code=400, detail="No MamoPay transfer ID on record for this payout")
    try:
        data = await mamopay_client.get_transfer(payout.mamopay_transfer_id)
        mamopay_status = data.get("status", "unknown")
        ms = mamopay_status.lower()
        # Always sync local status to match MamoPay's real state
        if ms in ("completed", "processed", "paid"):
            if payout.status != "completed":
                payout.status = "completed"
                payout.paid_at = payout.paid_at or datetime.now(timezone.utc)
                comms = (await db.execute(
                    select(Commission).where(Commission.payout_id == payout_id)
                )).scalars().all()
                for comm in comms:
                    comm.status = "paid"
                await db.flush()
        elif ms in ("processing", "pending", "in_progress"):
            if payout.status != "processing":
                payout.status = "processing"
                # Revert commissions back to approved (in-flight, not yet confirmed)
                comms = (await db.execute(
                    select(Commission).where(Commission.payout_id == payout_id)
                )).scalars().all()
                for comm in comms:
                    if comm.status == "paid":
                        comm.status = "approved"
                await db.flush()
        elif ms in ("failed", "rejected", "cancelled", "expired"):
            if payout.status != "failed":
                payout.status = "failed"
                payout.failure_reason = f"MamoPay status: {mamopay_status}"
                await db.flush()
        await db.commit()
        await db.refresh(payout)
        _audit(admin, "VERIFY_PAYOUT", f"payout={payout_id} mamopay_id={payout.mamopay_transfer_id} status={mamopay_status}")
        return {
            "payout_id": payout_id,
            "mamopay_id": payout.mamopay_transfer_id,
            "mamopay_status": mamopay_status,
            "amount": data.get("amount_formatted"),
            "recipient": data.get("recipient"),
            "method": data.get("method"),
            "reason": data.get("reason"),
            "created_at": data.get("created_at"),
            "local_status": payout.status,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"MamoPay error: {str(e)[:200]}")


@router.post("/payouts/{payout_id}/reset")
async def reset_payout(payout_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Reset a failed/stuck payout, returning commissions to pending so the next trigger re-processes them."""
    result = await db.execute(select(Payout).where(Payout.id == payout_id))
    payout = result.scalar_one_or_none()
    if payout is None:
        raise HTTPException(status_code=404, detail="Payout not found")
    if payout.status == "completed" and payout.mamopay_transfer_id:
        raise HTTPException(status_code=400, detail="Cannot reset a verified completed payout")

    # Return commissions to pending so they'll be picked up by the next trigger
    comms = (await db.execute(
        select(Commission).where(Commission.payout_id == payout_id)
    )).scalars().all()
    for comm in comms:
        comm.status = "pending"
        comm.payout_id = None

    await db.delete(payout)
    await db.flush()
    _audit(admin, "RESET_PAYOUT", f"payout={payout_id} commissions_reset={len(comms)}")
    return {"reset": True, "payout_id": payout_id, "commissions_reset": len(comms)}


@router.post("/users/{user_id}/subscription/activate")
async def admin_activate_subscription(user_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
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
    _audit(admin, "ACTIVATE_SUBSCRIPTION", f"target={user.email} ({user_id})")
    return {"success": True, "user_id": user_id, "status": "active"}


@router.post("/users/{user_id}/subscription/cancel")
async def admin_cancel_subscription(user_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    sub_result = await db.execute(select(Subscription).where(Subscription.user_id == user_id, Subscription.status == "active"))
    sub = sub_result.scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=404, detail="No active subscription found")
    sub.status = "cancelled"
    sub.cancelled_at = datetime.now(timezone.utc)
    await db.flush()
    _audit(admin, "CANCEL_SUBSCRIPTION", f"target={user.email} ({user_id})")
    return {"success": True, "user_id": user_id, "status": "cancelled"}


@router.post("/users/create")
async def create_user(data: dict, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    pwd_ctx_import = __import__("passlib.context", fromlist=["CryptContext"])
    pwd_context = pwd_ctx_import.CryptContext(schemes=["bcrypt"], deprecated="auto")

    email = data.get("email", "").lower().strip()
    full_name = data.get("full_name", "").strip()
    password = data.get("password", "").strip()
    role = data.get("role", "user")

    if not email or not full_name or not password:
        raise HTTPException(status_code=400, detail="email, full_name and password are required")
    if role not in ("user", "admin", "support"):
        raise HTTPException(status_code=400, detail="Invalid role")

    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    # Unique referral code
    chars = string.ascii_uppercase + string.digits
    ref_code = None
    for _ in range(5):
        candidate = "".join(secrets.choice(chars) for _ in range(8))
        clash = await db.execute(select(User).where(User.referral_code == candidate))
        if not clash.scalar_one_or_none():
            ref_code = candidate
            break
    if not ref_code:
        ref_code = "".join(secrets.choice(chars) for _ in range(12))

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
    _audit(admin, "CREATE_USER", f"new_user={email} role={role}")
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "referral_code": user.referral_code, "role": user.role}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "admin":
        raise HTTPException(status_code=403, detail="Cannot delete admin users")

    target_email = user.email  # capture before deletion

    comms = (await db.execute(select(Commission).where(Commission.earner_id == user_id))).scalars().all()
    for c in comms:
        await db.delete(c)

    payouts = (await db.execute(select(Payout).where(Payout.earner_id == user_id))).scalars().all()
    for p in payouts:
        await db.delete(p)

    payments = (await db.execute(select(Payment).where(Payment.user_id == user_id))).scalars().all()
    for p in payments:
        await db.delete(p)

    subs = (await db.execute(select(Subscription).where(Subscription.user_id == user_id))).scalars().all()
    for s in subs:
        await db.delete(s)

    await db.delete(user)
    await db.commit()
    _audit(admin, "DELETE_USER", f"deleted={target_email} ({user_id})")
    return {"deleted": True, "user_id": user_id}
