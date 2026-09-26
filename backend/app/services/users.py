from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import User


def upsert_google_user(db: Session, identity: dict) -> User:
    email = str(identity.get("email", "")).strip().lower()
    subject = str(identity.get("sub", "")).strip()
    if not email or not subject or identity.get("email_verified") is not True:
        raise HTTPException(status_code=401, detail="A verified Google identity is required")

    by_subject = db.query(User).filter(User.google_subject == subject).first()
    by_email = db.query(User).filter(User.email == email).first()
    if by_subject and by_email and by_subject.id != by_email.id:
        raise HTTPException(status_code=409, detail="Google identity conflicts with an existing account")

    user = by_subject or by_email
    if not user:
        user = User(email=email, display_name=identity.get("name") or email, role="owner")
        db.add(user)
    user.email = email
    user.google_subject = subject
    user.display_name = identity.get("name") or user.display_name
    user.avatar_url = identity.get("picture")
    user.last_login_at = datetime.now(timezone.utc)
    db.flush()
    return user
