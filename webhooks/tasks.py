from celery import shared_task
from webhooks.models import Delivery
from webhooks.services.delivery import retry_delivery

@shared_task
def retry_delivery_task(delivery_id):
    delivery=Delivery.objects.get(id=delivery_id)
    return retry_delivery(delivery)
    