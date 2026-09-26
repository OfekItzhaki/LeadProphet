from sqlalchemy.orm import Session

from app.models import Campaign, Lead, User
from app.schemas import ImportedLeadRow
from app.services.deduplication import find_duplicate
from app.services.enrichment import enrich_lead
from app.services.events import record_event


SOURCE_EVENTS = {
    "manual_csv": "lead_imported_csv",
    "search_stub": "lead_discovered_stub",
}


class LeadCreationService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, candidate: ImportedLeadRow, campaign: Campaign, user: User, source_type: str) -> Lead:
        duplicate, reason = find_duplicate(self.db, user.id, campaign.id, candidate)
        enrichment = enrich_lead(candidate)
        if reason:
            enrichment["duplicate_match_reason"] = reason
        lead = Lead(
            user_id=user.id,
            campaign_id=campaign.id,
            duplicate_of_id=duplicate.id if duplicate else None,
            source_type=source_type,
            business_name=candidate.business_name,
            website_url=candidate.website_url,
            contact_email=candidate.contact_email,
            contact_phone=candidate.contact_phone,
            location_city=candidate.location_city,
            location_country=candidate.location_country,
            raw_source_reference={"notes": candidate.notes} if candidate.notes else None,
            enrichment=enrichment,
            status="duplicate" if duplicate else "new",
        )
        self.db.add(lead)
        self.db.flush()
        details = {"source_type": source_type}
        if duplicate:
            details.update({"duplicate_of_id": duplicate.id, "match_reason": reason})
        record_event(self.db, "lead_created", user=user, campaign=campaign, lead=lead, details=details)
        source_event = SOURCE_EVENTS.get(source_type)
        if source_event:
            record_event(self.db, source_event, user=user, campaign=campaign, lead=lead, details=details)
        return lead
