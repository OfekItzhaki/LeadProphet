"""initial LeadProphet schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("vertical", sa.String(length=120), nullable=False),
        sa.Column("region", sa.String(length=120), nullable=False),
        sa.Column("languages", sa.JSON(), nullable=False),
        sa.Column("services_offered", sa.JSON(), nullable=False),
        sa.Column("search_patterns", sa.JSON(), nullable=False),
        sa.Column("lead_sources_enabled", sa.JSON(), nullable=False),
        sa.Column("ai_icp_description", sa.Text(), nullable=False),
        sa.Column("ai_value_proposition", sa.Text(), nullable=False),
        sa.Column("ai_tone_guidelines", sa.Text(), nullable=False),
        sa.Column("scoring_profile", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "leads",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("raw_source_reference", sa.JSON(), nullable=True),
        sa.Column("business_name", sa.String(length=255), nullable=False),
        sa.Column("website_url", sa.String(length=500), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=80), nullable=True),
        sa.Column("location_city", sa.String(length=120), nullable=True),
        sa.Column("location_country", sa.String(length=120), nullable=True),
        sa.Column("detected_language", sa.String(length=20), nullable=False, server_default="unknown"),
        sa.Column("lead_category", sa.String(length=40), nullable=False, server_default="business"),
        sa.Column("suggested_service_focus", sa.String(length=80), nullable=False, server_default="other"),
        sa.Column("tech_stack_detected", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("ai_business_summary", sa.Text(), nullable=True),
        sa.Column("ai_problem_summary", sa.JSON(), nullable=True),
        sa.Column("ai_proposed_value", sa.Text(), nullable=True),
        sa.Column("ai_analysis", sa.JSON(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="low"),
        sa.Column("score_reason", sa.Text(), nullable=True),
        sa.Column("risk_flags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="new"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_leads_campaign_id", "leads", ["campaign_id"])
    op.create_index("ix_leads_status", "leads", ["status"])
    op.create_index("ix_leads_score", "leads", ["score"])

    op.create_table(
        "outreach_templates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id"), nullable=True),
        sa.Column("service_focus", sa.String(length=80), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("template_body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "outreach_messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("lead_id", sa.String(length=36), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("ai_draft_body", sa.Text(), nullable=False),
        sa.Column("final_body", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_status", sa.String(length=80), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_outreach_messages_lead_id", "outreach_messages", ["lead_id"])

    op.create_table(
        "ai_call_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("lead_id", sa.String(length=36), sa.ForeignKey("leads.id"), nullable=True),
        sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id"), nullable=True),
        sa.Column("step_name", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ai_call_logs")
    op.drop_index("ix_outreach_messages_lead_id", table_name="outreach_messages")
    op.drop_table("outreach_messages")
    op.drop_table("outreach_templates")
    op.drop_index("ix_leads_score", table_name="leads")
    op.drop_index("ix_leads_status", table_name="leads")
    op.drop_index("ix_leads_campaign_id", table_name="leads")
    op.drop_table("leads")
    op.drop_table("campaigns")

