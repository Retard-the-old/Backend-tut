from __future__ import annotations
from pydantic import BaseModel
from datetime import datetime

class PayoutResponse(BaseModel):
    id: str
    earner_id: str
    amount_aed: float
    status: str
    mamopay_transfer_id: str | None
    failure_reason: str | None
    paid_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}

class CommissionResponse(BaseModel):
    id: str
    earner_id: str
    source_user_id: str
    level: int
    amount_aed: float
    status: str
    payout_id: str | None
    created_at: datetime
    model_config = {"from_attributes": True}
