from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app
from app.models import Campaign, CmsContent, ContactMessage, Event, Lead, LegalDocument, User
from app.services.auth import create_access_token
from app.services.enrichment import enrich_lead
from app.services.scoring import score_campaign_fit
from app.schemas import ImportedLeadRow
from app.campaign_config import CampaignConfig
from app.services.rules import RuleEngine
from app.providers.email import EmailMessage, StubEmailProvider
from pydantic import ValidationError
import asyncio


def campaign_payload(name: str = "Restaurant growth") -> dict:
    return {
        "name": name,
        "vertical": "restaurants",
        "region": "Israel",
        "languages": ["he", "en"],
        "services_offered": ["website_rebuild", "ai_automation"],
        "search_patterns": [{"query": "restaurants Tel Aviv"}, {"query": "cafes Haifa"}],
        "lead_sources_enabled": {"manual_import": True, "csv": True, "search_stub": True},
        "ai_icp_description": "Independent restaurants with weak online conversion",
        "ai_value_proposition": "Increase reservations and reduce repetitive admin",
        "ai_tone_guidelines": "Short, warm, and specific",
        "scoring_profile": {
            "base_score": 50,
            "website_missing_bonus": 15,
            "region_match_bonus": 10,
            "service_fit_bonus": 10,
        },
        "is_active": True,
    }


@pytest.fixture
def v02_app(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'v02.db'}", connect_args={"check_same_thread": False})
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    with TestingSession() as db:
        owner = User(email="v02-owner@example.com", display_name="Owner", role="owner")
        other = User(email="v02-other@example.com", display_name="Other", role="member")
        db.add_all([owner, other])
        db.flush()
        owner_headers = {"Authorization": f"Bearer {create_access_token(owner)}"}
        other_headers = {"Authorization": f"Bearer {create_access_token(other)}"}
        owner_id = owner.id
        db.commit()
    try:
        yield TestClient(app), owner_headers, other_headers, TestingSession, owner_id
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)


def test_campaign_crud_is_scoped(v02_app) -> None:
    client, owner_headers, other_headers, _, _ = v02_app
    created = client.post("/api/campaigns", json=campaign_payload(), headers=owner_headers)
    assert created.status_code == 200
    campaign_id = created.json()["id"]
    assert client.get("/campaigns/new", headers=owner_headers).status_code == 200
    assert client.get(f"/campaigns/{campaign_id}/edit", headers=owner_headers).status_code == 200
    detail_page = client.get(f"/campaigns/{campaign_id}", headers=owner_headers)
    assert detail_page.status_code == 200
    assert "Import leads from CSV" in detail_page.text

    updated_payload = campaign_payload("Concrete pouring prospects")
    updated_payload["vertical"] = "concrete pouring"
    updated = client.put(f"/api/campaigns/{campaign_id}", json=updated_payload, headers=owner_headers)
    assert updated.status_code == 200
    assert updated.json()["vertical"] == "concrete pouring"
    assert client.put(f"/api/campaigns/{campaign_id}", json=updated_payload, headers=other_headers).status_code == 404
    assert client.delete(f"/api/campaigns/{campaign_id}", headers=other_headers).status_code == 404

    deleted = client.delete(f"/api/campaigns/{campaign_id}", headers=owner_headers)
    assert deleted.status_code == 204
    assert client.get(f"/api/campaigns/{campaign_id}", headers=owner_headers).json()["is_active"] is False


