"""Real Celery consumer and HTTP receiver; memory broker keeps tests self-contained.

The separate Docker smoke test covers the Redis/PostgreSQL transports.
"""
import hashlib
import hmac
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from celery.contrib.testing.worker import start_worker
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app import api, tasks
from app.celery_app import celery_app
from app.config import settings
from app.models import Delivery
from tests.test_api import EVENT


def test_api_to_real_worker_to_http_receiver(client, auth, db, monkeypatch):
    received = []

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append((body, self.headers["X-EventGate-Signature"]))
            self.send_response(500 if len(received) == 1 else 200)
            self.end_headers()
            self.wfile.write(b"local test result")

        def log_message(self, *args):
            pass

    receiver = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    receiver_thread = threading.Thread(target=receiver.serve_forever, daemon=True)
    receiver_thread.start()
    monkeypatch.setattr(settings, "allow_private_webhooks", True)
    monkeypatch.setattr(tasks, "SessionLocal", sessionmaker(bind=db.get_bind(), expire_on_commit=False))
    monkeypatch.setattr(api, "enqueue_delivery", tasks.enqueue_delivery)
    old_broker = celery_app.conf.broker_url
    old_backend = celery_app.conf.result_backend
    celery_app.conf.update(broker_url="memory://", result_backend="cache+memory://")
    try:
        with start_worker(celery_app, perform_ping_check=False, pool="solo", concurrency=1, shutdown_timeout=10):
            response = client.post("/api/endpoints/", headers=auth, json={
                "name": "Real local receiver", "url": f"http://127.0.0.1:{receiver.server_port}/",
                "secret": "live-test-secret", "max_attempts": 2, "retry_base_delay": 1,
            })
            assert response.status_code == 201
            endpoint_id = response.json()["id"]
            assert client.post("/api/subscriptions/", headers=auth,
                               json={"endpoint": endpoint_id, "event_type": "order.created"}).status_code == 201
            assert client.post("/api/events/", headers=auth, json=EVENT).status_code == 201
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                tasks.dispatch_due.delay()
                time.sleep(0.25)
                db.expire_all()
                delivery = db.scalar(select(Delivery))
                db.commit()  # End the reader's SQLite transaction between polls.
                if delivery.status == "SUCCESS":
                    break
            assert delivery.status == "SUCCESS"
            assert delivery.attempt_count == 2
            assert len(received) == 2
            for body, signature in received:
                assert signature == hmac.new(b"live-test-secret", body, hashlib.sha256).hexdigest()
            attempts = client.get(f"/api/deliveries/{delivery.id}/attempts/", headers=auth).json()
            assert [attempt["status"] for attempt in attempts] == ["FAILED", "SUCCESS"]
    finally:
        receiver.shutdown()
        receiver.server_close()
        receiver_thread.join(timeout=5)
        celery_app.conf.update(broker_url=old_broker, result_backend=old_backend)
