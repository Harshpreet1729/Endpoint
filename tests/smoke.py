"""Exercise actual HTTP -> PostgreSQL -> Redis -> Celery -> HTTP delivery."""
import hashlib
import hmac
import json
import secrets
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, "/app")
from app.database import SessionLocal
from app.models import User
from app.security import hash_password

password = secrets.token_urlsafe(24)
username = "smoke-" + secrets.token_hex(6)
with SessionLocal() as db:
    db.add(User(username=username, password_hash=hash_password(password)))
    db.commit()

base = "http://web:8000"
token_request = Request(base + "/api/auth/token", data=urlencode({"username": username, "password": password}).encode())
with urlopen(token_request, timeout=10) as response:
    token = json.load(response)["access_token"]


def api(path, data=None):
    request = Request(base + path, data=json.dumps(data).encode() if data is not None else None,
                      headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def wait_status(delivery_id, status):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        deliveries = api("/api/deliveries/")
        found = next(item for item in deliveries if item["id"] == delivery_id)
        if found["status"] == status:
            return found
        time.sleep(1)
    raise AssertionError(f"Delivery {delivery_id} did not reach {status}")


for path, final_status in [("retry", "SUCCESS"), ("fail", "DEAD_LETTERED")]:
    endpoint = api("/api/endpoints/", {"name": path, "url": f"http://receiver:9000/{path}",
                   "secret": "smoke-signing-secret", "max_attempts": 2, "retry_base_delay": 1})
    api("/api/subscriptions/", {"endpoint": endpoint["id"], "event_type": path})
    event = api("/api/events/", {"event_type": path, "payload": {"source": "smoke"}, "idempotency_key": path})
    repeated = api("/api/events/", {"event_type": path, "payload": {"source": "smoke"}, "idempotency_key": path})
    assert event["id"] == repeated["id"]
    deliveries = api("/api/deliveries/")
    delivery = next(item for item in deliveries if item["event_id"] == event["id"])
    result = wait_status(delivery["id"], final_status)
    assert result["attempt_count"] == 2
    assert len(api(f"/api/deliveries/{delivery['id']}/attempts/")) == 2
    if path == "fail":
        replay = api(f"/api/deliveries/{delivery['id']}/replay/", {})
        assert replay["id"] != delivery["id"]
        wait_status(replay["id"], "DEAD_LETTERED")

with urlopen("http://receiver:9000/captures", timeout=10) as response:
    captures = json.load(response)
for capture in captures:
    expected = hmac.new(b"smoke-signing-secret", capture["body"].encode(), hashlib.sha256).hexdigest()
    assert capture["signature"] == expected
assert len(captures) >= 6
print("PASS: real PostgreSQL, Redis, Celery, HMAC, idempotency, retries, dead-lettering, replay")
