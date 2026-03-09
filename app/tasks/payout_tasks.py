import asyncio
import logging
from celery_app import celery
from app.db.database import AsyncSessionLocal
from app.services.payout_service import process_weekly_payouts

logger = logging.getLogger(__name__)

@celery.task(name="app.tasks.payout_tasks.run_weekly_payouts", bind=True, max_retries=2)
def run_weekly_payouts(self):
    logger.info("Starting weekly payout processing")
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    async def _run():
        async with AsyncSessionLocal() as db:
            try:
                results = await process_weekly_payouts(db)
                await db.commit()
                logger.info("Weekly payouts complete: %d processed", len(results))
                return results
            except Exception:
                await db.rollback()
                raise

    try:
        return loop.run_until_complete(_run())
    except Exception as exc:
        logger.error("Weekly payouts failed: %s", exc)
        raise self.retry(exc=exc, countdown=300)
