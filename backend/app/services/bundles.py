from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, selectinload

from app.models import Campaign, CmsContent, LegalDocument, MessageVariant, Sequence, SequenceStep, User
from app.schemas import CampaignCreate

Channel = Literal["email", "linkedin", "call", "task"]


class BundleStep(BaseModel):
    channel: Channel
    offset_days: int = Field(ge=0, le=365)
    metadata: dict = Field(default_factory=dict)


class BundleSequence(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    steps: list[BundleStep] = Field(min_length=1, max_length=20)


class BundleVariant(BaseModel):
    sequence_key: str | None = None
    channel: Channel
    variant_key: str = Field(min_length=1, max_length=40)
    content: str = Field(min_length=1, max_length=20000)


class CampaignBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    campaign: CampaignCreate
    sequences: list[BundleSequence] = Field(default_factory=list, max_length=20)
    variants: list[BundleVariant] = Field(default_factory=list, max_length=100)


class CmsBundleItem(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9_\-]+$", max_length=120)
    body: str = Field(min_length=1, max_length=100000)


class LegalBundleItem(BaseModel):
    document_type: Literal["terms_of_service", "privacy_policy"]
    version: str = Field(min_length=1, max_length=40)
    body: str = Field(min_length=100, max_length=200000)
    is_published: bool = False


class SiteContentBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    cms: list[CmsBundleItem] = Field(default_factory=list, max_length=100)
    legal: list[LegalBundleItem] = Field(default_factory=list, max_length=100)


def export_campaign(db: Session, user_id: str, campaign_id: str) -> CampaignBundle | None:
    campaign = db.query(Campaign).options(selectinload(Campaign.sequences).selectinload(Sequence.steps)).filter(Campaign.id == campaign_id, Campaign.user_id == user_id).first()
    if not campaign: return None
    sequence_keys = {sequence.id: f"sequence-{index + 1}" for index, sequence in enumerate(campaign.sequences)}
    return CampaignBundle(
        schema_version=1,
        campaign=CampaignCreate.model_validate(campaign, from_attributes=True),
        sequences=[BundleSequence(key=sequence_keys[sequence.id], name=sequence.name, description=sequence.description, steps=[BundleStep(channel=step.channel, offset_days=step.offset_days, metadata=step.step_metadata) for step in sequence.steps]) for sequence in campaign.sequences],
        variants=[BundleVariant(sequence_key=sequence_keys.get(row.sequence_id), channel=row.channel, variant_key=row.variant_key, content=row.content) for row in db.query(MessageVariant).filter(MessageVariant.campaign_id == campaign.id, MessageVariant.user_id == user_id).all()],
    )


def import_campaign(db: Session, user: User, bundle: CampaignBundle, name_suffix: str = " (imported)") -> Campaign:
    campaign_data = bundle.campaign.model_dump(); campaign_data["name"] += name_suffix
    campaign = Campaign(user_id=user.id, **campaign_data); db.add(campaign); db.flush()
    sequence_ids: dict[str, str] = {}
    for item in bundle.sequences:
        sequence = Sequence(user_id=user.id, campaign_id=campaign.id, name=item.name, description=item.description); db.add(sequence); db.flush(); sequence_ids[item.key] = sequence.id
        for index, step in enumerate(item.steps): db.add(SequenceStep(sequence_id=sequence.id, order_index=index, channel=step.channel, offset_days=step.offset_days, step_metadata=step.metadata))
    for item in bundle.variants:
        if item.sequence_key and item.sequence_key not in sequence_ids: raise ValueError(f"Unknown sequence key: {item.sequence_key}")
        db.add(MessageVariant(user_id=user.id, campaign_id=campaign.id, sequence_id=sequence_ids.get(item.sequence_key), channel=item.channel, variant_key=item.variant_key, content=item.content))
    db.commit(); db.refresh(campaign); return campaign


def export_site_content(db: Session) -> SiteContentBundle:
    return SiteContentBundle(schema_version=1, cms=[CmsBundleItem(slug=row.slug, body=row.body) for row in db.query(CmsContent).order_by(CmsContent.slug).all()], legal=[LegalBundleItem(document_type=row.document_type, version=row.version, body=row.body, is_published=row.is_published) for row in db.query(LegalDocument).order_by(LegalDocument.document_type, LegalDocument.version).all()])


def import_site_content(db: Session, bundle: SiteContentBundle) -> tuple[int, int]:
    cms_added = legal_added = 0
    for item in bundle.cms:
        existing = db.query(CmsContent).filter(CmsContent.slug == item.slug).first()
        if not existing: db.add(CmsContent(slug=item.slug, body=item.body)); cms_added += 1
    for item in bundle.legal:
        existing = db.query(LegalDocument).filter(LegalDocument.document_type == item.document_type, LegalDocument.version == item.version).first()
        if not existing: db.add(LegalDocument(**item.model_dump())); legal_added += 1
    db.commit(); return cms_added, legal_added