def test_csv_search_pipeline_metrics_and_tenant_isolation(v02_app) -> None:
    client, owner_headers, other_headers, TestingSession, owner_id = v02_app
    campaign = client.post("/api/campaigns", json=campaign_payload(), headers=owner_headers).json()
    campaign_id = campaign["id"]
    csv_data = (
        "business_name,website_url,contact_email,contact_phone,location_city,location_country,notes\n"
        "Cafe Alpha,,hello@alpha.example,0500000000,Tel Aviv,Israel,Needs a modern site\n"
        ",https://invalid.example,,,,,Missing name\n"
        "Bistro Beta,,,,Haifa,Israel,Reservation workflow is manual\n"
    )
    imported = client.post(
        f"/campaigns/{campaign_id}/leads/import-csv",
        files={"file": ("leads.csv", csv_data, "text/csv")},
        headers=owner_headers,
    )
    assert imported.status_code == 200
    assert imported.json()["created"] == 2
    assert imported.json()["skipped"] == 1
    assert imported.json()["queued_for_analysis"] == 2

    forbidden = client.post(
        f"/campaigns/{campaign_id}/leads/import-csv",
        files={"file": ("leads.csv", csv_data, "text/csv")},
        headers=other_headers,
    )
    assert forbidden.status_code == 404
    assert client.get("/api/leads", headers=other_headers).json() == []

    discovered = client.post(
        f"/campaigns/{campaign_id}/leads/discover-from-search", headers=owner_headers
    )
    assert discovered.status_code == 200
    assert discovered.json()["created"] == 2
    assert discovered.json()["queued_for_analysis"] == 2
    leads = client.get(f"/api/leads?campaign_id={campaign_id}", headers=owner_headers).json()
    assert {lead["source_type"] for lead in leads} == {"manual_csv", "search_stub"}
    assert {lead["status"] for lead in leads} == {"new"}

    lead_id = imported.json()["lead_ids"][0]
    analyzed = client.post(f"/api/leads/{lead_id}/analyze", headers=owner_headers)
    assert analyzed.status_code == 200
    body = analyzed.json()
    assert body["suggested_service_focus"] in campaign["services_offered"]
    assert body["detected_language"] in campaign["languages"]
    assert 0 <= body["score"] <= 100
    drafts = {(draft["language"], draft["channel"]) for draft in body["outreach_messages"]}
    assert drafts == {("he", "email"), ("he", "whatsapp"), ("en", "email"), ("en", "whatsapp")}
    detail_page = client.get(f"/leads/{lead_id}", headers=owner_headers)
    assert detail_page.status_code == 200
    assert "Copy draft" in detail_page.text
    assert "Enrichment" in detail_page.text

    summary = client.get("/metrics/summary", headers=owner_headers)
    assert summary.status_code == 200
    assert summary.json()["campaign_count"] == 1
    assert summary.json()["total_leads"] == 4
    campaign_summary = client.get(f"/campaigns/{campaign_id}/metrics", headers=owner_headers)
    assert campaign_summary.status_code == 200
    assert campaign_summary.json()["leads_by_status"]["contact_draft_ready"] == 1
    assert client.get(f"/campaigns/{campaign_id}/metrics", headers=other_headers).status_code == 404

    with TestingSession() as db:
        events = {row[0] for row in db.query(Event.event_type).filter(Event.user_id == owner_id).all()}
        assert {"campaign_created", "lead_created", "lead_imported_csv", "lead_discovered_stub", "analysis_started", "analysis_completed", "outreach_generated"} <= events


def test_v03_enrichment_scoring_and_profile_override() -> None:
    candidate = ImportedLeadRow(
        business_name="Family Bakery Studio",
        website_url="https://www.family-bakery.co.il/menu",
        contact_email="hello@family-bakery.co.il",
        location_city="Tel Aviv",
        location_country="Israel",
    )
    enrichment = enrich_lead(candidate)
    assert enrichment["domain"] == "family-bakery.co.il"
    assert enrichment["tld"] == "il"
    assert enrichment["uses_country_tld"] is True
    assert enrichment["inferred_business_size"] == "small_business"

    campaign = Campaign(
        id="campaign-score",
        user_id="user-score",
        **campaign_payload("Scoring fixture"),
    )
    lead = Lead(
        id="lead-score",
        user_id="user-score",
        campaign_id="campaign-score",
        business_name=candidate.business_name,
        location_city=candidate.location_city,
        location_country=candidate.location_country,
        enrichment=enrichment,
    )
    analysis = {
        "business_description": "An independent restaurants and bakery business",
        "suggested_service_focus": "website_rebuild",
        "pain_points": ["Website is outdated", "Reservations are manual"],
        "detected_language": "en",
    }
    campaign.scoring_profile = {}
    default_result = score_campaign_fit(campaign, lead, analysis, {"available": True, "uses_https": True})
    assert 0 <= default_result["score"] <= 100
    assert "location match" in default_result["reason_for_score"]

    campaign.scoring_profile = {
        "weights": {
            "website_quality": 0,
            "location_match": 100,
            "icp_match": 0,
            "pain_points": 0,
            "language_match": 0,
            "business_size_fit": 0,
        }
    }
    custom_result = score_campaign_fit(campaign, lead, analysis, {"available": False})
    assert custom_result["score"] == 100
    assert custom_result["profile_version"] == 2


