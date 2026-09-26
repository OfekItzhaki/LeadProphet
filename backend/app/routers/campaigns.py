from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Campaign, User
from app.schemas import CampaignCreate, CampaignRead, CampaignUpdate
from app.services.cache import cache
from app.services.events import record_event
from app.services.scoring import DEFAULT_SCORING_PROFILE
from app.campaign_config import CampaignConfig
from pydantic import ValidationError

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


def validate_campaign(campaign: Campaign) -> None:
    try:
        CampaignConfig.from_campaign(campaign)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid campaign configuration: {exc.errors()[0]['msg']}") from exc


@router.get("", response_model=list[CampaignRead])
def list_campaigns(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[Campaign]:
    key = cache.key(current_user.id, "campaigns", "list")
    return cache.get_or_set(
        key, lambda: db.query(Campaign).filter(Campaign.user_id == current_user.id).order_by(Campaign.created_at.desc()).all()
    )


@router.post("", response_model=CampaignRead)
def create_campaign(payload: CampaignCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Campaign:
    campaign = Campaign(user_id=current_user.id, **payload.model_dump())
    db.add(campaign)
    db.flush()
    validate_campaign(campaign)
    record_event(db, "campaign_created", user=current_user, campaign=campaign)
    db.commit()
    db.refresh(campaign)
    cache.invalidate_user(current_user.id)
    return campaign


@router.get("/{campaign_id}", response_model=CampaignRead)
def get_campaign(campaign_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Campaign:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == current_user.id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.patch("/{campaign_id}", response_model=CampaignRead)
def update_campaign(campaign_id: str, payload: CampaignUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Campaign:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == current_user.id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(campaign, key, value)
    validate_campaign(campaign)
    record_event(db, "campaign_updated", user=current_user, campaign=campaign)
    db.commit()
    db.refresh(campaign)
    cache.invalidate_user(current_user.id)
    return campaign


@router.put("/{campaign_id}", response_model=CampaignRead)
def replace_campaign(campaign_id: str, payload: CampaignCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Campaign:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == current_user.id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    for key, value in payload.model_dump().items():
        setattr(campaign, key, value)
    validate_campaign(campaign)
    record_event(db, "campaign_updated", user=current_user, campaign=campaign)
    db.commit()
    db.refresh(campaign)
    cache.invalidate_user(current_user.id)
    return campaign


@router.delete("/{campaign_id}", status_code=204)
def delete_campaign(campaign_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> None:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == current_user.id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.is_active = False
    record_event(db, "campaign_deactivated", user=current_user, campaign=campaign)
    db.commit()
    cache.invalidate_user(current_user.id)


@router.post("/seed-default", response_model=CampaignRead)
def seed_default_campaign(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Campaign:
    existing = db.query(Campaign).filter(Campaign.user_id == current_user.id, Campaign.name == "Web/App & AI Automation - Israel SMBs").first()
    if existing:
        return existing

    campaign = Campaign(
        user_id=current_user.id,
        name="Web/App & AI Automation - Israel SMBs",
        vertical="small and mid-sized businesses",
        region="Israel",
        languages=["he", "en"],
        services_offered=["web_app_rebuild", "ai_automation", "mvp_build"],
        search_patterns=[
            {"query": "site:.co.il עסקים קטנים אתר מיושן"},
            {"query": "Israel startup MVP development needed"},
        ],
        lead_sources_enabled={"web_search": False, "directories": False, "freelance": False, "manual_import": True},
        ai_icp_description=(
            "Israeli SMBs, founders, and service businesses whose website or operational workflow is holding back "
            "lead capture, trust, or speed."
        ),
        ai_value_proposition=(
            "modern web apps, practical AI automations, and MVP builds that create more qualified leads and reduce manual work"
        ),
        ai_tone_guidelines="Warm, specific, direct, low-pressure, and useful. Avoid hype and spam language.",
        scoring_profile=DEFAULT_SCORING_PROFILE,
        icp_firmographics={
            "company_sizes": ["small_business", "mid_market"],
            "industries": ["service businesses", "startups"],
            "regions": ["Israel"],
        },
        icp_technographics={"technologies": ["wordpress", "wix", "custom_web"]},
        icp_pains=["weak lead capture", "manual workflows", "outdated website"],
        icp_triggers=["hiring", "new product", "site redesign"],
        icp_personas=["Founder", "CTO", "Marketing lead", "Business owner"],
        is_active=True,
    )
    db.add(campaign)
    db.flush()
    validate_campaign(campaign)
    record_event(db, "campaign_created", user=current_user, campaign=campaign, details={"seeded": True})
    db.commit()
    db.refresh(campaign)
    cache.invalidate_user(current_user.id)
    return campaign
