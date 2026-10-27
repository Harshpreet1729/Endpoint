"""Send a signed payload and save one attempt. Called only by Celery."""

import hashlib
import hmac
import ipaddress
import json
import socket
from datetime import timedelta
from urllib.parse import urlsplit

import urllib3
from sqlalchemy import or_, update

from app.config import settings
from app.models import Delivery, DeliveryAttempt, utcnow


def send_webhook(url: str, body: bytes, headers: dict) -> tuple[int, str]:
    """Resolve once, reject private addresses, and connect to the validated IP.

    Pinning the connection prevents a hostname from changing to a private IP
    between validation and sending. HTTPS still verifies the original hostname.
    """
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Invalid webhook URL")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    if not addresses:
        raise ValueError("Webhook host has no address")
    ips = [item[4][0] for item in addresses]
    if not settings.allow_private_webhooks and any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise ValueError("Webhook must use a public IP address")
    pool_type = urllib3.HTTPSConnectionPool if parsed.scheme == "https" else urllib3.HTTPConnectionPool
    tls_options = {"server_hostname": parsed.hostname, "assert_hostname": parsed.hostname} if parsed.scheme == "https" else {}
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    with pool_type(ips[0], port=port, timeout=urllib3.Timeout(connect=5, read=5), **tls_options) as pool:
        response = pool.urlopen("POST", path, body=body, headers={**headers, "Host": parsed.netloc},
                                retries=False, redirect=False, preload_content=False)
        try:
            # Cap stored response size; do not log URL credentials or payloads.
            return response.status, response.read(65536).decode("utf-8", errors="replace")
        finally:
            response.close()


def due_condition(now):
    return (
        Delivery.status.in_(["PENDING", "FAILED"]),
        Delivery.next_attempt_at <= now,
        or_(Delivery.locked_until.is_(None), Delivery.locked_until <= now),
    )


def process_delivery(db, delivery_id: int):
    now = utcnow()
    claim = db.execute(update(Delivery).where(Delivery.id == delivery_id, *due_condition(now))
                       .values(locked_until=now + timedelta(seconds=60)))
    db.commit()
    if claim.rowcount != 1:
        return  # Already complete, not due, or another worker owns the lease.
    delivery = db.get(Delivery, delivery_id)
    db.refresh(delivery)
    endpoint = delivery.endpoint
    if not endpoint.is_active or delivery.attempt_count >= endpoint.max_attempts:
        delivery.status = "DEAD_LETTERED"
        delivery.next_attempt_at = None
        delivery.locked_until = None
        db.commit()
        return

    body = json.dumps(delivery.event.payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(endpoint.secret.encode(), body, hashlib.sha256).hexdigest()
    try:
        status_code, response_body = send_webhook(endpoint.url, body, {
            "Content-Type": "application/json",
            "X-EventGate-Signature": signature,
            "X-EventGate-Delivery-ID": str(delivery.id),
        })
    except (urllib3.exceptions.HTTPError, OSError, ValueError):
        status_code, response_body = None, "Delivery failed: network error or disallowed destination"

    success = status_code is not None and 200 <= status_code < 300
    delivery.attempt_count += 1
    delivery.response_status_code = status_code
    delivery.response_body = response_body
    delivery.locked_until = None
    delivery.next_attempt_at = None
    if success:
        delivery.status = "SUCCESS"
    elif delivery.attempt_count >= endpoint.max_attempts:
        delivery.status = "DEAD_LETTERED"
    else:
        delivery.status = "FAILED"
        delay = min(endpoint.retry_base_delay * 2 ** (delivery.attempt_count - 1), 86400)
        delivery.next_attempt_at = utcnow() + timedelta(seconds=delay)
    db.add(DeliveryAttempt(delivery_id=delivery.id, attempt_number=delivery.attempt_count,
                           status="SUCCESS" if success else "FAILED",
                           response_status_code=status_code, response_body=response_body))
    db.commit()
