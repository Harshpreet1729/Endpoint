import requests
from webhooks.models import Delivery

MAX_ATTEMPTS = 5

def deliver_event(event, endpoint):
    try:
        response=requests.post(
            endpoint.url,
            json=event.payload,
            timeout=5
        )

        Delivery.objects.create(
            event=event,
            endpoint=endpoint,
            status=Delivery.Status.SUCCESS if response.ok else Delivery.Status.FAILED,
            response_status_code=response.status_code,
            response_body=response.text
        )
        return response
    except requests.exceptions.RequestException as e:
        Delivery.objects.create(
            event=event,
            endpoint=endpoint,
            status=Delivery.Status.FAILED,
            response_status_code=None,
            response_body=str(e)
        )
        return None

def retry_delivery(delivery):

    if delivery.attempt_count>=MAX_ATTEMPTS:
        return None
    
    try:
        response=requests.post(
                delivery.endpoint.url,
                json=delivery.event.payload,
                timeout=5
        )
        delivery.attempt_count += 1
        delivery.status=(
            Delivery.Status.SUCCESS if response.ok else Delivery.Status.FAILED
        )
        delivery.response_status_code=response.status_code
        delivery.response_body=response.text
        delivery.save()
        return response
    except requests.exceptions.RequestException as e:
        delivery.attempt_count += 1
        delivery.status = Delivery.Status.FAILED
        delivery.response_status_code = None
        delivery.response_body = str(e)
        delivery.save()
        return None
    