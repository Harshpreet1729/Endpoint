import hashlib
import hmac
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.delivery import process_delivery, send_webhook
from app.models import Delivery, DeliveryAttempt, Endpoint, Event, utcnow


@pytest.fixture
def delivery(db, user):
    endpoint = Endpoint(owner_id=user.id, name="Test", url="https://example.com/webhook", secret="test-secret")
    event = Event(owner_id=user.id, event_type="test", payload={"z": 2, "a": 1})
    db.add_all([endpoint, event])
    db.flush()
    delivery = Delivery(endpoint_id=endpoint.id, event_id=event.id)
    db.add(delivery)
    db.commit()
    return delivery


def test_success_records_exact_hmac_and_attempt(db, delivery, monkeypatch):
    def receiver(url, body, headers):
        assert body == b'{"a":1,"z":2}'
        assert headers["X-EventGate-Signature"] == hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
        assert headers["X-EventGate-Delivery-ID"] == str(delivery.id)
        return 200, "OK"
    monkeypatch.setattr("app.delivery.send_webhook", receiver)
    process_delivery(db, delivery.id)
    assert delivery.status == "SUCCESS" and delivery.attempt_count == 1
    attempt = db.scalar(select(DeliveryAttempt))
    assert attempt.status == "SUCCESS" and attempt.response_status_code == 200
    process_delivery(db, delivery.id)  # duplicate task must not send twice
    assert delivery.attempt_count == 1


def test_failure_records_attempt_and_exponential_retry(db, delivery, monkeypatch):
    def fail(*args):
        raise OSError("secret URL must not leak")
    monkeypatch.setattr("app.delivery.send_webhook", fail)
    process_delivery(db, delivery.id)
    assert delivery.status == "FAILED" and delivery.attempt_count == 1
    assert 3 <= (delivery.next_attempt_at - utcnow()).total_seconds() <= 5
    assert "secret" not in delivery.response_body
    delivery.next_attempt_at = utcnow() - timedelta(seconds=1)
    db.commit()
    process_delivery(db, delivery.id)
    assert delivery.attempt_count == 2
    assert 8 <= (delivery.next_attempt_at - utcnow()).total_seconds() <= 10


@pytest.mark.parametrize("limit", [1, 3, 7])
def test_custom_attempt_limit_dead_letters(db, delivery, monkeypatch, limit):
    delivery.endpoint.max_attempts = limit
    monkeypatch.setattr("app.delivery.send_webhook", lambda *args: (500, "Unavailable"))
    for _ in range(limit):
        delivery.next_attempt_at = utcnow() - timedelta(seconds=1)
        db.commit()
        process_delivery(db, delivery.id)
    assert delivery.status == "DEAD_LETTERED" and delivery.attempt_count == limit
    assert delivery.next_attempt_at is None
    assert len(db.scalars(select(DeliveryAttempt)).all()) == limit


def test_maxed_out_delivery_never_sends(db, delivery, monkeypatch):
    delivery.attempt_count = 5
    db.commit()
    def unexpected(*args):
        pytest.fail("Exhausted delivery attempted a network call")
    monkeypatch.setattr("app.delivery.send_webhook", unexpected)
    process_delivery(db, delivery.id)
    assert delivery.status == "DEAD_LETTERED"


def test_leased_task_is_skipped_then_recovered(db, delivery, monkeypatch):
    monkeypatch.setattr("app.delivery.send_webhook", lambda *args: (200, "OK"))
    delivery.locked_until = utcnow() + timedelta(seconds=60)
    db.commit()
    process_delivery(db, delivery.id)
    assert delivery.attempt_count == 0
    delivery.locked_until = utcnow() - timedelta(seconds=1)
    db.commit()
    process_delivery(db, delivery.id)
    assert delivery.status == "SUCCESS"


@pytest.mark.parametrize("address", ["127.0.0.1", "10.1.0.1", "169.254.169.254", "::1", "::ffff:127.0.0.1"])
def test_private_webhook_addresses_rejected(monkeypatch, address):
    monkeypatch.setattr("app.delivery.socket.getaddrinfo", lambda *args, **kwargs: [(0, 0, 0, "", (address, 80))])
    with pytest.raises(ValueError, match="public IP"):
        send_webhook("http://example.com/", b"{}", {})
