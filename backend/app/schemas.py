from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
import re


class CampaignBase(BaseModel):
    name: str
    vertical: str
    region: str
    languages: list[str] = Field(default_factory=lambda: ["he", "en"], min_length=1)
    services_offered: list[str] = Field(
        default_factory=lambda: ["web_app_rebuild", "ai_automation", "mvp_build"], min_length=1
    )
    search_patterns: list[dict[str, Any]] = Field(default_factory=list)
    lead_sources_enabled: dict[str, bool] = Field(
        default_factory=lambda: {"web_search": False, "directories": False, "freelance": False, "manual_import": True}
    )
    ai_icp_description: str
    ai_value_proposition: str
    ai_tone_guidelines: str
    scoring_profile: dict[str, Any] = Field(default_factory=dict)
    icp_firmographics: dict[str, Any] = Field(default_factory=dict)
    icp_technographics: dict[str, Any] = Field(default_factory=dict)
    icp_pains: list[str] = Field(default_factory=list)
    icp_triggers: list[str] = Field(default_factory=list)
    icp_personas: list[str] = Field(default_factory=list)
    campaign_rules: list[dict[str, Any]] = Field(default_factory=list)
    is_active: bool = True


class CampaignCreate(CampaignBase):
    pass


class CampaignUpdate(BaseModel):
    name: str | None = None
    vertical: str | None = None
    region: str | None = None
    languages: list[str] | None = None
    services_offered: list[str] | None = None
    search_patterns: list[dict[str, Any]] | None = None
    lead_sources_enabled: dict[str, bool] | None = None
    ai_icp_description: str | None = None
    ai_value_proposition: str | None = None
    ai_tone_guidelines: str | None = None
    scoring_profile: dict[str, Any] | None = None
    icp_firmographics: dict[str, Any] | None = None
    icp_technographics: dict[str, Any] | None = None
    icp_pains: list[str] | None = None
    icp_triggers: list[str] | None = None
    icp_personas: list[str] | None = None
    campaign_rules: list[dict[str, Any]] | None = None
    is_active: bool | None = None


class CampaignRead(CampaignBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeadBase(BaseModel):
    campaign_id: str
    source_type: Literal["manual", "manual_csv", "search_stub", "web_search", "directory", "freelance_platform"] = "manual"
    raw_source_reference: dict[str, Any] | None = None
    business_name: str
    website_url: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    location_city: str | None = None
    location_country: str | None = None


class LeadCreate(LeadBase):
    rough_notes: str | None = None


class ImportedLeadRow(BaseModel):
    business_name: str = Field(min_length=1, max_length=255)
    website_url: str | None = Field(default=None, max_length=500)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=80)
    location_city: str | None = Field(default=None, max_length=120)
    location_country: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("business_name", mode="before")
    @classmethod
    def clean_business_name(cls, value):
        return str(value or "").strip()

    @field_validator(
        "website_url", "contact_email", "contact_phone", "location_city", "location_country", "notes", mode="before"
    )
    @classmethod
    def empty_to_none(cls, value):
        cleaned = str(value).strip() if value is not None else ""
        return cleaned or None


class ImportErrorDetail(BaseModel):
    row: int
    reason: str


class IngestionSummary(BaseModel):
    created: int
    skipped: int
    duplicates: int = 0
    queued_for_analysis: int
    lead_ids: list[str] = Field(default_factory=list)
    errors: list[ImportErrorDetail] = Field(default_factory=list)


class LeadUpdate(BaseModel):
    status: Literal[
        "new", "analysis_pending", "contact_draft_ready", "contacted", "responded",
        "closed_won", "closed_lost", "analysis_failed", "duplicate"
    ] | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    notes: str | None = None


PipelineStage = Literal["new", "qualified", "negotiation", "proposal_sent", "waiting_response", "won", "lost"]


class PipelineStageUpdate(BaseModel):
    pipeline_stage: PipelineStage


class PipelineStageBulkUpdate(PipelineStageUpdate):
    lead_ids: list[str] = Field(min_length=1, max_length=100)


class LeadBulkAction(BaseModel):
    lead_ids: list[str] = Field(min_length=1, max_length=100)


