"""Authenticated JSON API. Read one route at a time to follow the workflow."""

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Delivery, DeliveryAttempt, Endpoint, Event, Subscription, User
from app.schemas import AttemptOut, DeliveryOut, EndpointCreate, EndpointOut, EventCreate, EventOut, SubscriptionCreate, SubscriptionOut
from app.security import authenticate, create_token, get_current_user
from app.tasks import enqueue_delivery

router = APIRouter(prefix="/api")


@router.post("/auth/token", tags=["Authentication"])
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate(db, form.username, form.password)
    if not user:
        raise HTTPException(401, "Invalid username or password", headers={"WWW-Authenticate": "Bearer"})
    return {"access_token": create_token(user), "token_type": "bearer"}


@router.get("/auth/me", tags=["Authentication"])
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username}


def owned_endpoint(db: Session, endpoint_id: int, user: User) -> Endpoint:
    endpoint = db.scalar(select(Endpoint).where(Endpoint.id == endpoint_id, Endpoint.owner_id == user.id))
    if not endpoint:
        raise HTTPException(404, "Endpoint not found")
    return endpoint


def owned_delivery(db: Session, delivery_id: int, user: User) -> Delivery:
    delivery = db.scalar(select(Delivery).join(Event).where(Delivery.id == delivery_id, Event.owner_id == user.id))
    if not delivery:
        raise HTTPException(404, "Delivery not found")
    return delivery


@router.get("/endpoints/", response_model=list[EndpointOut], tags=["Endpoints"])
def list_endpoints(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100),
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(select(Endpoint).where(Endpoint.owner_id == user.id).order_by(Endpoint.id.desc()).offset(offset).limit(limit)).all()


@router.post("/endpoints/", response_model=EndpointOut, status_code=201, tags=["Endpoints"])
def create_endpoint(data: EndpointCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    endpoint = Endpoint(**data.model_dump(mode="json"), owner_id=user.id)
    db.add(endpoint)
    db.commit()
    return endpoint


@router.put("/endpoints/{endpoint_id}/", response_model=EndpointOut, tags=["Endpoints"])
def update_endpoint(endpoint_id: int, data: EndpointCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    endpoint = owned_endpoint(db, endpoint_id, user)
    for key, value in data.model_dump(mode="json").items():
        setattr(endpoint, key, value)
    db.commit()
    return endpoint


@router.delete("/endpoints/{endpoint_id}/", status_code=204, tags=["Endpoints"])
def deactivate_endpoint(endpoint_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Disable future delivery, preserving event and attempt history."""
    endpoint = owned_endpoint(db, endpoint_id, user)
    endpoint.is_active = False
    db.commit()


@router.get("/subscriptions/", response_model=list[SubscriptionOut], tags=["Subscriptions"])
def list_subscriptions(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100),
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(select(Subscription).join(Endpoint).where(Endpoint.owner_id == user.id)
                      .order_by(Subscription.id.desc()).offset(offset).limit(limit)).all()


@router.post("/subscriptions/", response_model=SubscriptionOut, status_code=201, tags=["Subscriptions"])
def create_subscription(data: SubscriptionCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    owned_endpoint(db, data.endpoint, user)
    subscription = Subscription(endpoint_id=data.endpoint, event_type=data.event_type)
    db.add(subscription)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "This endpoint is already subscribed to this event type") from None
    return subscription


@router.delete("/subscriptions/{subscription_id}/", status_code=204, tags=["Subscriptions"])
def delete_subscription(subscription_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    subscription = db.scalar(select(Subscription).join(Endpoint).where(Subscription.id == subscription_id, Endpoint.owner_id == user.id))
    if not subscription:
        raise HTTPException(404, "Subscription not found")
    db.delete(subscription)
    db.commit()


@router.get("/events/", response_model=list[EventOut], tags=["Events"])
def list_events(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100),
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(select(Event).where(Event.owner_id == user.id).order_by(Event.id.desc()).offset(offset).limit(limit)).all()


def existing_event(db, user, key, data):
    event = db.scalar(select(Event).where(Event.owner_id == user.id, Event.idempotency_key == key))
    if event and (event.event_type != data.event_type or json.dumps(event.payload, sort_keys=True) != json.dumps(data.payload, sort_keys=True)):
        raise HTTPException(409, "Idempotency key already used for a different event")
    return event


@router.post("/events/", response_model=EventOut, status_code=201, tags=["Events"])
def create_event(data: EventCreate, response: Response,
                 idempotency_key: str | None = Header(None, min_length=1, max_length=255),
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if idempotency_key and data.idempotency_key and idempotency_key != data.idempotency_key:
        raise HTTPException(400, "Header and body idempotency keys disagree")
    key = idempotency_key or data.idempotency_key
    if key:
        event = existing_event(db, user, key, data)
        if event:
            response.status_code = 200
            return event
    event = Event(owner_id=user.id, event_type=data.event_type, payload=data.payload, idempotency_key=key)
    db.add(event)
    deliveries = []
    try:
        db.flush()  # Allocate an event ID, but do not commit half the operation.
        endpoint_ids = db.scalars(select(Endpoint.id).join(Subscription).where(
            Endpoint.owner_id == user.id, Endpoint.is_active.is_(True), Subscription.event_type == data.event_type)).all()
        for endpoint_id in endpoint_ids:
            delivery = Delivery(event_id=event.id, endpoint_id=endpoint_id)
            db.add(delivery)
            deliveries.append(delivery)
        db.commit()  # Event + pending deliveries are saved together before queueing.
    except IntegrityError:
        db.rollback()
        if key:
            event = existing_event(db, user, key, data)
            if event:
                response.status_code = 200
                return event
        raise HTTPException(409, "Event could not be saved") from None
    for delivery in deliveries:
        enqueue_delivery(delivery.id)
    return event


@router.get("/deliveries/", response_model=list[DeliveryOut], tags=["Deliveries"])
def list_deliveries(status: str | None = Query(None, pattern="^(PENDING|SUCCESS|FAILED|DEAD_LETTERED)$"),
                    offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100),
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(Delivery).join(Event).where(Event.owner_id == user.id)
    if status:
        query = query.where(Delivery.status == status)
    return db.scalars(query.order_by(Delivery.id.desc()).offset(offset).limit(limit)).all()


@router.get("/deliveries/{delivery_id}/attempts/", response_model=list[AttemptOut], tags=["Deliveries"])
def list_attempts(delivery_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    owned_delivery(db, delivery_id, user)
    return db.scalars(select(DeliveryAttempt).where(DeliveryAttempt.delivery_id == delivery_id).order_by(DeliveryAttempt.attempt_number)).all()


def replay(db: Session, original: Delivery) -> Delivery:
    if original.status != "DEAD_LETTERED":
        raise HTTPException(409, "Replay is available after automatic retries have finished")
    if not original.endpoint.is_active:
        raise HTTPException(409, "Reactivate the endpoint before replaying")
    delivery = Delivery(event_id=original.event_id, endpoint_id=original.endpoint_id)
    db.add(delivery)
    db.commit()
    enqueue_delivery(delivery.id)
    return delivery


@router.post("/deliveries/{delivery_id}/replay/", response_model=DeliveryOut, status_code=202, tags=["Deliveries"])
def replay_delivery(delivery_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return replay(db, owned_delivery(db, delivery_id, user))
