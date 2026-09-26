import csv
import hashlib
import io
import re
from abc import ABC, abstractmethod

from pydantic import ValidationError

from app.campaign_config import CampaignConfig
from app.models import Campaign
from app.schemas import ImportedLeadRow, ImportErrorDetail


class LeadSource(ABC):
    source_type: str

    @abstractmethod
    def collect(self) -> tuple[list[ImportedLeadRow], list[ImportErrorDetail]]:
        raise NotImplementedError


class CsvLeadSource(LeadSource):
    source_type = "manual_csv"
    allowed_columns = set(ImportedLeadRow.model_fields)

    def __init__(self, content: str):
        self.content = content

    def collect(self) -> tuple[list[ImportedLeadRow], list[ImportErrorDetail]]:
        reader = csv.DictReader(io.StringIO(self.content))
        if not reader.fieldnames or "business_name" not in reader.fieldnames:
            return [], [ImportErrorDetail(row=1, reason="CSV must include a business_name column")]
        rows: list[ImportedLeadRow] = []
        errors: list[ImportErrorDetail] = []
        for row_number, raw in enumerate(reader, start=2):
            try:
                data = {key: value for key, value in raw.items() if key in self.allowed_columns}
                rows.append(ImportedLeadRow.model_validate(data))
            except ValidationError as exc:
                errors.append(ImportErrorDetail(row=row_number, reason=exc.errors()[0]["msg"]))
        return rows, errors


class SearchLeadSource(LeadSource):
    """Deterministic adapter stub. Replace collect() with a search API adapter later."""

    source_type = "search_stub"

    def __init__(self, campaign: Campaign, config: CampaignConfig | None = None):
        self.campaign = campaign
        self.config = config or CampaignConfig.from_campaign(campaign)

    def collect(self) -> tuple[list[ImportedLeadRow], list[ImportErrorDetail]]:
        # TODO(search-api): select a provider adapter from settings when credentials are configured.
        patterns = self.config.search_patterns or [{"query": self.config.vertical}]
        leads: list[ImportedLeadRow] = []
        for index, pattern in enumerate(patterns[:5], start=1):
            query = str(pattern.get("query") if isinstance(pattern, dict) else pattern).strip()
            if not query:
                continue
            digest = hashlib.sha256(f"{self.campaign.id}:{query}".encode()).hexdigest()[:10]
            label = re.sub(r"\s+", " ", query).strip()[:70]
            leads.append(
                ImportedLeadRow(
                    business_name=f"Search prospect {index}: {label}",
                    website_url=f"https://prospect-{digest}.example",
                    location_country=self.config.region,
                    notes=f"Stub result generated from search pattern: {query}",
                )
            )
        return leads, []


class ProviderSearchLeadSource(LeadSource):
    source_type = "search_stub"

    def __init__(self, results):
        self.results = results

    def collect(self) -> tuple[list[ImportedLeadRow], list[ImportErrorDetail]]:
        return [ImportedLeadRow(
            business_name=item.business_name, website_url=item.website_url,
            location_country=item.location_country, notes=item.notes,
        ) for item in self.results], []
