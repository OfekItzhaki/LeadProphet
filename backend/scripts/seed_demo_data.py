"""Create idempotent, tenant-scoped demo campaigns and synthetic leads."""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal  # noqa: E402
from app.models import Campaign, Lead, LeadNote, LeadTask, MessageVariant, Sequence, SequenceStep, User  # noqa: E402
from app.services.scoring import DEFAULT_SCORING_PROFILE  # noqa: E402

CAMPAIGNS = (
    {"name": "Local Services Growth", "vertical": "local services", "pain": "manual lead handling", "service": "ai_automation"},
    {"name": "Commerce Conversion", "vertical": "ecommerce", "pain": "low website conversion", "service": "website_rebuild"},
)


def get_or_create_campaign(db, user: User, spec: dict) -> Campaign:
    campaign = db.query(Campaign).filter(Campaign.user_id == user.id, Campaign.name == spec["name"]).first()
    if campaign:
        return campaign
    campaign = Campaign(
        user_id=user.id, name=spec["name"], vertical=spec["vertical"], region="Israel", languages=["he", "en"],
        services_offered=[spec["service"], "mvp_build"], search_patterns=[{"query": f"{spec['vertical']} Tel Aviv"}],
        lead_sources_enabled={"manual_csv": True, "web_search": True},
        ai_icp_description=f"Small {spec['vertical']} businesses with growth intent",
        ai_value_proposition="Improve conversion and automate repetitive lead handling",
        ai_tone_guidelines="Warm, concise, and specific", scoring_profile=DEFAULT_SCORING_PROFILE,
        icp_firmographics={"company_sizes": ["small_business"], "industries": [spec["vertical"]], "regions": ["Israel"]},
        icp_technographics={"technologies": ["wordpress", "wix"]}, icp_pains=[spec["pain"]],
        icp_triggers=["hiring", "new location"], icp_personas=["Founder", "Marketing lead"],
    )
    db.add(campaign); db.flush()
    sequence = Sequence(user_id=user.id, campaign_id=campaign.id, name="Founder cadence", description="Email, LinkedIn, then call")
    sequence.steps = [
        SequenceStep(order_index=0, channel="email", offset_days=0, step_metadata={"pipeline_stage": "qualified"}),
        SequenceStep(order_index=1, channel="linkedin", offset_days=2, step_metadata={"title": "Connect on LinkedIn"}),
        SequenceStep(order_index=2, channel="call", offset_days=5, step_metadata={"title": "Call decision maker", "pipeline_stage": "waiting_response"}),
    ]
    db.add(sequence)
    db.add_all([MessageVariant(user_id=user.id, campaign_id=campaign.id, channel="email", variant_key="subject_line", content=text) for text in ("A practical idea for your team", "Quick growth question")])
    return campaign


def seed(email: str, leads_per_campaign: int) -> None:
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email.lower()).first()
        if not user:
            user = User(email=email.lower(), display_name="LeadProphet Demo", role="owner")
            db.add(user); db.flush()
        campaigns = [get_or_create_campaign(db, user, spec) for spec in CAMPAIGNS]
        db.flush()
        created = 0
        for campaign in campaigns:
            sequence = db.query(Sequence).filter(Sequence.campaign_id == campaign.id, Sequence.user_id == user.id).first()
            for index in range(leads_per_campaign):
                name = f"{campaign.vertical.title()} Prospect {index + 1:03d}"
                lead = db.query(Lead).filter(Lead.user_id == user.id, Lead.campaign_id == campaign.id, Lead.business_name == name).first()
                if lead: continue
                analyzed = index < 10
                lead = Lead(
                    user_id=user.id, campaign_id=campaign.id, business_name=name,
                    website_url=f"https://demo-{campaign.id[:6]}-{index}.example", location_city="Tel Aviv", location_country="Israel",
                    pipeline_stage="qualified" if analyzed else "new", status="contact_draft_ready" if analyzed else "new",
                    priority="high" if analyzed else "low", score=85 if analyzed else None,
                    ai_analysis={"icp_fit_score": 88, "icp_explanation": "Synthetic ICP match", "icp_signals": {"region": True}} if analyzed else None,
                    enrichment={"inferred_business_size": "small_business", "provider": "synthetic"}, tech_stack_detected={}, risk_flags=[],
                    sequence_id=sequence.id if analyzed else None, sequence_position=0 if analyzed else None,
                )
                db.add(lead); db.flush(); created += 1
                if index < 5:
                    db.add(LeadTask(user_id=user.id, lead_id=lead.id, title="Review synthetic account", due_date=datetime.now(timezone.utc) + timedelta(days=index % 3)))
                    db.add(LeadNote(user_id=user.id, lead_id=lead.id, body="Synthetic demo account for product evaluation."))
        db.commit()
        print(f"Seeded {email}: {len(campaigns)} campaigns, {created} new leads ({leads_per_campaign} requested per campaign)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default="demo@leadprophet.local")
    parser.add_argument("--leads", type=int, default=100, help="Synthetic leads per campaign")
    args = parser.parse_args()
    seed(args.email, max(1, args.leads))
