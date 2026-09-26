from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base, get_db
from app.main import app
from app.models import Event, User
from app.routers import auth as auth_router
from app.services.auth import create_access_token, issue_refresh_token


def campaign_payload(name: str) -> dict:
    return {
        "name": name,
        "vertical": "services",
        "region": "Israel",
        "languages": ["en"],
        "services_offered": ["automation"],
        "search_patterns": [],
        "lead_sources_enabled": {"manual_import": True},
        "ai_icp_description": "Service businesses",
        "ai_value_proposition": "Reduce manual work",
        "ai_tone_guidelines": "Direct and useful",
        "scoring_profile": {},
        "is_active": True,
    }


def test_authentication_scoping_and_refresh_rotation(tmp_path: Path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    try:
        with TestingSession() as db:
            owner = User(email="owner@example.com", display_name="Owner", role="owner")
            member = User(email="member@example.com", display_name="Member", role="member")
            db.add_all([owner, member])
            db.flush()
            owner_token = create_access_token(owner)
            member_token = create_access_token(member)
            refresh_token = issue_refresh_token(db, owner)
            owner_id = owner.id
            db.commit()

        client = TestClient(app)
        unauthorized = client.get("/api/campaigns")
        assert unauthorized.status_code == 401
        assert unauthorized.json() == {"detail": "Authentication required", "code": "authentication_required"}

        owner_headers = {"Authorization": f"Bearer {owner_token}"}
        member_headers = {"Authorization": f"Bearer {member_token}"}
        created = client.post("/api/campaigns", json=campaign_payload("Owner campaign"), headers=owner_headers)
        assert created.status_code == 200
        campaign_id = created.json()["id"]

        assert [item["id"] for item in client.get("/api/campaigns", headers=owner_headers).json()] == [campaign_id]
        assert client.get("/api/campaigns", headers=member_headers).json() == []
        assert client.get(f"/api/campaigns/{campaign_id}", headers=member_headers).status_code == 404

        lead = client.post(
            "/api/leads",
            json={"campaign_id": campaign_id, "business_name": "Scoped lead"},
            headers=member_headers,
        )
        assert lead.status_code == 404

        owner_lead = client.post(
            "/api/leads",
            json={"campaign_id": campaign_id, "business_name": "Scoped lead"},
            headers=owner_headers,
        )
        assert owner_lead.status_code == 200
        lead_id = owner_lead.json()["id"]
        assert client.get(f"/api/leads/{lead_id}", headers=member_headers).status_code == 404
        assert client.post(f"/api/leads/{lead_id}/analyze", headers=member_headers).status_code == 404

        analyzed = client.post(f"/api/leads/{lead_id}/analyze", headers=owner_headers)
        assert analyzed.status_code == 200
        assert analyzed.json()["status"] == "contact_draft_ready"
        owner_messages = client.get("/api/outreach/messages", headers=owner_headers).json()
        assert len(owner_messages) == 2
        assert client.get("/api/outreach/messages", headers=member_headers).json() == []
        assert client.get(f"/api/outreach/messages/{owner_messages[0]['id']}", headers=member_headers).status_code == 404

        refreshed = client.post("/auth/refresh", json={"refresh_token": refresh_token})
        assert refreshed.status_code == 200
        assert refreshed.json()["user"]["id"] == owner_id
        assert client.post("/auth/refresh", json={"refresh_token": refresh_token}).status_code == 401

        async def fake_google_token(request):
            return {
                "userinfo": {
                    "sub": "google-subject-123",
                    "email": "google.user@example.com",
                    "email_verified": True,
                    "name": "Google User",
                    "picture": "https://example.com/avatar.png",
                }
            }

        monkeypatch.setattr(auth_router.settings, "google_client_id", "test-client")
        monkeypatch.setattr(auth_router.settings, "google_client_secret", "test-secret")
        monkeypatch.setattr(auth_router.oauth.google, "authorize_access_token", fake_google_token)
        callback = client.get("/auth/google/callback", follow_redirects=False)
        assert callback.status_code == 303
        assert callback.headers["location"] == "/daily"
        assert "leadprophet_access" in callback.cookies
        assert "leadprophet_refresh" in callback.cookies
        profile = client.get("/me")
        assert profile.status_code == 200
        assert profile.json()["email"] == "google.user@example.com"
        assert profile.json()["display_name"] == "Google User"

        logged_out = client.post("/auth/logout")
        assert logged_out.status_code == 200
        assert client.get("/me").status_code == 401
        with TestingSession() as db:
            auth_events = {row[0] for row in db.query(Event.event_type).all()}
            assert {"login", "logout", "refresh_failed"} <= auth_events
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
