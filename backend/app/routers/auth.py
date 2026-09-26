import logging
from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.dependencies import get_current_user
from app.models import RefreshSession, User
from app.schemas import RefreshRequest, TokenResponse, UserRead
from app.services.auth import (
    clear_auth_cookies,
    create_access_token,
    issue_refresh_token,
    consume_refresh_token,
    refresh_token_user_id,
    set_auth_cookies,
)
from app.services.users import upsert_google_user
from app.services.events import record_event
from app.services.test_support import create_second_test_user_if_not_exists, create_test_user_if_not_exists

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
oauth = OAuth()
oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    client_kwargs={"scope": "openid email profile"},
)


def _require_google_config() -> None:
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")


@router.get("/google/login")
async def google_login(request: Request):
    _require_google_config()
    return await oauth.google.authorize_redirect(request, settings.google_redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    _require_google_config()
    try:
        token = await oauth.google.authorize_access_token(request)
        identity = token.get("userinfo") or await oauth.google.userinfo(token=token)
    except OAuthError as exc:
        logger.warning("Google authentication failed: %s", exc.error)
        record_event(db, "login_failed", details={"provider": "google", "reason": str(exc.error)[:200]})
        db.commit()
        raise HTTPException(status_code=401, detail="Google authentication failed") from exc
    except Exception as exc:
        logger.exception("Unexpected Google authentication error")
        record_event(db, "login_failed", details={"provider": "google", "reason": "provider_unavailable"})
        db.commit()
        raise HTTPException(status_code=502, detail="Google authentication is temporarily unavailable") from exc

    try:
        user = upsert_google_user(db, identity)
    except HTTPException as exc:
        record_event(db, "login_failed", details={"provider": "google", "reason": str(exc.detail)[:200]})
        db.commit()
        raise
    access_token = create_access_token(user)
    refresh_token = issue_refresh_token(db, user)
    record_event(db, "login", user=user, details={"provider": "google"})
    db.commit()
    logger.info("User signed in: user_id=%s", user.id)

    response = RedirectResponse("/daily", status_code=303)
    set_auth_cookies(response, access_token, refresh_token)
    return response


@router.post("/refresh", response_model=TokenResponse)
def refresh_tokens(request: Request, payload: RefreshRequest | None = None, db: Session = Depends(get_db)):
    refresh_token = (payload.refresh_token if payload else None) or request.cookies.get("leadprophet_refresh")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token required")
    refresh_user_id = refresh_token_user_id(db, refresh_token)
    try:
        user = consume_refresh_token(db, refresh_token)
    except HTTPException:
        logger.warning("Refresh token rejected")
        record_event(db, "refresh_failed", user_id=refresh_user_id, details={"reason": "invalid_or_expired"})
        db.commit()
        raise
    access_token = create_access_token(user)
    next_refresh_token = issue_refresh_token(db, user)
    db.commit()
    logger.info("Session refreshed: user_id=%s", user.id)
    response = JSONResponse(
        TokenResponse(
            access_token=access_token,
            refresh_token=next_refresh_token,
            expires_in=settings.access_token_expire_minutes * 60,
            user=user,
        ).model_dump(mode="json")
    )
    set_auth_cookies(response, access_token, next_refresh_token)
    return response


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("leadprophet_refresh")
    if token:
        try:
            user = consume_refresh_token(db, token)
            record_event(db, "logout", user=user)
            db.commit()
        except HTTPException:
            db.rollback()
    response = JSONResponse({"status": "logged_out"})
    clear_auth_cookies(response)
    return response


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/dev/test-login", response_model=TokenResponse, include_in_schema=False)
def test_login(user: str = "primary", db: Session = Depends(get_db)):
    if settings.app_env.lower() not in {"local", "development", "test"}:
        raise HTTPException(status_code=404, detail="Not found")
    test_user = create_second_test_user_if_not_exists(db) if user == "second" else create_test_user_if_not_exists(db)
    access_token = create_access_token(test_user)
    refresh_token = issue_refresh_token(db, test_user)
    record_event(db, "login", user=test_user, details={"provider": "test_only"})
    db.commit()
    response = JSONResponse(TokenResponse(
        access_token=access_token, refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60, user=test_user,
    ).model_dump(mode="json"))
    set_auth_cookies(response, access_token, refresh_token)
    return response


@router.post("/dev/reset", include_in_schema=False)
def reset_test_state():
    if settings.app_env.lower() != "test":
        raise HTTPException(status_code=404, detail="Not found")
    from app.services.e2e_seed import reset_e2e_database
    reset_e2e_database()
    return {"status": "reset"}
