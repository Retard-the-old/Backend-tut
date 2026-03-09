from __future__ import annotations
import hashlib, hmac, logging
from fastapi import APIRouter, Request, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.core.config import settings
from app.services.subscription_service import activate_subscription
from app.services.commission_service import create_commissions_for_payment
from app.models.subscription import Payment
from sqlalchemy import select

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

def verify_mamopay_signature(payload: bytes, signature: str) -> bool:
    if not settings.MAMOPAY_WEBHOOK_SECRET:
        return True  # skip in dev
    expected = hmac.new(settings.MAMOPAY_WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

@router.post("/mamopay")
async def mamopay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()
    sig = request.headers.get("x-mamopay-signature", "")
    if not verify_mamopay_signature(body, sig):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")

    data = await request.json()
    event_type = data.get("type", "")
    payload = data.get("data", {})
    logger.info("MamoPay webhook: %s", event_type)

    if event_type in ("payment.captured", "charge.succeeded"):
        external_id = payload.get("external_id", "")
        charge_id = payload.get("id", "")
        if external_id:
            await activate_subscription(external_id, charge_id, db)
            # Create commissions for the payment
            pay_result = await db.execute(select(Payment).where(Payment.mamopay_charge_id == charge_id))
            payment = pay_result.scalar_one_or_none()
            if payment:
                await create_commissions_for_payment(payment, db)

    return {"status": "ok"}
