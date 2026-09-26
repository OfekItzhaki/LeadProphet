from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Campaign, Lead, User
from app.schemas import LeadBulkAction
from app.services.ai_pipeline import LeadPipeline
from app.services.cache import cache
from app.services.events import record_event

router = APIRouter(tags=["lead quality"])


def owned_campaign(db: Session, campaign_id: str, user_id: str) -> Campaign:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == user_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def lead_summary(lead: Lead) -> dict:
    return {
        "id": lead.id,
        "business_name": lead.business_name,
        "website_url": lead.website_url,
        "location_city": lead.location_city,
        "location_country": lead.location_country,
        "status": lead.status,
        "score": lead.score,
        "duplicate_of_id": lead.duplicate_of_id,
        "match_reason": (lead.enrichment or {}).get("duplicate_match_reason"),
    }


@router.get("/campaigns/{campaign_id}/duplicates")
def duplicate_clusters(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    owned_campaign(db, campaign_id, current_user.id)
    duplicates = db.query(Lead).filter(
        Lead.user_id == current_user.id,
        Lead.campaign_id == campaign_id,
        Lead.duplicate_of_id.is_not(None),
    ).order_by(Lead.created_at.desc()).all()
    canonical_ids = {lead.duplicate_of_id for lead in duplicates}
    canonicals = db.query(Lead).filter(
        Lead.user_id == current_user.id, Lead.id.in_(canonical_ids)
    ).all() if canonical_ids else []
    clusters = []
    for canonical in canonicals:
        clusters.append({
            "canonical": lead_summary(canonical),
            "duplicates": [lead_summary(lead) for lead in duplicates if lead.duplicate_of_id == canonical.id],
        })
    return {"campaign_id": campaign_id, "cluster_count": len(clusters), "clusters": clusters}


@router.post("/campaigns/{campaign_id}/leads/analyze-new")
async def analyze_new_leads(
    campaign_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    owned_campaign(db, campaign_id, current_user.id)
    leads = db.query(Lead).filter(
        Lead.user_id == current_user.id,
        Lead.campaign_id == campaign_id,
        Lead.status.in_(["new", "analysis_failed"]),
        Lead.duplicate_of_id.is_(None),
    ).order_by(Lead.created_at.asc()).limit(limit).all()
    processed: list[str] = []
    failed: dict[str, str] = {}
    pipeline = LeadPipeline(db)
    for lead in leads:
        try:
            await pipeline.process_lead(lead)
            processed.append(lead.id)
        except Exception as exc:
            failed[lead.id] = str(exc)
    cache.invalidate_user(current_user.id)
    return {"processed": processed, "failed": failed}


@router.post("/campaigns/{campaign_id}/leads/mark-contacted")
def mark_leads_contacted(
    campaign_id: str,
    payload: LeadBulkAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    campaign = owned_campaign(db, campaign_id, current_user.id)
    unique_ids = set(payload.lead_ids)
    leads = db.query(Lead).filter(
        Lead.user_id == current_user.id,
        Lead.campaign_id == campaign_id,
        Lead.id.in_(unique_ids),
    ).all()
    if len(leads) != len(unique_ids):
        raise HTTPException(status_code=404, detail="One or more leads were not found")
    for lead in leads:
        previous = lead.status
        lead.status = "contacted"
        if previous != "contacted":
            record_event(
                db, "status_changed", user=current_user, campaign=campaign, lead=lead,
                details={"from": previous, "to": "contacted", "bulk": True},
            )
    db.commit()
    cache.invalidate_user(current_user.id)
    return {"updated": len(leads), "status": "contacted"}
