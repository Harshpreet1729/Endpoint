"""Catch unsafe deployment configuration before serving requests."""

import pytest

from app.config import Settings
from app.database import normalize_url


@pytest.fixture
def production_env(monkeypatch):
    values = {
        "DEBUG": "False",
        "SECRET_KEY": "test-only-secret-" * 4,
        "DATABASE_URL": "postgres://test:test@postgres.internal/eventgate",
        "CELERY_BROKER_URL": "redis://redis.internal:6379/0",
        "CELERY_RESULT_BACKEND": "redis://redis.internal:6379/0",
        "ALLOWED_HOSTS": "",
        "CSRF_TRUSTED_ORIGINS": "",
        "ALLOW_PRIVATE_WEBHOOKS": "False",
        "RAILWAY_PROJECT_ID": "test-project",
        "RAILWAY_PUBLIC_DOMAIN": "eventgate-test.up.railway.app",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_railway_settings_and_postgres_driver(production_env):
    settings = Settings()
    assert settings.debug is False
    assert "eventgate-test.up.railway.app" in settings.allowed_hosts
    assert "healthcheck.railway.app" in settings.allowed_hosts
    assert "https://eventgate-test.up.railway.app" in settings.csrf_origins
    assert normalize_url(settings.database_url).startswith("postgresql+psycopg://")


@pytest.mark.parametrize(
    "name,value,message",
    [
        ("SECRET_KEY", "", "SECRET_KEY"),
        ("DATABASE_URL", "sqlite:///local.sqlite3", "PostgreSQL"),
        ("CELERY_BROKER_URL", "", "Redis URLs"),
        ("CELERY_RESULT_BACKEND", "", "Redis URLs"),
        ("ALLOW_PRIVATE_WEBHOOKS", "True", "local development only"),
        ("ALLOWED_HOSTS", "*", "explicit production ALLOWED_HOSTS"),
    ],
)
def test_unsafe_production_configuration_fails(
    production_env, monkeypatch, name, value, message
):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=message):
        Settings()
