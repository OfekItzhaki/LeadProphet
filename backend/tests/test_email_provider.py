import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import ContactMessage, Event
from app.providers import email as email_module
from app.providers.email import EmailMessage, email_delivery_ready, get_email_provider
from app.routers import public as public_router


class FakeSMTP:
    instances = []

    def __init__(self, host, port, *, timeout, context=None):
        self.host, self.port, self.timeout, self.context = host, port, timeout, context
        self.started_tls = False
        self.credentials = None
        self.message = None
        self.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def starttls(self, *, context):
        self.started_tls = context is not None

    def login(self, username, password):
        self.credentials = (username, password)

    def send_message(self, message):
        self.message = message


def configure_smtp(monkeypatch, security="starttls"):
    values = {
        "email_provider": "smtp", "smtp_host": "smtp.example.test", "smtp_port": 465 if security == "ssl" else 587,
        "smtp_username": "mailer", "smtp_password": "test-only-password", "smtp_security": security,
        "smtp_timeout_seconds": 5, "email_from_address": "sender@example.test", "admin_notification_email": "owner@example.test",
    }
    for key, value in values.items():
        monkeypatch.setattr(settings, key, value)


@pytest.mark.parametrize("security", ["starttls", "ssl"])
def test_smtp_sends_with_verified_tls_and_timeout(monkeypatch, security):
    configure_smtp(monkeypatch, security)
    FakeSMTP.instances.clear()
    monkeypatch.setattr(email_module.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(email_module.smtplib, "SMTP_SSL", FakeSMTP)
    assert email_delivery_ready()
    result = asyncio.run(get_email_provider().send(EmailMessage(to="owner@example.test", subject="Contact", body="A test message")))
    client = FakeSMTP.instances[-1]
    assert result.accepted and result.provider == "smtp"
    assert (client.host, client.port, client.timeout) == ("smtp.example.test", 465 if security == "ssl" else 587, 5)
    assert client.started_tls == (security == "starttls")
    assert (client.context is not None) == (security == "ssl")
    assert client.credentials == ("mailer", "test-only-password")
    assert client.message["From"] == "sender@example.test"
    assert client.message["To"] == "owner@example.test"


def test_missing_smtp_values_are_reported_without_secrets(monkeypatch):
    configure_smtp(monkeypatch)
    monkeypatch.setattr(settings, "smtp_password", None)
    assert not email_delivery_ready()
    with pytest.raises(RuntimeError, match="SMTP_PASSWORD") as error:
        get_email_provider()
    assert "test-only-password" not in str(error.value)


def test_contact_submission_uses_smtp_without_losing_the_saved_message(tmp_path: Path, monkeypatch):
    configure_smtp(monkeypatch)
    FakeSMTP.instances.clear()
    monkeypatch.setattr(email_module.smtplib, "SMTP", FakeSMTP)
    database = create_engine(f"sqlite:///{tmp_path / 'contact.db'}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=database)
    Base.metadata.create_all(database)

    def override_db():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    public_router._contact_attempts.clear()
    try:
        response = TestClient(app).post("/contact", data={
            "name": "Contact Test", "email": "visitor@example.test", "topic": "general",
            "message": "Please contact me about your service.",
        }, follow_redirects=False)
        assert response.status_code == 303
        with Session() as db:
            assert db.query(ContactMessage).count() == 1
            assert db.query(Event).filter(Event.event_type == "contact_message_created").count() == 1
        assert "visitor@example.test" in FakeSMTP.instances[-1].message.get_content()

        class FailingSMTP(FakeSMTP):
            def send_message(self, message):
                raise email_module.smtplib.SMTPException("test transport unavailable")

        monkeypatch.setattr(email_module.smtplib, "SMTP", FailingSMTP)
        failed = TestClient(app).post("/contact", data={
            "name": "Second Visitor", "email": "second@example.test", "topic": "support",
            "message": "Please contact me about this second request.",
        }, follow_redirects=False)
        assert failed.status_code == 303
        with Session() as db:
            assert db.query(ContactMessage).count() == 2
            assert db.query(Event).filter(Event.event_type == "contact_notification_failed").count() == 1
    finally:
        app.dependency_overrides.clear()
        public_router._contact_attempts.clear()
