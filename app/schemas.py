"""Pydantic request and response shapes for the API."""

from datetime import datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, JsonValue, field_validator


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EndpointCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: HttpUrl = Field(max_length=2048)
    secret: str = Field(min_length=1, max_length=255)
    is_active: bool = True
    max_attempts: int = Field(default=5, ge=1, le=20)
    retry_base_delay: int = Field(default=5, ge=1, le=3600)

    @field_validator("url")
    @classmethod
    def no_credentials(cls, value):
        parsed = urlsplit(str(value))
        if parsed.username or parsed.password or parsed.fragment:
            raise ValueError("Webhook URLs must not contain credentials or fragments")
        return value


class EndpointOut(Output):
    id: int
    name: str
    url: str
    is_active: bool
    max_attempts: int
    retry_base_delay: int
    created_at: datetime
    # secret deliberately has no response field.


class EventCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=100)
    payload: JsonValue
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)


class EventOut(Output):
    id: int
    event_type: str
    payload: JsonValue
    idempotency_key: str | None
    created_at: datetime


class SubscriptionCreate(BaseModel):
    endpoint: int = Field(gt=0)
    event_type: str = Field(min_length=1, max_length=100)


class SubscriptionOut(Output):
    id: int
    endpoint: int = Field(validation_alias="endpoint_id")
    event_type: str
    created_at: datetime


class DeliveryOut(Output):
    id: int
    event_id: int
    endpoint_id: int
    status: str
    attempt_count: int
    response_status_code: int | None
    response_body: str
    next_attempt_at: datetime | None
    created_at: datetime


class AttemptOut(Output):
    id: int
    delivery_id: int
    attempt_number: int
    status: str
    response_status_code: int | None
    response_body: str
    created_at: datetime
