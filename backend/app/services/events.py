import logging

from sqlalchemy.orm import Session

from app.models import Campaign, Event, Lead, User

logger = logging.getLogger("leadprophet.events")


def record_event(
    db: Session,
    event_type: str,
    *,
    user: User | None = None,
    user_id: str | None = None,
    campaign: Campaign | None = None,
    lead: Lead | None = None,
    details: dict | None = None,
) -> Event:
    event = Event(
        user_id=user.id if user else user_id,
        campaign_id=campaign.id if campaign else (lead.campaign_id if lead else None),
        lead_id=lead.id if lead else None,
        event_type=event_type,
        details=details or {},
    )
    db.add(event)
    logger.info(
        "event=%s user_id=%s campaign_id=%s lead_id=%s",
        event_type,
        event.user_id,
        event.campaign_id,
        event.lead_id,
    )
    return event
