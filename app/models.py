"""EventGate SQL tables, using the eg_ prefix."""

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    # Store UTC without a timezone so SQLite and PostgreSQL behave identically.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "eg_users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(150), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Endpoint(Base):
    __tablename__ = "eg_endpoints"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("eg_users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(String(2048))
    secret: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    max_attempts: Mapped[int] = mapped_column(default=5)
    retry_base_delay: Mapped[int] = mapped_column(default=5)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Subscription(Base):
    __tablename__ = "eg_subscriptions"
    __table_args__ = (UniqueConstraint("endpoint_id", "event_type", name="uq_eg_subscription"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint_id: Mapped[int] = mapped_column(ForeignKey("eg_endpoints.id"))
    event_type: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Event(Base):
    __tablename__ = "eg_events"
    __table_args__ = (UniqueConstraint("owner_id", "idempotency_key", name="uq_eg_event_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("eg_users.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Delivery(Base):
    __tablename__ = "eg_deliveries"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("eg_events.id"), index=True)
    endpoint_id: Mapped[int] = mapped_column(ForeignKey("eg_endpoints.id"))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str] = mapped_column(Text, default="")
    attempt_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow, nullable=True, index=True)
    # A short lease prevents two tasks from sending the same delivery together.
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    event: Mapped[Event] = relationship()
    endpoint: Mapped[Endpoint] = relationship()


class DeliveryAttempt(Base):
    __tablename__ = "eg_delivery_attempts"
    __table_args__ = (UniqueConstraint("delivery_id", "attempt_number", name="uq_eg_attempt"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("eg_deliveries.id"), index=True)
    attempt_number: Mapped[int]
    status: Mapped[str] = mapped_column(String(20))
    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