def test_v03_dedup_filters_bulk_actions_and_events(v02_app) -> None:
    client, owner_headers, other_headers, _, _ = v02_app
    campaign_id = client.post("/api/campaigns", json=campaign_payload(), headers=owner_headers).json()["id"]
    csv_data = (
        "business_name,website_url,contact_email,location_city,location_country\n"
        "Cafe One,https://www.cafe-one.example,hello@cafe-one.example,Tel Aviv,Israel\n"
        "Cafe One Duplicate,https://cafe-one.example/,other@example.com,Tel Aviv,Israel\n"
    )
    imported = client.post(
        f"/campaigns/{campaign_id}/leads/import-csv",
        files={"file": ("duplicates.csv", csv_data, "text/csv")},
        headers=owner_headers,
    )
    assert imported.status_code == 200
    assert imported.json()["created"] == 2
    assert imported.json()["duplicates"] == 1
    assert imported.json()["queued_for_analysis"] == 1

    duplicate_view = client.get(
        f"/api/leads?campaign_id={campaign_id}&view=duplicates", headers=owner_headers
    ).json()
    assert len(duplicate_view) == 1
    assert duplicate_view[0]["duplicate_of_id"] == imported.json()["lead_ids"][0]
    assert duplicate_view[0]["enrichment"]["duplicate_match_reason"] == "website_domain"

    first_discovery = client.post(
        f"/campaigns/{campaign_id}/leads/discover-from-search", headers=owner_headers
    ).json()
    second_discovery = client.post(
        f"/campaigns/{campaign_id}/leads/discover-from-search", headers=owner_headers
    ).json()
    assert first_discovery["duplicates"] == 0
    assert second_discovery["duplicates"] == 2
    assert second_discovery["queued_for_analysis"] == 0

    clusters = client.get(f"/campaigns/{campaign_id}/duplicates", headers=owner_headers)
    assert clusters.status_code == 200
    assert clusters.json()["cluster_count"] == 3
    assert client.get(f"/campaigns/{campaign_id}/duplicates", headers=other_headers).status_code == 404

    canonical_id = imported.json()["lead_ids"][0]
    assert client.post(
        f"/campaigns/{campaign_id}/leads/analyze-new", headers=other_headers
    ).status_code == 404
    assert client.post(
        f"/campaigns/{campaign_id}/leads/mark-contacted",
        json={"lead_ids": [canonical_id]},
        headers=other_headers,
    ).status_code == 404
    marked = client.post(
        f"/campaigns/{campaign_id}/leads/mark-contacted",
        json={"lead_ids": [canonical_id]},
        headers=owner_headers,
    )
    assert marked.status_code == 200
    assert marked.json()["updated"] == 1

    recent = client.get("/events/recent?limit=10", headers=owner_headers)
    assert recent.status_code == 200
    event_types = {event["event_type"] for event in recent.json()}
    assert {"lead_created", "lead_imported_csv", "status_changed"} <= event_types
    stats = client.get("/events/stats", headers=owner_headers).json()
    assert stats["counts"]["lead_imported_csv"] == 2
    assert client.get("/events/recent", headers=other_headers).json() == []


