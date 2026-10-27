import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import Campaign, MessageVariant, OperatorSettings, Sequence, User
from app.services.auth import create_access_token
from app.services.bundles import export_campaign


@pytest.fixture
def operator_app(tmp_path: Path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'operator.db'}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine); Base.metadata.create_all(engine)
    def override_db():
        with Session() as db: yield db
    app.dependency_overrides[get_db] = override_db; monkeypatch.setattr(settings, "app_env", "test")
    with Session() as db:
        owner = User(email="owner@example.com", display_name="Owner", role="owner"); member = User(email="member@example.com", display_name="Member", role="member")
        db.add_all([owner, member]); db.flush(); owner_token = create_access_token(owner); member_token = create_access_token(member); db.commit()
    try: yield TestClient(app), Session, {"Authorization": f"Bearer {owner_token}"}, {"Authorization": f"Bearer {member_token}"}
    finally: app.dependency_overrides.clear()


def test_global_profile_readiness_and_public_rendering(operator_app) -> None:
    client, Session, owner, member = operator_app
    assert client.get("/api/operator/readiness", headers=member).status_code == 403
    report = client.get("/api/operator/readiness", headers=owner).json()
    assert {item["id"] for item in report["checks"]} >= {"migrations", "public_profile", "legal_published", "first_campaign"}
    saved = client.post("/settings/profile", headers=owner, data={"product_name": "Launch Prophet", "support_email": "support@launch.example", "phone": "", "city": "Verified City", "timezone": "Asia/Jerusalem", "response_time": "One business day", "company_description": "A verified test description.", "footer_text": "Verified footer"}, follow_redirects=False)
    assert saved.status_code == 303
    assert "support@launch.example" in client.get("/contact").text
    assert "Verified footer" in client.get("/").text
    with Session() as db: assert db.query(OperatorSettings).count() == 1
    assert client.post("/settings/profile", headers=owner, data={"product_name": "X", "support_email": "bad", "city": "X", "timezone": "Invalid/Timezone"}).status_code == 422


def test_campaign_bundle_relationships_validation_and_tenant_scope(operator_app) -> None:
    client, Session, owner, member = operator_app
    created = client.post("/campaigns/wizard", headers=owner, data={"name": "Portable campaign"}, follow_redirects=False)
    campaign_id = created.headers["location"].split("/")[2].split("?")[0]
    assert client.get(f"/campaigns/{campaign_id}/export", headers=member).status_code == 403
    exported = client.get(f"/campaigns/{campaign_id}/export", headers=owner); assert exported.status_code == 200
    payload = exported.json(); assert payload["variants"][0]["sequence_key"] == payload["sequences"][0]["key"]
    preview = client.post("/campaigns/import", headers=owner, files={"file": ("bundle.json", json.dumps(payload), "application/json")})
    assert preview.json()["requires_confirmation"] is True
    imported = client.post("/campaigns/import", headers=owner, data={"confirm": "true"}, files={"file": ("bundle.json", json.dumps(payload), "application/json")}, follow_redirects=False)
    assert imported.status_code == 303
    with Session() as db:
        copy = db.query(Campaign).filter(Campaign.name == "Portable campaign (imported)").one(); sequence = db.query(Sequence).filter(Sequence.campaign_id == copy.id).one(); variant = db.query(MessageVariant).filter(MessageVariant.campaign_id == copy.id).one()
        assert copy.user_id == sequence.user_id == variant.user_id
        assert variant.sequence_id == sequence.id
    payload["sequences"][0]["steps"][0]["channel"] = "carrier_pigeon"
    invalid = client.post("/campaigns/import", headers=owner, data={"confirm": "true"}, files={"file": ("bad.json", json.dumps(payload), "application/json")})
    assert invalid.status_code == 422


def test_site_content_additive_and_demo_reset_is_environment_guarded(operator_app, monkeypatch) -> None:
    client, Session, owner, _ = operator_app
    export = client.get("/settings/site-content/export", headers=owner); assert export.status_code == 200
    preview = client.post("/settings/site-content/import", headers=owner, files={"file": ("site.json", export.content, "application/json")})
    assert preview.json()["requires_confirmation"] is True
    reset = client.post("/settings/demo/reset", headers=owner, data={"confirm": "RESET SANDBOX"}, follow_redirects=False)
    assert reset.status_code == 303
    with Session() as db: assert db.query(Campaign).filter(Campaign.name == "Sandbox Website Modernization").count() == 1
    monkeypatch.setattr(settings, "app_env", "production")
    assert client.post("/settings/demo/reset", headers=owner, data={"confirm": "RESET SANDBOX"}).status_code == 404
