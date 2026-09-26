from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Campaign, User
from app.services.metrics import campaign_metrics, user_metrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics/summary")
@router.get("/api/metrics/summary", include_in_schema=False)
def metrics_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict:
    return user_metrics(db, current_user.id)


@router.get("/campaigns/{campaign_id}/metrics")
@router.get("/api/campaigns/{campaign_id}/metrics", include_in_schema=False)
def metrics_for_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == current_user.id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    result = campaign_metrics(db, current_user.id, campaign.id)
    result.update({"name": campaign.name, "active": campaign.is_active})
    return result