def test_v04_pipeline_tasks_notes_outreach_timeline_and_reminders(v02_app) -> None:
    client, owner_headers, other_headers, _, _ = v02_app
    campaign_id = client.post("/api/campaigns", json=campaign_payload(), headers=owner_headers).json()["id"]
    lead = client.post(
        "/api/leads",
        json={
            "campaign_id": campaign_id, "business_name": "Workflow Cafe", "source_type": "manual",
            "website_url": "https://workflow-cafe.example", "location_city": "Tel Aviv", "location_country": "Israel",
        },
        headers=owner_headers,
    ).json()
    lead_id = lead["id"]

    stage = client.patch(
        f"/api/leads/{lead_id}/pipeline-stage", json={"pipeline_stage": "qualified"}, headers=owner_headers
    )
    assert stage.status_code == 200
    assert stage.json()["pipeline_stage"] == "qualified"
    assert client.patch(
        f"/api/leads/{lead_id}/pipeline-stage", json={"pipeline_stage": "won"}, headers=other_headers
    ).status_code == 404

    due_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    task = client.post(
        f"/api/leads/{lead_id}/tasks",
        json={"title": "Call owner", "description": "Discuss proposal", "due_date": due_at},
        headers=owner_headers,
    )
    assert task.status_code == 201
    task_id = task.json()["id"]
    assert client.get(f"/api/leads/{lead_id}/tasks", headers=other_headers).status_code == 404

    note = client.post(
        f"/api/leads/{lead_id}/notes", json={"body": "Prefers morning calls."}, headers=owner_headers
    )
    assert note.status_code == 201
    assert client.get(f"/api/leads/{lead_id}/notes", headers=other_headers).status_code == 404

    analyzed = client.post(f"/api/leads/{lead_id}/analyze", headers=owner_headers)
    assert analyzed.status_code == 200
    message_id = analyzed.json()["outreach_messages"][0]["id"]
    sent = client.post(
        f"/api/leads/{lead_id}/outreach/send",
        json={"message_id": message_id, "sent_via": "email", "follow_up_due_at": due_at},
        headers=owner_headers,
    )
    assert sent.status_code == 200
    assert sent.json()["delivery_status"] == "sent"
    assert sent.json()["sent_by_user_id"]

    reminders = client.get("/api/reminders/upcoming?days=7", headers=owner_headers).json()
    assert {item["type"] for item in reminders} == {"task", "follow_up"}
    assert client.get("/api/reminders/upcoming", headers=other_headers).json() == []

    completed = client.patch(f"/api/tasks/{task_id}", json={"completed": True}, headers=owner_headers)
    assert completed.status_code == 200
    assert completed.json()["completed_at"] is not None
    assert client.patch(f"/api/tasks/{task_id}", json={"completed": False}, headers=other_headers).status_code == 404

    timeline = client.get(f"/api/leads/{lead_id}/timeline", headers=owner_headers)
    assert timeline.status_code == 200
    titles = {item["title"] for item in timeline.json()}
    assert {"pipeline stage changed", "Note added", "Task completed", "Outreach sent"} <= titles
    assert client.get(f"/api/leads/{lead_id}/timeline", headers=other_headers).status_code == 404

    follow_up_view = client.get(
        f"/api/leads?campaign_id={campaign_id}&view=needs_follow_up", headers=owner_headers
    ).json()
    assert [item["id"] for item in follow_up_view] == [lead_id]
    page = client.get(f"/leads/{lead_id}", headers=owner_headers)
    assert page.status_code == 200
    assert "Timeline" in page.text
    assert "Sent via email" in page.text
    assert "Call owner" in page.text


