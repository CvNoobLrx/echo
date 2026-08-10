"""Echo 的非周期异步任务队列。"""
from celery import Celery

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
    },
)
