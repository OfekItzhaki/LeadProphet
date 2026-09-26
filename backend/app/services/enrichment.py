import re
from abc import ABC, abstractmethod
from urllib.parse import urlparse

from app.schemas import ImportedLeadRow


class EnrichmentProvider(ABC):
    @abstractmethod
    def enrich(self, lead: ImportedLeadRow) -> dict:
        raise NotImplementedError


class InternalEnrichmentProvider(EnrichmentProvider):
    LARGE_ORG_TERMS = {"group", "holdings", "international", "global", "corporation", "corp", "ltd", "inc"}
    SMALL_BUSINESS_TERMS = {"studio", "cafe", "bakery", "clinic", "salon", "shop", "local", "family"}

    def enrich(self, lead: ImportedLeadRow) -> dict:
        normalized_url = lead.website_url or ""
        if normalized_url and not normalized_url.startswith(("http://", "https://")):
            normalized_url = f"https://{normalized_url}"
        parsed = urlparse(normalized_url)
        domain = (parsed.hostname or "").lower().removeprefix("www.")
        tld = domain.rsplit(".", 1)[-1] if "." in domain else None
        name_tokens = set(re.findall(r"[a-z0-9]+", lead.business_name.lower()))
        if name_tokens & self.LARGE_ORG_TERMS:
            size = "larger_org"
            confidence = 0.7
        elif name_tokens & self.SMALL_BUSINESS_TERMS or len(lead.business_name) <= 24:
            size = "small_business"
            confidence = 0.65
        else:
            size = "unknown"
            confidence = 0.35
        domain_keywords = [token for token in re.split(r"[-.]", domain) if len(token) >= 4]
        return {
            "domain": domain or None,
            "tld": tld,
            "domain_length": len(domain) if domain else None,
            "domain_keywords": domain_keywords[:8],
            "uses_country_tld": bool(tld and len(tld) == 2),
            "inferred_business_size": size,
            "business_size_confidence": confidence,
            "has_contact_email": bool(lead.contact_email),
            "has_contact_phone": bool(lead.contact_phone),
            "provider": "internal_v1",
        }


def enrich_lead(lead: ImportedLeadRow) -> dict:
    from app.providers.enrichment import get_enrichment_provider

    return get_enrichment_provider().enrich_now(lead)
