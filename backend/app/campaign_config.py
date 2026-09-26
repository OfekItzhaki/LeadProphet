from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.models import Campaign, MessageVariant, Sequence


class RuleConfig(BaseModel):
    type: Literal["minimum_icp_fit", "high_score_call", "duplicate_guard"]
    enabled: bool = True
    params: dict[str, Any] = Field(default_factory=dict)


class SequenceConfig(BaseModel):
    id: str
    name: str
    is_active: bool
    steps: list[dict[str, Any]]


class VariantConfig(BaseModel):
    id: str
    sequence_id: str | None
    channel: str
    variant_key: str
    content: str
    is_active: bool


class CampaignConfig(BaseModel):
    id: str
    user_id: str
    name: str
    vertical: str
    region: str
    languages: list[str]
    services_offered: list[str]
    icp_firmographics: dict[str, Any]
    icp_technographics: dict[str, Any]
    icp_pains: list[str]
    icp_triggers: list[str]
    icp_personas: list[str]
    scoring_profile: dict[str, Any]
    search_patterns: list[dict[str, Any]]
    lead_sources_enabled: dict[str, bool]
    ai_icp_description: str
    ai_value_proposition: str
    ai_tone_guidelines: str
    rules: list[RuleConfig]
    sequences: list[SequenceConfig] = Field(default_factory=list)
    variants: list[VariantConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_operating_config(self):
        if not self.languages or not self.services_offered:
            raise ValueError("Campaign requires at least one language and service")
        if not self.ai_icp_description.strip():
            raise ValueError("Campaign requires an ICP description")
        if not self.icp_firmographics.get("industries"):
            raise ValueError("Campaign ICP requires at least one target industry")
        if not self.icp_firmographics.get("regions"):
            raise ValueError("Campaign ICP requires at least one target region")
        if not self.icp_pains:
            raise ValueError("Campaign ICP requires at least one target pain")
        return self

    @classmethod
    def from_campaign(cls, campaign: Campaign, *, sequences: list[Sequence] | None = None, variants: list[MessageVariant] | None = None):
        firmographics = dict(campaign.icp_firmographics or {})
        firmographics.setdefault("industries", [campaign.vertical])
        firmographics.setdefault("regions", [campaign.region])
        pains = list(campaign.icp_pains or []) or [campaign.ai_icp_description]
        raw_rules = campaign.campaign_rules or [
            {"type": "minimum_icp_fit", "params": {"threshold": 60}},
            {"type": "high_score_call", "params": {"threshold": 80}},
            {"type": "duplicate_guard"},
        ]
        return cls(
            id=campaign.id, user_id=campaign.user_id, name=campaign.name, vertical=campaign.vertical,
            region=campaign.region, languages=campaign.languages, services_offered=campaign.services_offered,
            icp_firmographics=firmographics, icp_technographics=campaign.icp_technographics or {},
            icp_pains=pains, icp_triggers=campaign.icp_triggers or [], icp_personas=campaign.icp_personas or [],
            scoring_profile=campaign.scoring_profile or {}, search_patterns=campaign.search_patterns or [],
            lead_sources_enabled=campaign.lead_sources_enabled or {}, ai_icp_description=campaign.ai_icp_description,
            ai_value_proposition=campaign.ai_value_proposition, ai_tone_guidelines=campaign.ai_tone_guidelines,
            rules=[RuleConfig.model_validate(rule) for rule in raw_rules],
            sequences=[SequenceConfig(
                id=item.id, name=item.name, is_active=item.is_active,
                steps=[{"id": step.id, "order_index": step.order_index, "channel": step.channel, "offset_days": step.offset_days, "template_ref": step.template_ref, "metadata": step.step_metadata} for step in item.steps],
            ) for item in sequences or []],
            variants=[VariantConfig.model_validate({
                "id": item.id, "sequence_id": item.sequence_id, "channel": item.channel,
                "variant_key": item.variant_key, "content": item.content, "is_active": item.is_active,
            }) for item in variants or []],
        )

    @classmethod
    def load(cls, db: Session, campaign: Campaign):
        sequences = db.query(Sequence).filter(Sequence.campaign_id == campaign.id, Sequence.user_id == campaign.user_id).all()
        variants = db.query(MessageVariant).filter(MessageVariant.campaign_id == campaign.id, MessageVariant.user_id == campaign.user_id).all()
        return cls.from_campaign(campaign, sequences=sequences, variants=variants)
