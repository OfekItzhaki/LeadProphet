from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Campaign, Lead, OutreachMessage, User
from app.schemas import ImportedLeadRow, LeadCreate, LeadRead, LeadUpdate
from app.services.ai_pipeline import LeadPipeline
from app.services.cache import cache
from app.services.lead_creation import LeadCreationService
from app.services.events import record_event

router = APIRouter(prefix="/api/leads", tags=["leads"])


@router.get("", response_model=list[LeadRead])
def list_leads(
    campaign_id: str | None = None,
    status: str | None = None,
    min_score: int | None = Query(default=None, ge=0, le=100),
    max_score: int | None = Query(default=None, ge=0, le=100),
    priority: str | None = None,
    pipeline_stage: str | None = None,
    view: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Lead]:
    query = db.query(Lead).options(selectinload(Lead.outreach_messages)).filter(Lead.user_id == current_user.id)
    if campaign_id:
        query = query.filter(Lead.campaign_id == campaign_id)
    if status:
        query = query.filter(Lead.status == status)
    if min_score is not None:
        query = query.filter(Lead.score >= min_score)
    if max_score is not None:
        query = query.filter(Lead.score <= max_score)
    if priority:
        query = query.filter(Lead.priority == priority)
    if pipeline_stage:
        query = query.filter(Lead.pipeline_stage == pipeline_stage)
    if view == "high_priority":
        query = query.filter(Lead.priority == "high", Lead.duplicate_of_id.is_(None))
    elif view == "needs_outreach":
        query = query.filter(Lead.status == "contact_draft_ready", Lead.duplicate_of_id.is_(None))
    elif view == "duplicates":
        query = query.filter(Lead.duplicate_of_id.is_not(None))
    elif view == "failed_analysis":
        query = query.filter(Lead.status == "analysis_failed")
    elif view == "needs_follow_up":
        query = query.filter(Lead.outreach_messages.any(OutreachMessage.follow_up_due_at.is_not(None)))
    suffix = f"campaign={campaign_id}:status={status}:min={min_score}:max={max_score}:priority={priority}:stage={pipeline_stage}:view={view}"
    key = cache.key(current_user.id, "leads", suffix)
    return cache.get_or_set(
        key, lambda: query.order_by(Lead.score.desc().nullslast(), Lead.created_at.desc()).all()
    )


@router.post("", response_model=LeadRead)
def create_lead(payload: LeadCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Lead:
    campaign = db.query(Campaign).filter(Campaign.id == payload.campaign_id, Campaign.user_id == current_user.id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    candidate = ImportedLeadRow(
        business_name=payload.business_name,
        website_url=payload.website_url,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
        location_city=payload.location_city,
        location_country=payload.location_country,
        notes=payload.rough_notes,
    )
    lead = LeadCreationService(db).create(candidate, campaign, current_user, payload.source_type)
    db.commit()
    db.refresh(lead)
    cache.invalidate_user(current_user.id)
    return lead


@router.get("/{lead_id}", response_model=LeadRead)
def get_lead(lead_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Lead:
    lead = db.query(Lead).options(selectinload(Lead.outreach_messages)).filter(Lead.id == lead_id, Lead.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.patch("/{lead_id}", response_model=LeadRead)
def update_lead(lead_id: str, payload: LeadUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Lead:
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    previous_status = lead.status
    for key, value in payload.model_dump(exclude_unset=True, exclude={"notes"}).items():
        setattr(lead, key, value)
    if lead.status != previous_status:
        record_event(
            db, "status_changed", user=current_user, lead=lead,
            details={"from": previous_status, "to": lead.status},
        )
    db.commit()
    db.refresh(lead)
    cache.invalidate_user(current_user.id)
    return lead


@router.delete("/{lead_id}", status_code=204)
def delete_lead(lead_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> None:
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    db.delete(lead)
    db.commit()
    cache.invalidate_user(current_user.id)


@router.post("/{lead_id}/analyze", response_model=LeadRead)
async def analyze_lead(lead_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Lead:
    lead = db.query(Lead).options(selectinload(Lead.outreach_messages)).filter(Lead.id == lead_id, Lead.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if lead.duplicate_of_id:
        raise HTTPException(status_code=409, detail="Analyze the canonical lead instead of its duplicate")
    result = await LeadPipeline(db).process_lead(lead)
    cache.invalidate_user(current_user.id)
    return result
