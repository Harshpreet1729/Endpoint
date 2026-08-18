import requests
from webhooks.models import Delivery

def deliver_event(event, endpoint):
    response=requests.post(
        endpoint.url,
        json=event.payload
    )

    Delivery.objects.create(
        event=event,
        endpoint=endpoint,
        status=Delivery.Status.SUCCESS if response.ok else Delivery.Status.FAILED,
        response_status_code=response.status_code,
        response_body=response.text
    )
    return response