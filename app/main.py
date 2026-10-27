"""Application entry point: uvicorn app.main:app --reload."""

from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import api, web
from app.config import settings
from app.database import get_db

app = FastAPI(title="EventGate", description="Signed webhook delivery with retries and replay.", version="2.0.0")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, session_cookie="eventgate_session",
                   max_age=settings.token_seconds, same_site="lax", https_only=not settings.debug)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.url.path.startswith(("/api", "/dashboard")):
        response.headers["Cache-Control"] = "no-store"
    if not settings.debug and request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=3600"
    return response


@app.get("/health/", tags=["Health"])
def health(db: Session = Depends(get_db)):
    # Railway probes over HTTP; this route has no auth or redirect.
    db.execute(text("SELECT 1 FROM eg_users LIMIT 1"))
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.include_router(api.router)
app.include_router(web.router)
