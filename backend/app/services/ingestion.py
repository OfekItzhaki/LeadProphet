from sqlalchemy.orm import Session

from app.models import Campaign, Lead, User
from app.schemas import ImportedLeadRow, ImportErrorDetail, IngestionSummary
from app.services.cache import cache
from app.services.lead_creation import LeadCreationService
from app.services.lead_sources import LeadSource
from app.services.ai_pipeline import LeadPipeline


class LeadIngestionService:
    def __init__(self, db: Session):
        self.db = db

    async def ingest(
        self, source: LeadSource, campaign: Campaign, user: User, *, analyze: bool = False
    ) -> IngestionSummary:
        candidates, errors = source.collect()
        created: list[Lead] = []
        creator = LeadCreationService(self.db)
        for candidate in candidates:
            created.append(creator.create(candidate, campaign, user, source.source_type))
        self.db.commit()
        if analyze:
            pipeline = LeadPipeline(self.db)
            for index, lead in enumerate(created, start=2):
                if lead.status == "duplicate":
                    continue
                try:
                    await pipeline.process_lead(lead)
                except Exception as exc:
                    errors.append(ImportErrorDetail(row=index, reason=f"Analysis failed: {str(exc)[:300]}"))
        cache.invalidate_user(user.id)
        return IngestionSummary(
            created=len(created),
            skipped=len(errors),
            duplicates=sum(lead.status == "duplicate" for lead in created),
            queued_for_analysis=0 if analyze else sum(lead.status == "new" for lead in created),
            lead_ids=[lead.id for lead in created],
            errors=errors,
        )
