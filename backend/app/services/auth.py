import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.models import RefreshSession, User

# PyJWT owns LeadProphet session tokens. If this module ever adopts authlib.jose,
# migrate directly to joserfc first: https://docs.authlib.org/en/latest/upgrades/jose.html


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user: User) -> str:
    now = utcnow()
    payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.effective_jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.effective_jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "access" or not payload.get("sub"):
            raise ValueError("Invalid token type")
        return payload
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def issue_refresh_token(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(48)
    db.add(
        RefreshSession(
            user_id=user.id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=utcnow() + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    return token


def consume_refresh_token(db: Session, token: str) -> User:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    session = db.query(RefreshSession).filter(RefreshSession.token_hash == token_hash).first()
    expires_at = session.expires_at if session else None
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if not session or session.revoked_at or not expires_at or expires_at <= utcnow():
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    user = db.query(User).filter(User.id == session.user_id, User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User is inactive or unavailable")
    session.revoked_at = utcnow()
    return user


def refresh_token_user_id(db: Session, token: str) -> str | None:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    session = db.query(RefreshSession.user_id).filter(RefreshSession.token_hash == token_hash).first()
    return session[0] if session else None


def set_auth_cookies(response, access_token: str, refresh_token: str) -> None:
    secure = settings.secure_cookies
    response.set_cookie(
        "leadprophet_access",
        access_token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=secure,
        samesite=settings.cookie_samesite,
    )
    response.set_cookie(
        "leadprophet_refresh",
        refresh_token,
        max_age=settings.refresh_token_expire_days * 86400,
        httponly=True,
        secure=secure,
        samesite=settings.cookie_samesite,
    )


def clear_auth_cookies(response) -> None:
    response.delete_cookie("leadprophet_access")
    response.delete_cookie("leadprophet_refresh")


def request_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return request.cookies.get("leadprophet_access")
