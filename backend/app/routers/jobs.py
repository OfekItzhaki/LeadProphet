from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Lead, User
from app.services.ai_pipeline import LeadPipeline
from app.services.cache import cache

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("/process-new-leads")
async def process_new_leads(
    campaign_id: str | None = None,
    limit: int = Query(default=5, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    query = db.query(Lead).filter(Lead.user_id == current_user.id, Lead.status.in_(["new", "analysis_failed"]))
    if campaign_id:
        query = query.filter(Lead.campaign_id == campaign_id)
    leads = query.order_by(Lead.created_at.asc()).limit(limit).all()
    pipeline = LeadPipeline(db)
    processed: list[str] = []
    failed: dict[str, str] = {}

    for lead in leads:
        try:
            await pipeline.process_lead(lead)
            processed.append(lead.id)
        except Exception as exc:
            failed[lead.id] = str(exc)

    cache.invalidate_user(current_user.id)
    return {"processed": processed, "failed": failed}
