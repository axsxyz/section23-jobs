from __future__ import annotations

import uuid
from datetime import datetime, timezone

import bcrypt as _bcrypt
from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select, update

from job_aggregator.config import settings
from job_aggregator.db.engine import async_session
from job_aggregator.db.models import User

COOKIE_NAME = "s23_session"
MAX_AGE = 60 * 60 * 24 * 7  # 7 days

def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.webapp_secret)


def create_session_cookie(user_id: uuid.UUID) -> str:
    """Sign a session cookie payload containing the user's UUID."""
    return _serializer().dumps(str(user_id))


def _decode_cookie(token: str) -> str | None:
    """Decode and verify a signed cookie. Returns the raw payload string or None."""
    try:
        return _serializer().loads(token, max_age=MAX_AGE)
    except BadSignature:
        return None


async def _resolve_user(request: Request) -> User | None:
    """Extract and validate the session cookie, returning the active User or None."""
    token = request.cookies.get(COOKIE_NAME, "")
    if not token:
        return None
    payload = _decode_cookie(token)
    if not payload:
        return None
    try:
        user_id = uuid.UUID(payload)
    except ValueError:
        # Old cookies (pre-user-auth) stored "authenticated" — treat as invalid
        return None
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.id == user_id, User.is_active == True)  # noqa: E712
        )
        return result.scalar_one_or_none()


async def require_auth_api(request: Request) -> User:
    """Dependency for JSON API routes — returns the authenticated User or raises 401."""
    user = await _resolve_user(request)
    if user:
        return user
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
    )


async def require_auth_page(request: Request) -> User:
    """Dependency for HTML page routes — returns the authenticated User or redirects to /login."""
    user = await _resolve_user(request)
    if user:
        return user
    raise HTTPException(
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        headers={"Location": "/login"},
    )


async def require_admin(user: User = Depends(require_auth_api)) -> User:
    """Dependency that requires an authenticated admin user."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )
    return user


async def touch_last_login(user_id: uuid.UUID) -> None:
    """Update last_login_at for the given user (fire-and-forget on login)."""
    async with async_session() as session:
        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(last_login_at=datetime.now(timezone.utc))
        )
        await session.commit()
