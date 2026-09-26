from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import Campaign, Event, Lead, LeadNote, LeadTask, MessageVariant, Sequence, SequenceStep, User
from app.services.test_support import create_test_user_if_not_exists


def seed_test_workspace(db: Session) -> tuple[User, list[Campaign]]:
    user = create_test_user_if_not_exists(db)
    campaigns: list[Campaign] = []
    for vertical, pain in (("restaurants", "manual reservations"), ("clinics", "manual scheduling")):
        campaign = Campaign(
            user_id=user.id, name=f"Test {vertical}", vertical=vertical, region="Israel", languages=["en"],
            services_offered=["automation"], search_patterns=[{"query": f"{vertical} Tel Aviv"}],
            lead_sources_enabled={"manual_csv": True, "web_search": True},
            ai_icp_description=f"Independent {vertical}", ai_value_proposition="Reduce manual work",
            ai_tone_guidelines="Direct", scoring_profile={},
            icp_firmographics={"industries": [vertical], "regions": ["Israel"], "company_sizes": ["small_business"]},
            icp_technographics={}, icp_pains=[pain], icp_personas=["Founder"], icp_triggers=["hiring"],
        )
        db.add(campaign); db.flush()
        sequence = Sequence(user_id=user.id, campaign_id=campaign.id, name="Test cadence")
        sequence.steps = [
            SequenceStep(order_index=0, channel="email", offset_days=0, step_metadata={"pipeline_stage": "qualified"}),
            SequenceStep(order_index=1, channel="call", offset_days=2, step_metadata={"title": "Test call"}),
        ]
        db.add(sequence)
        db.add_all([
            MessageVariant(user_id=user.id, campaign_id=campaign.id, channel="email", variant_key="subject_line", content="Test subject A"),
            MessageVariant(user_id=user.id, campaign_id=campaign.id, channel="email", variant_key="subject_line", content="Test subject B"),
        ])
        lead = Lead(user_id=user.id, campaign_id=campaign.id, business_name=f"Test {vertical} lead", location_country="Israel", enrichment={}, tech_stack_detected={}, risk_flags=[])
        db.add(lead); db.flush()
        db.add(LeadTask(user_id=user.id, lead_id=lead.id, title="Test reminder", due_date=datetime.now(timezone.utc) + timedelta(hours=1)))
        db.add(LeadNote(user_id=user.id, lead_id=lead.id, body="Seeded test note"))
        db.add(Event(user_id=user.id, campaign_id=campaign.id, lead_id=lead.id, event_type="test_seeded", details={}))
        campaigns.append(campaign)
    db.commit()
    return user, campaigns
