from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Campaign, Event, User
from app.schemas import EventRead

router = APIRouter(prefix="/events", tags=["events"])


def validate_campaign(db: Session, campaign_id: str | None, user_id: str) -> None:
    if campaign_id and not db.query(Campaign.id).filter(
        Campaign.id == campaign_id, Campaign.user_id == user_id
    ).first():
        raise HTTPException(status_code=404, detail="Campaign not found")


@router.get("/recent", response_model=list[EventRead])
def recent_events(
    campaign_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Event]:
    validate_campaign(db, campaign_id, current_user.id)
    query = db.query(Event).filter(Event.user_id == current_user.id)
    if campaign_id:
        query = query.filter(Event.campaign_id == campaign_id)
    return query.order_by(Event.created_at.desc()).limit(limit).all()


@router.get("/stats")
def event_stats(
    campaign_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    validate_campaign(db, campaign_id, current_user.id)
    query = db.query(Event.event_type, func.count(Event.id)).filter(Event.user_id == current_user.id)
    if campaign_id:
        query = query.filter(Event.campaign_id == campaign_id)
    counts = {event_type: count for event_type, count in query.group_by(Event.event_type).all()}
    return {"campaign_id": campaign_id, "counts": counts, "total": sum(counts.values())}
