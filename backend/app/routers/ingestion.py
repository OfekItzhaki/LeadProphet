from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Campaign, User
from app.schemas import IngestionSummary
from app.services.ingestion import LeadIngestionService
from app.services.lead_sources import CsvLeadSource, ProviderSearchLeadSource
from app.campaign_config import CampaignConfig
from app.providers.search import search_campaign

router = APIRouter(tags=["ingestion"])
MAX_CSV_BYTES = 2 * 1024 * 1024


def owned_campaign(db: Session, campaign_id: str, user_id: str) -> Campaign:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == user_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.post("/campaigns/{campaign_id}/leads/import-csv", response_model=IngestionSummary)
@router.post("/api/campaigns/{campaign_id}/leads/import-csv", response_model=IngestionSummary, include_in_schema=False)
async def import_csv(
    campaign_id: str,
    file: UploadFile = File(...),
    analyze: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IngestionSummary:
    campaign = owned_campaign(db, campaign_id, current_user.id)
    content = await file.read(MAX_CSV_BYTES + 1)
    if len(content) > MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="CSV file exceeds the 2 MB limit")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="CSV must be UTF-8 encoded") from exc
    return await LeadIngestionService(db).ingest(CsvLeadSource(text), campaign, current_user, analyze=analyze)


@router.post("/campaigns/{campaign_id}/leads/discover-from-search", response_model=IngestionSummary)
@router.post(
    "/api/campaigns/{campaign_id}/leads/discover-from-search",
    response_model=IngestionSummary,
    include_in_schema=False,
)
async def discover_from_search(
    campaign_id: str,
    analyze: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IngestionSummary:
    campaign = owned_campaign(db, campaign_id, current_user.id)
    config = CampaignConfig.load(db, campaign)
    results = await search_campaign(config)
    return await LeadIngestionService(db).ingest(ProviderSearchLeadSource(results), campaign, current_user, analyze=analyze)
