from __future__ import annotations
from pydantic import BaseModel
from datetime import datetime

class SubscriptionResponse(BaseModel):
    id: str
    status: str
    plan_price_aed: float
    mamopay_payment_link: str | None
    current_period_start: datetime | None
    current_period_end: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}

class CreateSubscriptionResponse(BaseModel):
    subscription_id: str
    payment_link: str
