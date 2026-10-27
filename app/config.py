"""Environment settings shared by the API, worker, and migration command."""

import os
from dataclasses import dataclass, field


def boolean(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    if value.lower() not in {"true", "false", "1", "0"}:
        raise ValueError(f"{name} must be true or false")
    return value.lower() in {"true", "1"}


def csv(name: str) -> list[str]:
    return [value.strip() for value in os.getenv(name, "").split(",") if value.strip()]


@dataclass
class Settings:
    debug: bool = field(default_factory=lambda: boolean("DEBUG", not bool(os.getenv("RAILWAY_PROJECT_ID"))))
    secret_key: str = field(default_factory=lambda: os.getenv("SECRET_KEY", ""))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./fastapi.sqlite3"))
    broker_url: str = field(default_factory=lambda: os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0"))
    result_backend: str = field(default_factory=lambda: os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/0"))
    allowed_hosts: list[str] = field(default_factory=lambda: csv("ALLOWED_HOSTS"))
    csrf_origins: list[str] = field(default_factory=lambda: csv("CSRF_TRUSTED_ORIGINS"))
    allow_private_webhooks: bool = field(default_factory=lambda: boolean("ALLOW_PRIVATE_WEBHOOKS"))
    token_seconds: int = 3600

    def __post_init__(self):
        if self.debug and not self.secret_key:
            self.secret_key = "local-development-only-never-use-in-production"
        if not self.debug:
            if len(self.secret_key) < 50 or self.secret_key.startswith("local-development"):
                raise ValueError("Production requires a random SECRET_KEY of at least 50 characters")
            if not self.database_url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
                raise ValueError("Production requires a PostgreSQL DATABASE_URL")
            if not os.getenv("CELERY_BROKER_URL") or not os.getenv("CELERY_RESULT_BACKEND"):
                raise ValueError("Production requires both Celery Redis URLs")
            if self.allow_private_webhooks:
                raise ValueError("ALLOW_PRIVATE_WEBHOOKS is for local development only")
        domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
        if domain:
            self.allowed_hosts.append(domain)
            self.csrf_origins.append(f"https://{domain}")
        if os.getenv("RAILWAY_PROJECT_ID"):
            self.allowed_hosts.append("healthcheck.railway.app")
        if self.debug:
            self.allowed_hosts.extend(["localhost", "127.0.0.1", "testserver"])
        if not self.allowed_hosts:
            raise ValueError("Set ALLOWED_HOSTS or generate a Railway public domain")
        if not self.debug and "*" in self.allowed_hosts:
            raise ValueError("Use explicit production ALLOWED_HOSTS")


settings = Settings()
