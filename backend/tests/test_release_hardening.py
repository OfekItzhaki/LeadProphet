from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import ContactMessage
from app.routers import public as public_router


@pytest.fixture
def release_client(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'release.db'}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    def override_db():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    public_router._contact_attempts.clear()
    try:
        yield TestClient(app), Session
    finally:
        app.dependency_overrides.clear()
        public_router._contact_attempts.clear()


def test_security_headers_honeypot_and_duplicate_contact(release_client) -> None:
    client, Session = release_client
    home = client.get("/")
    assert home.headers["x-content-type-options"] == "nosniff"
    assert home.headers["x-frame-options"] == "DENY"
    assert home.headers["x-request-id"]

    payload = {"name": "Release Test", "email": "release@example.com", "topic": "general", "message": "A release readiness message."}
    assert client.post("/contact", data=payload, follow_redirects=False).status_code == 303
    assert client.post("/contact", data=payload, follow_redirects=False).status_code == 303
    honeypot = {**payload, "email": "bot@example.com", "website": "https://spam.example"}
    assert client.post("/contact", data=honeypot, follow_redirects=False).status_code == 303
    with Session() as db:
        assert db.query(ContactMessage).count() == 1


def test_contact_rate_limit(release_client) -> None:
    client, _ = release_client
    for index in range(public_router.CONTACT_MAX_ATTEMPTS):
        response = client.post("/contact", data={
            "name": "Rate Test", "email": f"rate{index}@example.com", "topic": "general",
            "message": f"Unique rate limiting message number {index}.",
        }, follow_redirects=False)
        assert response.status_code == 303
    blocked = client.post("/contact", data={
        "name": "Rate Test", "email": "blocked@example.com", "topic": "general",
        "message": "This request should be rate limited.",
    }, follow_redirects=False)
    assert blocked.status_code == 429


def test_test_only_auth_is_disabled_in_production(release_client, monkeypatch) -> None:
    client, _ = release_client
    monkeypatch.setattr(settings, "app_env", "production")
    assert client.post("/auth/dev/test-login").status_code == 404
    assert client.post("/auth/dev/reset").status_code == 404
