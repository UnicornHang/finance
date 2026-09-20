"""Celery 应用实例。"""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "finance",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.ocr_task",
        "app.tasks.contract_task",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    worker_max_tasks_per_child=1000,
    worker_prefetch_multiplier=1,
)