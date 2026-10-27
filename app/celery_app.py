"""Celery runs slow network calls outside the API process."""

from celery import Celery

from app.config import settings

celery_app = Celery("eventgate", broker=settings.broker_url, backend=settings.result_backend, include=["app.tasks"])
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=2,
    broker_transport_options={"socket_connect_timeout": 2, "socket_timeout": 2},
    task_publish_retry=False,
    task_soft_time_limit=30,
    task_time_limit=40,
    worker_prefetch_multiplier=1,
    timezone="UTC",
    # The DB is the source of truth: redis outages never discard saved work.
    beat_schedule={"recover-due-deliveries": {"task": "app.tasks.dispatch_due", "schedule": 5.0}},
)
