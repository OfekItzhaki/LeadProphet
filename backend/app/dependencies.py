from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.services.auth import decode_access_token, request_token


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = decode_access_token(token)
    user = db.query(User).filter(User.id == payload["sub"], User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User is inactive or unavailable")
    return user


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request_token(request)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except HTTPException:
        return None
    return db.query(User).filter(User.id == payload["sub"], User.is_active.is_(True)).first()
