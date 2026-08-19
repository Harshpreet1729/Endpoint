from celery import shared_task
from webhooks.models import Delivery
from webhooks.services.delivery import retry_delivery, MAX_ATTEMPTS

@shared_task(bind=True, max_retries=None)
def retry_delivery_task(self,delivery_id):
    delivery=Delivery.objects.get(id=delivery_id)
    retry_delivery(delivery)
    delivery.refresh_from_db()
    if(
        delivery.status==Delivery.Status.FAILED and delivery.attempt_count<MAX_ATTEMPTS
    ):
        raise self.retry(
            args=[delivery_id],
            countdown=5
        )
    