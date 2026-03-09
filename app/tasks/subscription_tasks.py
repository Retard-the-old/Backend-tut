import asyncio
import logging
from datetime import datetime, timezone
from celery_app import celery
from sqlalchemy import select
from app.db.database import AsyncSessionLocal
from app.models.subscription import Subscription
from app.models.user import User
from app.services.email_service import send_subscription_expired

logger = logging.getLogger(__name__)

@celery.task(name="app.tasks.subscription_tasks.expire_overdue_subscriptions")
def expire_overdue_subscriptions():
    logger.info("Checking for expired subscriptions")
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    async def _run():
        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
            result = await db.execute(
                select(Subscription).where(
                    Subscription.status == "active",
                    Subscription.current_period_end < now,
                )
            )
            count = 0
            for sub in result.scalars().all():
                sub.status = "expired"
                user_result = await db.execute(select(User).where(User.id == sub.user_id))
                user = user_result.scalar_one_or_none()
                if user:
                    await send_subscription_expired(user.email, user.full_name)
                count += 1
            await db.commit()
            logger.info("Expired %d subscriptions", count)
            return count

    return loop.run_until_complete(_run())
