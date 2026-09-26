import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def new_uuid() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("google_subject", name="uq_users_google_subject"),
        Index("ix_users_email", "email"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(320))
    google_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="owner")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Campaign(Base, TimestampMixin):
    __tablename__ = "campaigns"
    __table_args__ = (Index("ix_campaigns_user_active", "user_id", "is_active"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    vertical: Mapped[str] = mapped_column(String(120))
    region: Mapped[str] = mapped_column(String(120))
    languages: Mapped[list[str]] = mapped_column(JSON, default=list)
    services_offered: Mapped[list[str]] = mapped_column(JSON, default=list)
    search_patterns: Mapped[list[dict]] = mapped_column(JSON, default=list)
    lead_sources_enabled: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_icp_description: Mapped[str] = mapped_column(Text)
    ai_value_proposition: Mapped[str] = mapped_column(Text)
    ai_tone_guidelines: Mapped[str] = mapped_column(Text)
    scoring_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    icp_firmographics: Mapped[dict] = mapped_column(JSON, default=dict)
    icp_technographics: Mapped[dict] = mapped_column(JSON, default=dict)
    icp_pains: Mapped[list] = mapped_column(JSON, default=list)
    icp_triggers: Mapped[list] = mapped_column(JSON, default=list)
    icp_personas: Mapped[list] = mapped_column(JSON, default=list)
    campaign_rules: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    leads: Mapped[list["Lead"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")
    sequences: Mapped[list["Sequence"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")


class Lead(Base, TimestampMixin):
    __tablename__ = "leads"
    __table_args__ = (
        Index("ix_leads_user_status", "user_id", "status"),
        Index("ix_leads_user_score", "user_id", "score"),
        Index("ix_leads_user_campaign", "user_id", "campaign_id"),
        Index("ix_leads_user_campaign_duplicate", "user_id", "campaign_id", "duplicate_of_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    duplicate_of_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(40), default="manual")
    raw_source_reference: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    business_name: Mapped[str] = mapped_column(String(255))
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    location_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    location_country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    detected_language: Mapped[str] = mapped_column(String(20), default="unknown")
    lead_category: Mapped[str] = mapped_column(String(40), default="business")
    suggested_service_focus: Mapped[str] = mapped_column(String(80), default="other")
    tech_stack_detected: Mapped[dict] = mapped_column(JSON, default=dict)
    enrichment: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_business_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_problem_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ai_proposed_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    priority: Mapped[str] = mapped_column(String(20), default="low")
    score_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(40), default="new", index=True)
    pipeline_stage: Mapped[str] = mapped_column(String(40), default="new", index=True)
    sequence_id: Mapped[str | None] = mapped_column(ForeignKey("sequences.id", ondelete="SET NULL"), nullable=True, index=True)
    sequence_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    campaign: Mapped[Campaign] = relationship(back_populates="leads")
    outreach_messages: Mapped[list["OutreachMessage"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )
    tasks: Mapped[list["LeadTask"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    notes: Mapped[list["LeadNote"]] = relationship(back_populates="lead", cascade="all, delete-orphan")


class OutreachTemplate(Base, TimestampMixin):
    __tablename__ = "outreach_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True)
    service_focus: Mapped[str] = mapped_column(String(80))
    language: Mapped[str] = mapped_column(String(10))
    channel: Mapped[str] = mapped_column(String(40))
    template_body: Mapped[str] = mapped_column(Text)


class OutreachMessage(Base, TimestampMixin):
    __tablename__ = "outreach_messages"
    __table_args__ = (Index("ix_outreach_user_campaign", "user_id", "campaign_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"))
    channel: Mapped[str] = mapped_column(String(40))
    language: Mapped[str] = mapped_column(String(10))
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ai_draft_body: Mapped[str] = mapped_column(Text)
    final_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sent_via: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sent_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    follow_up_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sequence_step_id: Mapped[str | None] = mapped_column(ForeignKey("sequence_steps.id", ondelete="SET NULL"), nullable=True, index=True)
    variant_ids: Mapped[list[str]] = mapped_column(JSON, default=list)

    lead: Mapped[Lead] = relationship(back_populates="outreach_messages")


class LeadTask(Base):
    __tablename__ = "lead_tasks"
    __table_args__ = (Index("ix_lead_tasks_user_due", "user_id", "due_date", "completed_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lead: Mapped[Lead] = relationship(back_populates="tasks")


class LeadNote(Base):
    __tablename__ = "lead_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lead: Mapped[Lead] = relationship(back_populates="notes")


class Sequence(Base, TimestampMixin):
    __tablename__ = "sequences"
    __table_args__ = (Index("ix_sequences_user_campaign", "user_id", "campaign_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    campaign: Mapped[Campaign] = relationship(back_populates="sequences")
    steps: Mapped[list["SequenceStep"]] = relationship(back_populates="sequence", cascade="all, delete-orphan", order_by="SequenceStep.order_index")


class SequenceStep(Base):
    __tablename__ = "sequence_steps"
    __table_args__ = (UniqueConstraint("sequence_id", "order_index", name="uq_sequence_step_order"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    sequence_id: Mapped[str] = mapped_column(ForeignKey("sequences.id", ondelete="CASCADE"), index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    channel: Mapped[str] = mapped_column(String(40))
    offset_days: Mapped[int] = mapped_column(Integer, default=0)
    template_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    step_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    sequence: Mapped[Sequence] = relationship(back_populates="steps")


class MessageVariant(Base, TimestampMixin):
    __tablename__ = "message_variants"
    __table_args__ = (Index("ix_variants_campaign_channel_key", "campaign_id", "channel", "variant_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    sequence_id: Mapped[str | None] = mapped_column(ForeignKey("sequences.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(40))
    variant_key: Mapped[str] = mapped_column(String(40))
    content: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AICallLog(Base):
    __tablename__ = "ai_call_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id"), nullable=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True)
    step_name: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(120))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(40))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_user_created", "user_id", "created_at"),
        Index("ix_events_campaign_type", "campaign_id", "event_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CmsContent(Base):
    __tablename__ = "cms_content"
    __table_args__ = (UniqueConstraint("slug", name="uq_cms_content_slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    slug: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LegalDocument(Base):
    __tablename__ = "legal_documents"
    __table_args__ = (UniqueConstraint("document_type", "version", name="uq_legal_document_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_type: Mapped[str] = mapped_column(String(40), index=True)
    version: Mapped[str] = mapped_column(String(40))
    body: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ContactMessage(Base):
    __tablename__ = "contact_messages"
    __table_args__ = (Index("ix_contact_messages_status_created", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(320), index=True)
    topic: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
