import os

# Set safe test settings before importing the application.
os.environ["DEBUG"] = "True"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ALLOW_PRIVATE_WEBHOOKS"] = "False"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db, make_engine
from app.main import app
from app.models import User
from app.security import create_token, hash_password


@pytest.fixture
def db(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.sqlite3'}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session
    engine.dispose()


@pytest.fixture(scope="session")
def password_hash():
    return hash_password("test-password-123")


@pytest.fixture
def user(db, password_hash):
    user = User(username="alice", password_hash=password_hash)
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def other(db, password_hash):
    user = User(username="bob", password_hash=password_hash)
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def client(db, monkeypatch):
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr("app.api.enqueue_delivery", lambda delivery_id: None)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def auth(user):
    return {"Authorization": f"Bearer {create_token(user)}"}
