import requests
from webhooks.models import Delivery, DeliveryAttempt
import hmac
import hashlib
import json

MAX_ATTEMPTS = 5

def deliver_event(event, endpoint):
    try:
        payload_json=json.dumps(
            event.payload, 
            sort_keys=True,
            separators=(",",":")
            )
        payload_bytes=payload_json.encode("utf-8")

        signature=hmac.new(
            endpoint.secret.encode(),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()
        response=requests.post(
            endpoint.url,
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-EventGate-Signature": signature
            },
            timeout=5
        )

        delivery=Delivery.objects.create(
            event=event,
            endpoint=endpoint,
            status=Delivery.Status.SUCCESS if response.ok else Delivery.Status.FAILED,
            response_status_code=response.status_code,
            response_body=response.text
        )
        DeliveryAttempt.objects.create(
            delivery=delivery,
            attempt_number=1,
            status=DeliveryAttempt.Status.SUCCESS if response.ok else DeliveryAttempt.Status.FAILED,
            response_status_code=response.status_code,
            response_body=response.text
        )
        return response
    except requests.exceptions.RequestException as e:
        delivery=Delivery.objects.create(
            event=event,
            endpoint=endpoint,
            status=Delivery.Status.FAILED,
            response_status_code=None,
            response_body=str(e)
        )
        DeliveryAttempt.objects.create(
            delivery=delivery,
            attempt_number=1,
            status=DeliveryAttempt.Status.FAILED,
            response_status_code=None,
            response_body=str(e)
        )
        return None

def retry_delivery(delivery):

    if delivery.attempt_count>=MAX_ATTEMPTS:
        return None
    
    try:
        payload_json = json.dumps(
            delivery.event.payload,
            sort_keys=True,
            separators=(",", ":")
        )
        payload_bytes=payload_json.encode("utf-8")

        signature = hmac.new(
            delivery.endpoint.secret.encode(),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()
        response=requests.post(
            delivery.endpoint.url,
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-EventGate-Signature": signature
            },
            timeout=5
        )
        delivery.attempt_count += 1
        delivery.status=(
            Delivery.Status.SUCCESS if response.ok else Delivery.Status.FAILED
        )
        delivery.response_status_code=response.status_code
        delivery.response_body=response.text
        delivery.save()

        DeliveryAttempt.objects.create(
            delivery=delivery,
            attempt_number=delivery.attempt_count,
            status=DeliveryAttempt.Status.SUCCESS if response.ok else DeliveryAttempt.Status.FAILED,
            response_status_code=response.status_code,
            response_body=response.text
        )

        return response
    except requests.exceptions.RequestException as e:
        delivery.attempt_count += 1
        delivery.status = Delivery.Status.FAILED
        delivery.response_status_code = None
        delivery.response_body = str(e)
        delivery.save()
        DeliveryAttempt.objects.create(
            delivery=delivery,
            attempt_number=delivery.attempt_count,
            status=DeliveryAttempt.Status.FAILED,
            response_status_code=None,
            response_body=str(e)
        )
        return None

def replay_delivery(delivery):
    return deliver_event(
        delivery.event,
        delivery.endpoint
    )