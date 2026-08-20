from celery import shared_task
from webhooks.models import Delivery, Event, Endpoint
from webhooks.services.delivery import retry_delivery, MAX_ATTEMPTS, deliver_event

@shared_task(bind=True, max_retries=None)
def retry_delivery_task(self,delivery_id):
    delivery=Delivery.objects.get(id=delivery_id)
    retry_delivery(delivery)
    delivery.refresh_from_db()

    if delivery.status==Delivery.Status.FAILED:
        if delivery.attempt_count>=MAX_ATTEMPTS:
            delivery.status=Delivery.Status.DEAD_LETTERED
            delivery.save()
        else:
            delay=5*(2**(delivery.attempt_count-2))
            raise self.retry(
                args=[delivery_id],
                countdown=delay
            )

@shared_task
def deliver_event_task(event_id, endpoint_id):
    event = Event.objects.get(id=event_id)
    endpoint = Endpoint.objects.get(id=endpoint_id)
    deliver_event(event, endpoint)

    delivery=Delivery.objects.filter(
        event=event,
        endpoint=endpoint
    ).latest("id")
    if delivery.status==Delivery.Status.FAILED:
        retry_delivery_task.delay(delivery.id)