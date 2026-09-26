import re
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models import Lead
from app.schemas import ImportedLeadRow


def normalize_domain(url: str | None) -> str | None:
    if not url:
        return None
    value = url.strip().lower()
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    return (urlparse(value).hostname or "").removeprefix("www.") or None


def normalize_text(value: str | None) -> str:
    return re.sub(r"[^a-z0-9\u0590-\u05ff]+", "", (value or "").casefold())


def duplicate_reason(existing: Lead, candidate: ImportedLeadRow) -> str | None:
    existing_domain = normalize_domain(existing.website_url)
    candidate_domain = normalize_domain(candidate.website_url)
    if existing_domain and candidate_domain and existing_domain == candidate_domain:
        return "website_domain"
    if existing.contact_email and candidate.contact_email and existing.contact_email.casefold() == candidate.contact_email.casefold():
        return "contact_email"
    same_name = normalize_text(existing.business_name) == normalize_text(candidate.business_name)
    existing_location = normalize_text(f"{existing.location_city or ''}{existing.location_country or ''}")
    candidate_location = normalize_text(f"{candidate.location_city or ''}{candidate.location_country or ''}")
    if same_name and existing_location and existing_location == candidate_location:
        return "business_name_location"
    return None


def find_duplicate(
    db: Session, user_id: str, campaign_id: str, candidate: ImportedLeadRow
) -> tuple[Lead | None, str | None]:
    existing_leads = db.query(Lead).filter(
        Lead.user_id == user_id,
        Lead.campaign_id == campaign_id,
        Lead.duplicate_of_id.is_(None),
    ).all()
    for existing in existing_leads:
        reason = duplicate_reason(existing, candidate)
        if reason:
            return existing, reason
    return None, None
