from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.database import get_db
from app.core.dependencies import require_admin
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

@router.get("/users", response_model=list[UserResponse])
async def list_users(skip: int = 0, limit: int = 50, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).order_by(User.created_at.desc()).offset(skip).limit(limit))
    return [UserResponse.model_validate(u) for u in result.scalars().all()]

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
