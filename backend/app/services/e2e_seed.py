from datetime import datetime, timedelta, timezone

from app.db import Base, SessionLocal, engine
from app.models import Campaign, ContactMessage, Lead, LeadNote, LeadTask, MessageVariant, Sequence, SequenceStep
from app.services.public_content import ensure_public_content
from app.services.test_support import create_second_test_user_if_not_exists, create_test_user_if_not_exists


def reset_e2e_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        ensure_public_content(db)
        primary = create_test_user_if_not_exists(db)
        create_second_test_user_if_not_exists(db)
        campaign = Campaign(
            user_id=primary.id, name="E2E Automation Campaign", vertical="service businesses", region="Israel",
            languages=["en"], services_offered=["automation"], search_patterns=[{"query": "service businesses Tel Aviv"}],
            lead_sources_enabled={"manual_csv": True, "web_search": True},
            ai_icp_description="Independent service businesses with manual workflows",
            ai_value_proposition="Reduce manual work and improve lead follow-up", ai_tone_guidelines="Direct, useful, low-pressure",
            scoring_profile={}, icp_firmographics={"industries": ["service businesses"], "regions": ["Israel"], "company_sizes": ["small_business"]},
            icp_technographics={}, icp_pains=["manual workflows"], icp_personas=["Founder"], icp_triggers=["hiring"],
        )
        db.add(campaign); db.flush()
        sequence = Sequence(user_id=primary.id, campaign_id=campaign.id, name="E2E Follow-up")
        sequence.steps = [
            SequenceStep(order_index=0, channel="email", offset_days=0, step_metadata={"pipeline_stage": "qualified"}),
            SequenceStep(order_index=1, channel="call", offset_days=2, step_metadata={"title": "Call prospect"}),
        ]
        db.add(sequence)
        db.add(MessageVariant(user_id=primary.id, campaign_id=campaign.id, channel="email", variant_key="subject_line", content="A practical idea for your workflow"))
        lead = Lead(user_id=primary.id, campaign_id=campaign.id, business_name="Seeded Service Company", website_url="https://seeded.example",
                    contact_email="hello@seeded.example", location_city="Tel Aviv", location_country="Israel", enrichment={}, tech_stack_detected={}, risk_flags=[])
        db.add(lead); db.flush()
        db.add(LeadTask(user_id=primary.id, lead_id=lead.id, title="Review seeded lead", due_date=datetime.now(timezone.utc) + timedelta(hours=1)))
        db.add(LeadNote(user_id=primary.id, lead_id=lead.id, body="Seeded E2E note"))
        db.add(ContactMessage(name="Seeded Contact", email="contact@example.com", topic="general", message="Seeded contact message for backup verification."))
        db.commit()
