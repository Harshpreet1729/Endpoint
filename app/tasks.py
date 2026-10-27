"""Small Celery wrappers; the delivery logic lives in delivery.py for testing."""

import logging

from kombu.exceptions import OperationalError
from sqlalchemy import select

from app.celery_app import celery_app
from app.database import SessionLocal
from app.delivery import due_condition, process_delivery
from app.models import Delivery, utcnow

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.deliver")
def deliver(delivery_id: int):
    with SessionLocal() as db:
        process_delivery(db, delivery_id)


def enqueue_delivery(delivery_id: int):
    try:
        deliver.delay(delivery_id)
    except (OperationalError, OSError):
        # No exception text: a broker error may contain credentials.
        logger.warning("Broker unavailable; saved delivery %s will be recovered by the scheduler", delivery_id)


@celery_app.task(name="app.tasks.dispatch_due")
def dispatch_due():
    with SessionLocal() as db:
        ids = db.scalars(select(Delivery.id).where(*due_condition(utcnow()))
                         .order_by(Delivery.next_attempt_at, Delivery.id).limit(100)).all()
    for delivery_id in ids:
        enqueue_delivery(delivery_id)
