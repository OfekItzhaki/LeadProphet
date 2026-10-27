from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import Campaign, Lead, LeadNote, LeadTask, MessageVariant, Sequence, SequenceStep, User
from app.services.scoring import DEFAULT_SCORING_PROFILE


def reset_demo_data(db: Session, user: User) -> Campaign:
    for campaign in db.query(Campaign).filter(Campaign.user_id == user.id).all(): db.delete(campaign)
    db.flush()
    campaign = Campaign(user_id=user.id, name="Sandbox Website Modernization", vertical="local service businesses", region="Israel", languages=["en", "he"], services_offered=["website_rebuild", "ai_automation"], search_patterns=[{"query": "local services Israel outdated website"}], lead_sources_enabled={"manual_import": True, "web_search": True}, ai_icp_description="Small service businesses with dated sites and manual lead handling", ai_value_proposition="Improve conversion and automate repetitive follow-up", ai_tone_guidelines="Consultative, specific, and low-pressure", scoring_profile=DEFAULT_SCORING_PROFILE, icp_firmographics={"company_sizes": ["small_business"], "industries": ["local services"], "regions": ["Israel"]}, icp_technographics={"technologies": ["wordpress", "wix"]}, icp_pains=["weak lead capture", "manual follow-up"], icp_triggers=["site redesign"], icp_personas=["Owner", "Marketing lead"], campaign_rules=[])
    db.add(campaign); db.flush()
    sequence = Sequence(user_id=user.id, campaign_id=campaign.id, name="Sandbox follow-up", description="Deterministic demo cadence"); db.add(sequence); db.flush()
    for index, (channel, days) in enumerate((("email", 0), ("linkedin", 2), ("task", 5))): db.add(SequenceStep(sequence_id=sequence.id, order_index=index, channel=channel, offset_days=days, step_metadata={"title": f"Demo step {index + 1}"}))
    db.add(MessageVariant(user_id=user.id, campaign_id=campaign.id, sequence_id=sequence.id, channel="email", variant_key="sandbox-a", content="A practical idea based on {{evidence}}."))
    for index in range(3):
        lead = Lead(user_id=user.id, campaign_id=campaign.id, business_name=f"Sandbox Prospect {index + 1}", website_url=f"https://sandbox-{index + 1}.example", location_city="Tel Aviv", location_country="Israel", status="new", pipeline_stage="new", priority="low", enrichment={}, tech_stack_detected={}, risk_flags=[])
        db.add(lead); db.flush(); db.add(LeadNote(user_id=user.id, lead_id=lead.id, body="Deterministic sandbox note.")); db.add(LeadTask(user_id=user.id, lead_id=lead.id, title="Review sandbox prospect", due_date=datetime.now(timezone.utc) + timedelta(days=index)))
    db.commit(); db.refresh(campaign); return campaign
