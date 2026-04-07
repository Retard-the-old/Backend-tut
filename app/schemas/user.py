from __future__ import annotations
from pydantic import BaseModel
from datetime import datetime

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    phone: str | None
    role: str
    referral_code: str
    referred_by_id: str | None
    is_active: bool
    payout_iban: str | None
    created_at: datetime
    model_config = {"from_attributes": True}

class UserUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    payout_iban: str | None = None
    payout_name: str | None = None

class ReferralStats(BaseModel):
    referral_code: str
    total_l1_referrals: int
    total_l2_referrals: int
    total_earned_aed: float
    pending_aed: float
    paid_aed: float
