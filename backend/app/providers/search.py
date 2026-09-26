import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.campaign_config import CampaignConfig
from app.config import settings


@dataclass
class SearchResult:
    business_name: str
    website_url: str | None
    location_country: str | None
    notes: str | None = None


class SearchProvider(ABC):
    @abstractmethod
    async def search_businesses(self, query: str, region: str, filters: dict) -> list[SearchResult]: ...


class StubSearchProvider(SearchProvider):
    async def search_businesses(self, query: str, region: str, filters: dict) -> list[SearchResult]:
        seed = str(filters.get("campaign_id", "stub"))
        digest = hashlib.sha256(f"{seed}:{query}".encode()).hexdigest()[:10]
        label = re.sub(r"\s+", " ", query).strip()[:70]
        return [SearchResult(
            business_name=f"Search prospect: {label}", website_url=f"https://prospect-{digest}.example",
            location_country=region, notes=f"Stub result generated from search pattern: {query}",
        )]


def get_search_provider() -> SearchProvider:
    if settings.search_provider != "stub":
        raise RuntimeError(f"Search provider '{settings.search_provider}' is not installed")
    return StubSearchProvider()


async def search_campaign(config: CampaignConfig) -> list[SearchResult]:
    provider = get_search_provider()
    results: list[SearchResult] = []
    patterns = config.search_patterns or [{"query": config.vertical}]
    for pattern in patterns[:5]:
        query = str(pattern.get("query") if isinstance(pattern, dict) else pattern).strip()
        if query:
            results.extend(await provider.search_businesses(query, config.region, {"campaign_id": config.id, "icp": config.icp_firmographics}))
    return results
