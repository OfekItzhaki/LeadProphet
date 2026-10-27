from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.config import settings
from app.db import engine
from app.models import Campaign, CmsContent, Lead, LegalDocument, OperatorSettings
from app.services.public_content import DEFAULT_CONTENT


def get_operator_settings(db: Session, user_id: str, *, create: bool = True) -> OperatorSettings | None:
    """Return the deployment-wide public profile, regardless of the managing owner."""
    item = db.query(OperatorSettings).order_by(OperatorSettings.updated_at.asc(), OperatorSettings.id.asc()).first()
    if item or not create:
        return item
    item = OperatorSettings(user_id=user_id, product_name="LeadProphet", support_email=settings.public_contact_email, phone=settings.public_contact_phone, city=settings.public_contact_city, timezone=settings.public_contact_timezone, response_time=settings.public_response_hours)
    db.add(item); db.commit(); db.refresh(item)
    return item


def public_profile(db: Session) -> dict[str, str | None]:
    profile = get_operator_settings(db, "", create=False)
    return {
        "product_name": profile.product_name if profile else "LeadProphet",
        "email": profile.support_email if profile and profile.support_email else settings.public_contact_email,
        "phone": profile.phone if profile else settings.public_contact_phone,
        "city": profile.city if profile and profile.city else settings.public_contact_city,
        "timezone": profile.timezone if profile else settings.public_contact_timezone,
        "response_hours": profile.response_time if profile and profile.response_time else settings.public_response_hours,
        "description": profile.company_description if profile else None,
        "footer_text": profile.footer_text if profile else None,
    }


def readiness(db: Session, user_id: str) -> dict:
    profile = get_operator_settings(db, user_id)
    content = {row.slug: row.body for row in db.query(CmsContent).all()}
    checks = [
        make_check("database", "Database connected", True, "required", "Database connection is healthy."),
        make_check("migrations", "Migrations at head", migration_at_head(), "required", "Run Alembic upgrade head."),
        make_check("jwt_secret", "Secure JWT secret", bool(settings.jwt_secret_key), "required", "Set JWT_SECRET_KEY before production."),
        make_check("public_profile", "Public profile", bool(profile and profile.support_email and profile.city), "required", "Add verified support email and location."),
        make_check("legal_published", "Legal documents published", db.query(LegalDocument).filter(LegalDocument.is_published.is_(True)).count() >= 2, "required", "Review and publish terms and privacy documents."),
        make_check("first_campaign", "First campaign", db.query(Campaign).filter(Campaign.user_id == user_id).count() > 0, "required", "Create a campaign with the guided wizard."),
        make_check("first_leads", "Campaign leads", db.query(Lead).filter(Lead.user_id == user_id).count() > 0, "warning", "Import a CSV or run discovery."),
        make_check("google_oauth", "Google OAuth", bool(settings.google_client_id and settings.google_client_secret), "optional", "Add client ID, secret, and callback URL."),
        make_check("email_delivery", "Email delivery", settings.email_provider not in {"stub", "disabled"} and bool(settings.email_api_key), "optional", "Configure a supported sending provider; manual sending remains available."),
        make_check("cms_customized", "Customized public content", any(content.get(key) != value for key, value in DEFAULT_CONTENT.items()), "warning", "Review the default home and about copy."),
    ]
    required_ok = all(item["ok"] for item in checks if item["category"] == "required")
    configured = sum(item["ok"] for item in checks)
    if required_ok and all(item["ok"] for item in checks): status = "Ready for production"
    elif required_ok: status = "Ready for staging"
    elif configured: status = "Partially ready"
    else: status = "Not ready"
    return {"status": status, "checks": checks, "by_id": {item["id"]: item for item in checks}, "configured": configured, "total": len(checks)}


def make_check(check_id: str, label: str, ok: bool, category: str, guidance: str) -> dict:
    severity = "complete" if ok else ("blocking" if category == "required" else "warning")
    return {"id": check_id, "label": label, "ok": ok, "category": category, "group": category, "severity": severity, "level": severity, "guidance": guidance}


def migration_at_head() -> bool:
    try:
        root = Path(__file__).resolve().parents[2]
        cfg = Config(str(root / "alembic.ini")); cfg.set_main_option("script_location", str(root / "alembic"))
        expected = ScriptDirectory.from_config(cfg).get_current_head()
        with engine.connect() as connection:
            if "alembic_version" not in inspect(connection).get_table_names(): return False
            current = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
        return current == expected
    except Exception:
        return False