def test_v05_icp_sequences_variants_and_outbound_metrics(v02_app) -> None:
    client, owner_headers, other_headers, _, _ = v02_app
    payload = campaign_payload("ICP outbound")
    payload.update({
        "icp_firmographics": {"company_sizes": ["small_business"], "industries": ["restaurant"], "regions": ["Israel"]},
        "icp_technographics": {"technologies": []},
        "icp_pains": ["manual", "outdated"], "icp_triggers": ["hiring"], "icp_personas": ["Founder", "Marketing lead"],
    })
    campaign_id = client.post("/api/campaigns", json=payload, headers=owner_headers).json()["id"]
    variants = [
        client.post(f"/campaigns/{campaign_id}/variants", json={"channel": "email", "variant_key": "subject_line", "content": content}, headers=owner_headers).json()
        for content in ("Growth idea A", "Growth idea B")
    ]
    sequence_response = client.post(
        f"/campaigns/{campaign_id}/sequences",
        json={
            "name": "Founder cadence", "description": "Email then call",
            "steps": [
                {"order_index": 1, "channel": "call", "offset_days": 2, "metadata": {"title": "Call founder", "pipeline_stage": "waiting_response"}},
                {"order_index": 0, "channel": "email", "offset_days": 0, "metadata": {"pipeline_stage": "qualified"}},
            ],
        }, headers=owner_headers,
    )
    assert sequence_response.status_code == 201
    sequence = sequence_response.json()
    sequence_id = sequence["id"]
    assert [step["order_index"] for step in sequence["steps"]] == [0, 1]
    assert client.get(f"/sequences/{sequence_id}", headers=other_headers).status_code == 404

    lead_ids = []
    selected_variants = []
    for index in range(2):
        lead = client.post("/api/leads", json={
            "campaign_id": campaign_id, "business_name": f"Restaurant {index}", "source_type": "manual",
            "location_city": "Tel Aviv", "location_country": "Israel",
        }, headers=owner_headers).json()
        lead_ids.append(lead["id"])
        attached = client.post(f"/leads/{lead['id']}/attach-sequence/{sequence_id}", headers=owner_headers)
        assert attached.status_code == 200
        assert attached.json()["sequence_position"] == 0
        refreshed = client.get(f"/api/leads/{lead['id']}", headers=owner_headers).json()
        assert refreshed["pipeline_stage"] == "qualified"
        planned = [message for message in refreshed["outreach_messages"] if message["delivery_status"] == "planned"]
        assert len(planned) == 1
        selected_variants.append(planned[0]["variant_ids"][0])
    assert set(selected_variants) == {variant["id"] for variant in variants}
    assert client.post(f"/leads/{lead_ids[0]}/attach-sequence/{sequence_id}", headers=other_headers).status_code == 404

    advanced = client.post(f"/leads/{lead_ids[0]}/advance-sequence", headers=owner_headers)
    assert advanced.status_code == 200
    assert advanced.json() == {"lead_id": lead_ids[0], "sequence_position": 1, "created_type": "task"}
    refreshed = client.get(f"/api/leads/{lead_ids[0]}", headers=owner_headers).json()
    assert refreshed["pipeline_stage"] == "waiting_response"
    tasks = client.get(f"/api/leads/{lead_ids[0]}/tasks", headers=owner_headers).json()
    assert any(task["title"] == "Call founder" for task in tasks)

    analyzed = client.post(f"/api/leads/{lead_ids[1]}/analyze", headers=owner_headers)
    assert analyzed.status_code == 200
    analysis = analyzed.json()["ai_analysis"]
    assert 0 <= analysis["icp_fit_score"] <= 100
    assert "Matches ICP on" in analysis["icp_explanation"]

    metrics = client.get(f"/campaigns/{campaign_id}/outbound-metrics", headers=owner_headers)
    assert metrics.status_code == 200
    assert metrics.json()["leads_attached_to_sequences"] == 2
    assert metrics.json()["pipeline_stages"]["waiting_response"] == 1
    assert metrics.json()["sequences"][0]["step_distribution"] == {"0": 1, "1": 1}
    sequence_stats = client.get(f"/sequences/{sequence_id}/metrics", headers=owner_headers).json()
    assert sequence_stats["lead_count"] == 2
    variant_stats = client.get(f"/campaigns/{campaign_id}/variants", headers=owner_headers).json()
    assert sorted(item["times_used"] for item in variant_stats) == [1, 3]

    campaign_page = client.get(f"/campaigns/{campaign_id}", headers=owner_headers)
    assert campaign_page.status_code == 200
    assert "Ideal Customer Profile" in campaign_page.text
    assert "Founder cadence" in campaign_page.text
    sequence_page = client.get(f"/sequences/{sequence_id}/view", headers=owner_headers)
    assert sequence_page.status_code == 200
    assert "Step distribution" in sequence_page.text
    assert client.get(f"/sequences/{sequence_id}/view", headers=other_headers).status_code == 404
    lead_page = client.get(f"/leads/{lead_ids[0]}", headers=owner_headers)
    assert lead_page.status_code == 200
    assert "Current step 2 of 2" in lead_page.text


