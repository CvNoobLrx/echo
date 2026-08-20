"""Echo 的非周期异步任务队列。"""
from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "echo",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks",
        "app.tasks.parse",
        "app.tasks.image",
        "app.tasks.memory",
        "app.tasks.daily_review",
        "app.tasks.news",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=False,
    task_track_started=True,
    task_default_queue="default",
    task_routes={
        "app.tasks.parse.*": {"queue": "parse"},
        "app.tasks.image.*": {"queue": "parse"},
        "app.tasks.memory.*": {"queue": "memory"},
        "app.tasks.news.*": {"queue": "news"},
    },
    beat_schedule={
        "daily-news-at-eight": {
            "task": "app.tasks.news.dispatch_daily_news",
            "schedule": crontab(hour=8, minute=0),
        },
    },
)
