from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.config import settings
from app.db import engine
from app.models import Campaign, CmsContent, LegalDocument, OperatorSettings
from app.services.public_content import DEFAULT_CONTENT


def get_operator_settings(db: Session, user_id: str) -> OperatorSettings:
    item = db.query(OperatorSettings).filter(OperatorSettings.user_id == user_id).first()
    if item:
        return item
    item = OperatorSettings(
        user_id=user_id,
        support_email=settings.public_contact_email,
        phone=settings.public_contact_phone,
        city=settings.public_contact_city,
        timezone=settings.public_contact_timezone,
        response_time=settings.public_response_hours,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def readiness(db: Session, user_id: str) -> dict:
    profile = get_operator_settings(db, user_id)
    legal_count = db.query(LegalDocument).count()
    content = {row.slug: row.body for row in db.query(CmsContent).all()}
    customized = any(content.get(key) != value for key, value in DEFAULT_CONTENT.items())
    checks = [
        ("Database connected", True, "required", "Database connection is healthy."),
        ("Migrations at head", migration_at_head(), "required", "Run Alembic upgrade head."),
        ("Secure JWT secret", bool(settings.jwt_secret_key), "required", "Set JWT_SECRET_KEY before production."),
        ("Public profile", bool(profile.support_email and profile.city), "required", "Add verified contact details."),
        ("Legal documents", legal_count >= 2, "required", "Publish terms and privacy documents."),
        ("Google OAuth", bool(settings.google_client_id and settings.google_client_secret), "optional", "Add client ID, secret, and callback URL."),
        ("Email delivery", settings.email_provider not in {"stub", "disabled"} and bool(settings.email_api_key), "optional", "Configure a supported sending provider."),
        ("Customized public content", customized, "optional", "Review the default home and about copy."),
        ("First campaign", db.query(Campaign).filter(Campaign.user_id == user_id).count() > 0, "required", "Create a campaign with the guided wizard."),
    ]
    items = [{"label": label, "ok": ok, "group": group, "guidance": guidance, "level": "complete" if ok else ("blocking" if group == "required" else "warning")} for label, ok, group, guidance in checks]
    required_ok = all(item["ok"] for item in items if item["group"] == "required")
    configured = sum(item["ok"] for item in items)
    if required_ok and all(item["ok"] for item in items): status = "Ready for production"
    elif required_ok: status = "Ready for staging"
    elif configured: status = "Partially ready"
    else: status = "Not ready"
    return {"status": status, "checks": items, "configured": configured, "total": len(items)}


def migration_at_head() -> bool:
    try:
        cfg = Config("alembic.ini")
        expected = ScriptDirectory.from_config(cfg).get_current_head()
        with engine.connect() as connection:
            if "alembic_version" not in inspect(connection).get_table_names(): return False
            current = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
        return current == expected
    except Exception:
        return False
