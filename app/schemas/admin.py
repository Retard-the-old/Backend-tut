from pydantic import BaseModel

class DashboardStats(BaseModel):
    total_users: int
    active_subscribers: int
    total_revenue_aed: float
    pending_commissions_aed: float
    total_payouts_aed: float
    total_courses: int

class UserRoleUpdate(BaseModel):
    role: str