class OutreachMessageRead(BaseModel):
    id: str
    channel: str
    language: str
    subject: str | None
    ai_draft_body: str
    final_body: str | None
    delivery_status: str | None
    sent_at: datetime | None
    sent_via: str | None
    sent_by_user_id: str | None
    follow_up_due_at: datetime | None
    notes: str | None
    sequence_step_id: str | None
    variant_ids: list[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OutreachMessageUpdate(BaseModel):
    final_body: str | None = None
    delivery_status: str | None = None
    notes: str | None = None
    follow_up_due_at: datetime | None = None


class OutreachSendRequest(BaseModel):
    message_id: str
    sent_via: Literal["email", "linkedin", "whatsapp", "phone", "other"]
    follow_up_due_at: datetime | None = None


class LeadTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    due_date: datetime | None = None


class LeadTaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    due_date: datetime | None = None
    completed: bool | None = None


class LeadTaskRead(BaseModel):
    id: str
    lead_id: str
    title: str
    description: str | None
    due_date: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeadNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


class LeadNoteRead(BaseModel):
    id: str
    lead_id: str
    body: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TimelineItem(BaseModel):
    type: str
    title: str
    timestamp: datetime
    details: dict[str, Any] = Field(default_factory=dict)


class ReminderItem(BaseModel):
    type: Literal["task", "follow_up"]
    id: str
    lead_id: str
    business_name: str
    title: str
    due_at: datetime


class SequenceStepCreate(BaseModel):
    order_index: int = Field(ge=0)
    channel: Literal["email", "linkedin", "call", "task"]
    offset_days: int = Field(default=0, ge=0, le=365)
    template_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SequenceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    is_active: bool = True
    steps: list[SequenceStepCreate] = Field(default_factory=list)


class SequenceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    is_active: bool | None = None
    steps: list[SequenceStepCreate] | None = None


class SequenceStepRead(SequenceStepCreate):
    id: str

    model_config = ConfigDict(from_attributes=True)


class SequenceRead(BaseModel):
    id: str
    campaign_id: str
    name: str
    description: str | None
    is_active: bool
    steps: list[SequenceStepRead]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageVariantCreate(BaseModel):
    sequence_id: str | None = None
    channel: Literal["email", "linkedin", "call", "task", "whatsapp"]
    variant_key: Literal["subject_line", "opening_line", "cta"]
    content: str = Field(min_length=1, max_length=4000)
    is_active: bool = True


class MessageVariantUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=4000)
    is_active: bool | None = None


class MessageVariantRead(MessageVariantCreate):
    id: str
    campaign_id: str
    created_at: datetime
    updated_at: datetime
    times_used: int = 0
    positive_outcomes: int = 0

    model_config = ConfigDict(from_attributes=True)


class OutreachTemplateCreate(BaseModel):
    campaign_id: str | None = None
    service_focus: str
    language: str
    channel: str
    template_body: str


class OutreachTemplateRead(OutreachTemplateCreate):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserRead(BaseModel):
    id: str
    email: str
    display_name: str
    avatar_url: str | None
    role: str
    created_at: datetime
    last_login_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class CmsContentUpdate(BaseModel):
    body: str = Field(min_length=1, max_length=100000)


class CmsContentRead(CmsContentUpdate):
    slug: str
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LegalDocumentUpdate(BaseModel):
    version: str = Field(min_length=1, max_length=40)
    body: str = Field(min_length=100, max_length=200000)


class LegalDocumentRead(LegalDocumentUpdate):
    document_type: str
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContactMessageCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=5, max_length=320)
    topic: Literal["general", "feature_request", "bug", "partnership", "support", "sales"] = "general"
    message: str = Field(min_length=10, max_length=10000)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address")
        return value


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead


class EventRead(BaseModel):
    id: str
    campaign_id: str | None
    lead_id: str | None
    event_type: str
    details: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeadRead(LeadBase):
    id: str
    duplicate_of_id: str | None
    detected_language: str
    lead_category: str
    suggested_service_focus: str
    tech_stack_detected: dict[str, Any]
    enrichment: dict[str, Any]
    ai_business_summary: str | None
    ai_problem_summary: dict[str, Any] | None
    ai_proposed_value: str | None
    ai_analysis: dict[str, Any] | None
    score: int | None
    priority: str
    score_reason: str | None
    risk_flags: list[str]
    status: str
    pipeline_stage: str
    sequence_id: str | None
    sequence_position: int | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    outreach_messages: list[OutreachMessageRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
