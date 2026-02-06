from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "knowrenewals",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.reminders", "app.tasks.cleanup"],
)

celery_app.conf.update(
    timezone="UTC",
    task_default_queue="default",
    beat_schedule={
        "daily-reminder-scan": {
            "task": "app.tasks.reminders.schedule_notice_reminders",
            "schedule": crontab(hour=6, minute=0),
        },
        "daily-refresh-token-cleanup": {
            "task": "app.tasks.cleanup.purge_expired_refresh_tokens",
            "schedule": crontab(hour=3, minute=0),
        },
    },
)
