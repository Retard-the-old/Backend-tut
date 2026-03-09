from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery = Celery(
    "tutorii",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Dubai",
    enable_utc=True,
    beat_schedule={
        "weekly-payouts": {
            "task": "app.tasks.payout_tasks.run_weekly_payouts",
            "schedule": crontab(hour=9, minute=0, day_of_week=2),
        },
        "expire-subscriptions": {
            "task": "app.tasks.subscription_tasks.expire_overdue_subscriptions",
            "schedule": crontab(hour=1, minute=0),
        },
    },
)
celery.autodiscover_tasks(["app.tasks"])
