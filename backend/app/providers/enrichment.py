from abc import ABC, abstractmethod

from app.config import settings
from app.schemas import ImportedLeadRow
from app.services.enrichment import InternalEnrichmentProvider


class EnrichmentProvider(ABC):
    @abstractmethod
    async def enrich_lead(self, lead: ImportedLeadRow) -> dict: ...

    @abstractmethod
    def enrich_now(self, lead: ImportedLeadRow) -> dict: ...


class InternalProviderAdapter(EnrichmentProvider):
    async def enrich_lead(self, lead: ImportedLeadRow) -> dict:
        return self.enrich_now(lead)

    def enrich_now(self, lead: ImportedLeadRow) -> dict:
        return InternalEnrichmentProvider().enrich(lead)


def get_enrichment_provider() -> EnrichmentProvider:
    if settings.enrichment_provider != "internal":
        raise RuntimeError(f"Enrichment provider '{settings.enrichment_provider}' is not installed")
    return InternalProviderAdapter()
