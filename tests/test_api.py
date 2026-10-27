import re

from kombu.exceptions import OperationalError
from sqlalchemy import func, select

from app import tasks
from app.models import Delivery, Endpoint, Event
from app.security import create_token


ENDPOINT = {"name": "Receiver", "url": "https://example.com/webhook", "secret": "test-secret"}
EVENT = {"event_type": "order.created", "payload": {"order_id": 1}}


def subscribe(client, auth):
    response = client.post("/api/endpoints/", headers=auth, json=ENDPOINT)
    assert response.status_code == 201, response.text
    endpoint = response.json()
    assert "secret" not in endpoint
    response = client.post("/api/subscriptions/", headers=auth, json={"endpoint": endpoint["id"], "event_type": "order.created"})
    assert response.status_code == 201, response.text
    assert response.json()["endpoint"] == endpoint["id"]
    return endpoint


def test_health_docs_static_and_auth(client, user):
    assert client.get("/health/").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/api/events/").status_code == 401
    response = client.post("/api/auth/token", data={"username": "alice", "password": "wrong"})
    assert response.status_code == 401
    response = client.post("/api/auth/token", data={"username": "alice", "password": "test-password-123"})
    token = response.json()["access_token"]
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["username"] == "alice"


def test_subscription_routing_and_idempotency(client, auth, db):
    subscribe(client, auth)
    response = client.post("/api/events/", headers={**auth, "Idempotency-Key": "request-1"}, json=EVENT)
    assert response.status_code == 201
    repeat = client.post("/api/events/", headers={**auth, "Idempotency-Key": "request-1"}, json=EVENT)
    assert repeat.status_code == 200 and repeat.json()["id"] == response.json()["id"]
    assert db.scalar(select(func.count(Delivery.id))) == 1
    assert db.scalar(select(func.count(Event.id))) == 1
    conflict = client.post("/api/events/", headers={**auth, "Idempotency-Key": "request-1"}, json={**EVENT, "payload": {"order_id": 2}})
    assert conflict.status_code == 409
    client.post("/api/events/", headers=auth, json={**EVENT, "event_type": "unsubscribed"})
    assert db.scalar(select(func.count(Delivery.id))) == 1


def test_ownership_enforced_everywhere(client, auth, other, db):
    endpoint = subscribe(client, auth)
    client.post("/api/events/", headers=auth, json=EVENT)
    delivery = db.scalar(select(Delivery))
    other_auth = {"Authorization": f"Bearer {create_token(other)}"}
    for route in ("endpoints", "events", "subscriptions", "deliveries"):
        assert client.get(f"/api/{route}/", headers=other_auth).json() == []
    assert client.post("/api/subscriptions/", headers=other_auth, json={"endpoint": endpoint["id"], "event_type": "x"}).status_code == 404
    assert client.put(f"/api/endpoints/{endpoint['id']}/", headers=other_auth, json=ENDPOINT).status_code == 404
    assert client.post(f"/api/deliveries/{delivery.id}/replay/", headers=other_auth).status_code == 404
    assert client.get(f"/api/deliveries/{delivery.id}/attempts/", headers=other_auth).status_code == 404


def test_validation_duplicate_subscription_and_deactivation(client, auth, db):
    assert client.post("/api/endpoints/", headers=auth, json={**ENDPOINT, "max_attempts": 0}).status_code == 422
    assert client.post("/api/endpoints/", headers=auth, json={**ENDPOINT, "url": "https://user:secret@example.com/"}).status_code == 422
    # Match PostgreSQL's URL column limit instead of failing during INSERT.
    too_long = "https://example.com/" + "a" * 2040
    assert client.post("/api/endpoints/", headers=auth, json={**ENDPOINT, "url": too_long}).status_code == 422
    endpoint = subscribe(client, auth)
    duplicate = client.post("/api/subscriptions/", headers=auth, json={"endpoint": endpoint["id"], "event_type": "order.created"})
    assert duplicate.status_code == 409
    assert client.delete(f"/api/endpoints/{endpoint['id']}/", headers=auth).status_code == 204
    client.post("/api/events/", headers=auth, json=EVENT)
    assert db.scalar(select(func.count(Delivery.id))) == 0
    assert db.get(Endpoint, endpoint["id"]).is_active is False


def test_replay_queues_new_delivery_without_deleting_history(client, auth, db):
    subscribe(client, auth)
    client.post("/api/events/", headers=auth, json=EVENT)
    original = db.scalar(select(Delivery))
    assert client.post(f"/api/deliveries/{original.id}/replay/", headers=auth).status_code == 409
    original.status = "DEAD_LETTERED"
    original.attempt_count = 5
    original.next_attempt_at = None
    db.commit()
    replay = client.post(f"/api/deliveries/{original.id}/replay/", headers=auth)
    assert replay.status_code == 202
    assert replay.json()["id"] != original.id
    assert replay.json()["attempt_count"] == 0
    assert db.scalar(select(func.count(Delivery.id))) == 2


def token_from_html(html):
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def test_browser_login_csrf_dashboard_logout(client, user):
    assert client.get("/api/dashboard/", follow_redirects=False).status_code == 303
    login = client.get("/api-auth/login/")
    token = token_from_html(login.text)
    credentials = {"username": "alice", "password": "test-password-123", "csrf": token}
    assert client.post("/api-auth/login/", data={**credentials, "csrf": "wrong"}).status_code == 403
    dashboard = client.post("/api-auth/login/", data=credentials)
    assert dashboard.status_code == 200 and "EventGate Dashboard" in dashboard.text
    csrf = token_from_html(dashboard.text)
    assert client.post("/api/endpoints/", json=ENDPOINT).status_code == 403
    assert client.post("/api/endpoints/", headers={"X-CSRF-Token": csrf, "Origin": "https://attacker.example"}, json=ENDPOINT).status_code == 403
    assert client.post("/api/endpoints/", headers={"X-CSRF-Token": csrf}, json=ENDPOINT).status_code == 201
    assert client.post("/api-auth/logout/", data={"csrf": csrf}, follow_redirects=False).status_code == 303
    assert client.get("/api/events/").status_code == 401


def test_broker_failure_preserves_event_and_pending_delivery(client, auth, db, monkeypatch, caplog):
    subscribe(client, auth)
    monkeypatch.setattr("app.api.enqueue_delivery", tasks.enqueue_delivery)
    def unavailable(*args):
        raise OperationalError("redis://secret-must-not-appear")
    monkeypatch.setattr(tasks.deliver, "delay", unavailable)
    assert client.post("/api/events/", headers=auth, json=EVENT).status_code == 201
    assert db.scalar(select(Delivery)).status == "PENDING"
    assert "secret-must-not-appear" not in caplog.text


def test_password_change_and_disabled_user_invalidate_tokens(client, auth, db, user):
    user.password_hash = "changed"
    db.commit()
    assert client.get("/api/events/", headers=auth).status_code == 401
    new_token = {"Authorization": f"Bearer {create_token(user)}"}
    user.is_active = False
    db.commit()
    assert client.get("/api/events/", headers=new_token).status_code == 401