def test_v10_config_rules_providers_daily_and_failure_paths(v02_app, monkeypatch) -> None:
    client, owner_headers, _, TestingSession, owner_id = v02_app
    test_login = client.post("/auth/dev/test-login")
    assert test_login.status_code == 200
    assert test_login.json()["user"]["email"] == "test+leadprophet@example.com"
    assert test_login.json()["user"]["role"] == "test"
    from app.routers import auth as auth_router
    monkeypatch.setattr(auth_router.settings, "app_env", "production")
    assert client.post("/auth/dev/test-login").status_code == 404
    monkeypatch.setattr(auth_router.settings, "app_env", "local")
    invalid_campaign = campaign_payload("Invalid config")
    invalid_campaign["ai_icp_description"] = ""
    rejected = client.post("/api/campaigns", json=invalid_campaign, headers=owner_headers)
    assert rejected.status_code == 422
    assert "Invalid campaign configuration" in rejected.json()["detail"]

    campaign_id = client.post("/api/campaigns", json=campaign_payload("Rules campaign"), headers=owner_headers).json()["id"]
    lead_id = client.post("/api/leads", json={
        "campaign_id": campaign_id, "business_name": "Rules Lead", "source_type": "manual", "location_country": "Israel",
    }, headers=owner_headers).json()["id"]
    with TestingSession() as db:
        campaign = db.get(Campaign, campaign_id)
        lead = db.get(Lead, lead_id)
        config = CampaignConfig.load(db, campaign)
        assert config.icp_firmographics["industries"] == [campaign.vertical]
        lead.ai_analysis = {"icp_fit_score": 30}
        decision = RuleEngine(config).apply(db, lead, {"phase": "before_attach", "automatic": True})
        assert decision.allowed is False
        assert "ICP fit" in decision.reasons[0]
        bad = config.model_dump()
        bad["icp_firmographics"] = {"industries": [], "regions": []}
        with pytest.raises(ValidationError):
            CampaignConfig.model_validate(bad)

    result = asyncio.run(StubEmailProvider().send(EmailMessage(to="buyer@example.com", subject="Test", body="Body")))
    assert result.accepted is False
    assert result.provider == "stub"
    assert client.get("/daily", headers=owner_headers).status_code == 200
    assert "Needs action" in client.get("/daily", headers=owner_headers).text

    from app.services.ai_pipeline import LeadPipeline

    async def fail_analysis(self, campaign, lead, heuristics):
        raise RuntimeError("simulated model failure")

    monkeypatch.setattr(LeadPipeline, "analyze", fail_analysis)
    failed = client.post(f"/api/leads/{lead_id}/analyze", headers=owner_headers)
    assert failed.status_code == 502
    assert failed.json()["code"] == "pipeline_error"
    with TestingSession() as db:
        lead = db.get(Lead, lead_id)
        assert lead.status == "analysis_failed"
        assert "simulated model failure" in lead.last_error
        assert db.query(Event).filter(Event.user_id == owner_id, Event.lead_id == lead_id, Event.event_type == "analysis_failed").count() == 1


def test_public_pages_contact_legal_and_cms(v02_app) -> None:
    client, owner_headers, other_headers, TestingSession, _ = v02_app
    pages = {
        "/": ("Turn good prospects", "Home"),
        "/home": ("How it works", "Home"),
        "/about": ("Our Mission", "About"),
        "/contact": ("Contact details", "Contact Us"),
        "/legal": ("Terms &amp; Privacy", "Legal"),
    }
    for path, expected in pages.items():
        response = client.get(path)
        assert response.status_code == 200
        assert expected[0] in response.text
        assert f'>{expected[1]}<' in response.text
        assert "site-footer" in response.text

    invalid = client.post("/contact", data={"name": "A", "email": "invalid", "topic": "general", "message": "short"})
    assert invalid.status_code == 422
    with TestingSession() as db:
        assert db.query(ContactMessage).count() == 0

    submitted = client.post("/contact", data={
        "name": "Prospect Owner", "email": "owner@prospect.example", "topic": "partnership",
        "message": "I would like to discuss a product partnership.",
    }, follow_redirects=False)
    assert submitted.status_code == 303
    assert submitted.headers["location"] == "/contact?sent=true"
    success = client.get(submitted.headers["location"])
    assert "Thanks for reaching out" in success.text
    with TestingSession() as db:
        message = db.query(ContactMessage).one()
        assert message.email == "owner@prospect.example"
        assert message.topic == "partnership"
        assert message.status == "new"
        assert db.query(Event).filter(Event.event_type == "contact_message_created").count() == 1

    mission = client.get("/api/cms/about_mission")
    assert mission.status_code == 200
    assert client.put("/api/cms/about_mission", json={"body": "Unauthorized edit"}, headers=other_headers).status_code == 403
    updated = client.put("/api/cms/about_mission", json={"body": "A focused outbound mission."}, headers=owner_headers)
    assert updated.status_code == 200
    assert "A focused outbound mission." in client.get("/about").text
    with TestingSession() as db:
        assert db.query(CmsContent).filter(CmsContent.slug == "about_mission").one().body == "A focused outbound mission."

    terms = client.get("/api/legal/terms_of_service")
    privacy = client.get("/api/legal/privacy_policy")
    assert terms.status_code == privacy.status_code == 200
    assert "Acceptable use" in terms.json()["body"]
    assert "Data we collect" in privacy.json()["body"]
    legal_body = "## Template update\n\n" + ("This remains a general legal template and is not legal advice. " * 3)
    legal_update = client.put("/api/legal/terms_of_service", json={"version": "1.1-template", "body": legal_body}, headers=owner_headers)
    assert legal_update.status_code == 200
    legal_page = client.get("/legal").text
    assert "Template update" in legal_page
    assert "1.1-template" not in legal_page
    with TestingSession() as db:
        assert db.query(LegalDocument).filter(LegalDocument.document_type == "terms_of_service").count() == 2
