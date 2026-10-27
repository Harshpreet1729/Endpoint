"""Password hashing, expiring API tokens, and browser session protection."""

import base64
import hashlib
import hmac
import secrets

from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)
signer = URLSafeTimedSerializer(settings.secret_key, salt="eventgate-api-token")


def hash_password(password: str) -> str:
    # Store the algorithm, iteration count, salt, and digest for verification.
    salt = secrets.token_hex(16)
    rounds = 1_000_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), rounds)
    return f"pbkdf2_sha256${rounds}${salt}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256" or not 1 <= int(rounds) <= 10_000_000:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(rounds))
        return hmac.compare_digest(base64.b64encode(digest).decode(), expected)
    except (ValueError, TypeError):
        return False


# Use a dummy hash so unknown users still incur password-verification work.
DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.username == username))
    valid = verify_password(password, user.password_hash if user else DUMMY_HASH)
    return user if user and user.is_active and valid else None


def password_stamp(user: User) -> str:
    return hashlib.sha256(user.password_hash.encode()).hexdigest()


def create_token(user: User) -> str:
    return signer.dumps({"user_id": user.id, "stamp": password_stamp(user)})


def session_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    user = db.get(User, user_id) if isinstance(user_id, int) else None
    if user and user.is_active and request.session.get("stamp") == password_stamp(user):
        return user
    return None


def csrf_token(request: Request) -> str:
    if "csrf" not in request.session:
        request.session["csrf"] = secrets.token_urlsafe(32)
    return request.session["csrf"]


def check_csrf(request: Request, submitted: str | None):
    expected = request.session.get("csrf", "")
    if not expected or not submitted or not hmac.compare_digest(expected, submitted):
        raise HTTPException(403, "Missing or invalid CSRF token")
    origin = request.headers.get("origin")
    allowed = [str(request.base_url).rstrip("/"), *settings.csrf_origins]
    if origin and origin not in allowed:
        raise HTTPException(403, "Untrusted request origin")


def get_current_user(request: Request, token: str | None = Depends(oauth2), db: Session = Depends(get_db)) -> User:
    if token:
        try:
            data = signer.loads(token, max_age=settings.token_seconds)
            user = db.get(User, data["user_id"])
            if user and user.is_active and data["stamp"] == password_stamp(user):
                return user
        except (BadSignature, KeyError, TypeError):
            pass
    elif not request.headers.get("authorization"):
        user = session_user(request, db)
        if user:
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                check_csrf(request, request.headers.get("X-CSRF-Token"))
            return user
    raise HTTPException(401, "Log in first", headers={"WWW-Authenticate": "Bearer"})
