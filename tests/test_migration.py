from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select

from app import tasks
from app.database import make_engine
from app.models import Delivery, Event


def test_alembic_creates_matching_schema_and_preserves_unrelated_tables(tmp_path, monkeypatch):
    from app import database
    engine = make_engine(f"sqlite:///{tmp_path / 'migrations.sqlite3'}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE unrelated_note (id INTEGER PRIMARY KEY, value TEXT)")
        connection.exec_driver_sql("INSERT INTO unrelated_note VALUES (1, 'keep me')")
    monkeypatch.setattr(database, "engine", engine)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    command.upgrade(config, "head")  # Repeated deploys must be safe.
    command.check(config)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT value FROM unrelated_note").scalar() == "keep me"
    assert "eg_users" in inspect(engine).get_table_names()
    engine.dispose()


def test_scheduler_only_queues_due_work(db, user, monkeypatch):
    from app.models import Endpoint
    endpoint = Endpoint(owner_id=user.id, name="Test", url="https://example.com/", secret="test")
    event = Event(owner_id=user.id, event_type="test", payload={})
    db.add_all([endpoint, event])
    db.flush()
    pending = Delivery(event_id=event.id, endpoint_id=endpoint.id)
    complete = Delivery(event_id=event.id, endpoint_id=endpoint.id, status="SUCCESS", next_attempt_at=None)
    db.add_all([pending, complete])
    db.commit()
    @contextmanager
    def session():
        yield db
    monkeypatch.setattr(tasks, "SessionLocal", session)
    queued = []
    monkeypatch.setattr(tasks, "enqueue_delivery", queued.append)
    tasks.dispatch_due.run()
    assert queued == [pending.id]
