"""Login forms and the existing dashboard, rendered with Jinja templates."""

import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api import owned_delivery, replay
from app.database import get_db
from app.models import Delivery, Endpoint, Event
from app.security import authenticate, check_csrf, csrf_token, password_stamp, session_user

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@router.get("/")
def home():
    return RedirectResponse("/api/dashboard/", status_code=303)


@router.get("/api-auth/login/")
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"csrf": csrf_token(request), "error": None})


@router.post("/api-auth/login/")
def login_submit(request: Request, username: str = Form(..., max_length=150), password: str = Form(..., max_length=1024),
                 csrf: str = Form(...), db: Session = Depends(get_db)):
    check_csrf(request, csrf)
    user = authenticate(db, username, password)
    if not user:
        return templates.TemplateResponse(request=request, name="login.html", status_code=401,
                                           context={"csrf": csrf_token(request), "error": "Invalid username or password"})
    request.session.clear()
    request.session.update(user_id=user.id, stamp=password_stamp(user), csrf=secrets.token_urlsafe(32))
    return RedirectResponse("/api/dashboard/", status_code=303)


@router.post("/api-auth/logout/")
def logout(request: Request, csrf: str = Form(...)):
    check_csrf(request, csrf)
    request.session.clear()
    return RedirectResponse("/api-auth/login/", status_code=303)


@router.get("/api/dashboard/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = session_user(request, db)
    if not user:
        return RedirectResponse("/api-auth/login/", status_code=303)
    statuses = dict(db.execute(select(Delivery.status, func.count(Delivery.id)).join(Event)
                               .where(Event.owner_id == user.id).group_by(Delivery.status)).all())
    context = {
        "username": user.username, "csrf": csrf_token(request),
        "endpoint_count": db.scalar(select(func.count(Endpoint.id)).where(Endpoint.owner_id == user.id)),
        "event_count": db.scalar(select(func.count(Event.id)).where(Event.owner_id == user.id)),
        "success_count": statuses.get("SUCCESS", 0), "failed_count": statuses.get("FAILED", 0),
        "dead_letter_count": statuses.get("DEAD_LETTERED", 0),
        "recent_deliveries": db.scalars(select(Delivery).join(Event).where(Event.owner_id == user.id)
                                        .options(joinedload(Delivery.event), joinedload(Delivery.endpoint))
                                        .order_by(Delivery.id.desc()).limit(20)).all(),
        "endpoints": db.scalars(select(Endpoint).where(Endpoint.owner_id == user.id).order_by(Endpoint.id).limit(100)).all(),
    }
    return templates.TemplateResponse(request=request, name="dashboard.html", context=context)


@router.post("/dashboard/deliveries/{delivery_id}/replay/")
def replay_form(request: Request, delivery_id: int, csrf: str = Form(...), db: Session = Depends(get_db)):
    user = session_user(request, db)
    if not user:
        return RedirectResponse("/api-auth/login/", status_code=303)
    check_csrf(request, csrf)
    replay(db, owned_delivery(db, delivery_id, user))
    return RedirectResponse("/api/dashboard/", status_code=303)
