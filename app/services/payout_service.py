from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.user import User
from app.models.commission import Commission, Payout
from app.clients.mamopay import mamopay_client
from app.core.config import settings
from app.services.email_service import send_payout_confirmation
import logging
logger = logging.getLogger(__name__)

async def process_weekly_payouts(db: AsyncSession) -> list[dict]:
    results = []
    earner_totals = await db.execute(
        select(Commission.earner_id, func.sum(Commission.amount_aed).label("total"))
        .where(Commission.status == "pending").group_by(Commission.earner_id)
    )
    for earner_id, total_aed in earner_totals.all():
        total_aed = float(total_aed)
        if total_aed < settings.MINIMUM_PAYOUT_AED:
            results.append({"earner_id": earner_id, "status": "below_minimum", "amount": total_aed})
            continue

        user = (await db.execute(select(User).where(User.id == earner_id))).scalar_one_or_none()
        if user is None or not user.payout_iban or not user.payout_name:
            results.append({"earner_id": earner_id, "status": "missing_payout_info", "amount": total_aed})
            continue

        payout = Payout(earner_id=earner_id, amount_aed=total_aed, status="processing")
        db.add(payout)
        await db.flush()

        pending_comms = (await db.execute(
            select(Commission).where(Commission.earner_id == earner_id, Commission.status == "pending")
        )).scalars().all()
        for comm in pending_comms:
            comm.status = "approved"
            comm.payout_id = payout.id

        try:
            transfer = await mamopay_client.create_transfer(
                amount=total_aed, iban=user.payout_iban,
                recipient_name=user.payout_name, external_id=payout.id,
            )
            # MamoPay returns `identifier` (string) as the unique reference;
            # `id` is a numeric DB id — stringify it as a last resort.
            raw_id = transfer.get("id")
            transfer_id = (
                transfer.get("identifier")
                or (str(raw_id) if raw_id is not None else "")
                or transfer.get("reference", "")
                or transfer.get("transaction_id", "")
            )
            if not transfer_id:
                raise ValueError(
                    f"MamoPay returned no transfer ID. Response keys: {list(transfer.keys())}"
                )
            payout.mamopay_transfer_id = transfer_id
            payout.status = "completed"
            payout.paid_at = datetime.now(timezone.utc)
            for comm in pending_comms:
                comm.status = "paid"
            await send_payout_confirmation(user.email, user.full_name, total_aed, user.payout_iban, len(pending_comms))
            results.append({"earner_id": earner_id, "status": "completed", "amount": total_aed})
            logger.info("Payout %.2f AED to %s completed", total_aed, user.email)
        except Exception as e:
            payout.status = "failed"
            payout.failure_reason = str(e)[:500]
            for comm in pending_comms:
                comm.status = "pending"
                comm.payout_id = None
            results.append({"earner_id": earner_id, "status": "failed", "error": str(e)[:200]})
            logger.error("Payout failed for %s: %s", user.email, e)

    await db.flush()
    return results
