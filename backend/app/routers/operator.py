import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.dependencies import get_optional_user
from app.models import Campaign, LegalDocument, MessageVariant, Sequence, SequenceStep, User
from app.services.bundles import CampaignBundle, SiteContentBundle, export_campaign as build_campaign_bundle, export_site_content, import_campaign as create_imported_campaign, import_site_content
from app.services.demo import reset_demo_data
from app.services.operator import get_operator_settings, readiness
from app.services.scoring import DEFAULT_SCORING_PROFILE
from app.providers.email import email_delivery_ready, smtp_missing_settings

router = APIRouter(tags=["operator"])

TEMPLATES = {
    "israel-smb": ("Israeli SMB website modernization", "small businesses", "Israel", ["outdated website", "weak lead capture"], ["Owner", "Marketing manager"]),
    "saas-mvp": ("SaaS founders needing MVP help", "SaaS", "Global", ["slow product delivery", "limited engineering capacity"], ["Founder", "CTO"]),
    "ai-automation": ("Business AI automation", "service businesses", "Global", ["manual workflows", "repetitive operations"], ["Owner", "Operations lead"]),
    "agency-partner": ("Agency white-label engineering", "agencies", "Global", ["delivery capacity", "specialist engineering gaps"], ["Agency owner", "Delivery lead"]),
}


def owner(user: User | None) -> User:
    if not user: raise HTTPException(status_code=401, detail="Authentication required")
    if user.role != "owner" and not (settings.app_env.lower() in {"local", "development", "test"} and user.role == "test"):
        raise HTTPException(status_code=403, detail="Owner access required")
    return user


@router.get("/api/operator/readiness")
def readiness_api(db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    return readiness(db, owner(current_user).id)


@router.get("/settings")
def settings_page(request: Request, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    user = owner(current_user); profile = get_operator_settings(db, user.id); report = readiness(db, user.id)
    email_mode = "SMTP configured" if email_delivery_ready() else ("SMTP incomplete" if settings.email_provider == "smtp" else ("disabled" if settings.email_provider == "disabled" else "stub/test mode"))
    diagnostics = {"environment": settings.app_env, "app_version": settings.app_version, "api_version": settings.app_version, "database": settings.database_url.split(":", 1)[0], "oauth": bool(settings.google_client_id and settings.google_client_secret), "oauth_callback": settings.google_redirect_uri, "email_mode": email_mode, "email_missing": smtp_missing_settings() if settings.email_provider == "smtp" else []}
    return request.app.state.templates.TemplateResponse(request=request, name="settings.html", context={"current_user": user, "profile": profile, "readiness": report, "diagnostics": diagnostics, "demo_mode": settings.app_env in {"local", "test", "demo"}})


@router.post("/settings/profile")
def update_profile(product_name: str = Form(...), support_email: str = Form(...), phone: str = Form(""), city: str = Form(""), timezone: str = Form(...), response_time: str = Form(""), company_description: str = Form(""), footer_text: str = Form(""), db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    user = owner(current_user); profile = get_operator_settings(db, user.id)
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", support_email.strip()): raise HTTPException(status_code=422, detail="Enter a valid support email")
    try: ZoneInfo(timezone.strip())
    except ZoneInfoNotFoundError as exc: raise HTTPException(status_code=422, detail="Enter a valid IANA timezone") from exc
    values = {"product_name": product_name, "support_email": support_email, "phone": phone, "city": city, "timezone": timezone, "response_time": response_time, "company_description": company_description, "footer_text": footer_text}
    limits = {"product_name": 120, "support_email": 320, "phone": 80, "city": 160, "timezone": 80, "response_time": 160, "company_description": 4000, "footer_text": 500}
    if any(len(values[key]) > limit for key, limit in limits.items()): raise HTTPException(status_code=422, detail="One or more profile fields are too long")
    for key, value in locals().copy().items():
        if key in {"product_name", "support_email", "phone", "city", "timezone", "response_time", "company_description", "footer_text"}: setattr(profile, key, value.strip() or None)
    db.commit(); return RedirectResponse("/settings?saved=1", status_code=303)


@router.get("/setup")
def setup_page(request: Request, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    user = owner(current_user)
    return request.app.state.templates.TemplateResponse(request=request, name="setup.html", context={"current_user": user, "readiness": readiness(db, user.id), "demo_mode": settings.app_env in {"local", "test", "demo"}})


@router.get("/campaigns/wizard")
def wizard_page(request: Request, current_user: User | None = Depends(get_optional_user)):
    return request.app.state.templates.TemplateResponse(request=request, name="campaign_wizard.html", context={"current_user": owner(current_user), "templates": TEMPLATES, "demo_mode": settings.app_env in {"local", "test", "demo"}})


@router.post("/campaigns/wizard")
def create_from_wizard(template: str = Form("israel-smb"), name: str = Form(""), region: str = Form(""), languages: str = Form("en"), services: str = Form("web development"), industry: str = Form(""), company_size: str = Form("small business"), pains: str = Form(""), personas: str = Form(""), emphasis: str = Form("ICP fit"), tone: str = Form("consultative"), db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    user = owner(current_user); starter = TEMPLATES.get(template, TEMPLATES["israel-smb"])
    split = lambda value: [part.strip() for part in value.replace("\n", ",").split(",") if part.strip()]
    campaign = Campaign(user_id=user.id, name=name.strip() or starter[0], vertical=industry.strip() or starter[1], region=region.strip() or starter[2], languages=split(languages), services_offered=split(services), search_patterns=[], lead_sources_enabled={"manual_import": True, "web_search": False}, ai_icp_description=f"{company_size} {industry or starter[1]} in {region or starter[2]}", ai_value_proposition=f"Help with {', '.join(split(services))}", ai_tone_guidelines=f"{tone.capitalize()}, specific, useful, and low-pressure.", scoring_profile={**DEFAULT_SCORING_PROFILE, "primary_emphasis": emphasis}, icp_firmographics={"company_sizes": [company_size], "industries": [industry or starter[1]], "regions": [region or starter[2]]}, icp_technographics={}, icp_pains=split(pains) or starter[3], icp_triggers=[], icp_personas=split(personas) or starter[4], campaign_rules=[])
    db.add(campaign); db.flush()
    sequence = Sequence(user_id=user.id, campaign_id=campaign.id, name="Starter outreach", description=f"A practical {tone} four-step cadence")
    db.add(sequence); db.flush()
    for index, (channel, days, title) in enumerate((("email", 0, "Relevant introduction"), ("linkedin", 2, "Connect with context"), ("email", 5, "Useful follow-up"), ("task", 10, "Review and close loop"))): db.add(SequenceStep(sequence_id=sequence.id, order_index=index, channel=channel, offset_days=days, step_metadata={"title": title}))
    db.add(MessageVariant(user_id=user.id, campaign_id=campaign.id, sequence_id=sequence.id, channel="email", variant_key="starter-a", content="Hi {{first_name}}, I noticed {{evidence}}. We help teams like yours with {{service}}. Worth a brief conversation?"))
    db.commit(); return RedirectResponse(f"/campaigns/{campaign.id}?created=1", status_code=303)


@router.get("/campaigns/{campaign_id}/export")
def export_campaign(campaign_id: str, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    user = owner(current_user); bundle = build_campaign_bundle(db, user.id, campaign_id)
    if not bundle: raise HTTPException(status_code=404, detail="Campaign not found")
    return JSONResponse(bundle.model_dump(mode="json"), headers={"Content-Disposition": f'attachment; filename="campaign-{campaign_id}.json"'})


@router.post("/campaigns/{campaign_id}/clone")
def clone_campaign(campaign_id: str, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    user = owner(current_user); bundle = build_campaign_bundle(db, user.id, campaign_id)
    if not bundle: raise HTTPException(status_code=404, detail="Campaign not found")
    campaign = create_imported_campaign(db, user, bundle, " (copy)")
    return RedirectResponse(f"/campaigns/{campaign.id}?cloned=1", status_code=303)


@router.post("/campaigns/import")
async def import_campaign(file: UploadFile = File(...), confirm: bool = Form(False), db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    user = owner(current_user); raw = await read_bundle(file)
    bundle = validate_bundle(CampaignBundle, raw)
    if not confirm: return JSONResponse({"preview": {"campaign": bundle.campaign.name, "sequences": len(bundle.sequences), "variants": len(bundle.variants)}, "requires_confirmation": True})
    try: campaign = create_imported_campaign(db, user, bundle)
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RedirectResponse(f"/campaigns/{campaign.id}?imported=1", status_code=303)


@router.get("/settings/portability")
def portability_page(request: Request, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    user = owner(current_user)
    return request.app.state.templates.TemplateResponse(request=request, name="portability.html", context={"current_user": user, "demo_mode": settings.app_env.lower() in {"local", "development", "test", "demo"}, "campaigns": db.query(Campaign).filter(Campaign.user_id == user.id).order_by(Campaign.name).all(), "legal_documents": db.query(LegalDocument).order_by(LegalDocument.document_type, LegalDocument.version.desc()).all()})


@router.get("/settings/site-content/export")
def export_content(db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    owner(current_user); bundle = export_site_content(db)
    return JSONResponse(bundle.model_dump(mode="json"), headers={"Content-Disposition": 'attachment; filename="leadprophet-site-content.json"'})


@router.post("/settings/site-content/import")
async def import_content(file: UploadFile = File(...), confirm: bool = Form(False), db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    owner(current_user); bundle = validate_bundle(SiteContentBundle, await read_bundle(file))
    if not confirm: return JSONResponse({"preview": {"cms": len(bundle.cms), "legal": len(bundle.legal)}, "requires_confirmation": True})
    cms, legal = import_site_content(db, bundle)
    return RedirectResponse(f"/settings/portability?content_imported=1&cms={cms}&legal={legal}", status_code=303)


@router.post("/settings/demo/reset")
def reset_demo(confirm: str = Form(""), db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    user = owner(current_user)
    if settings.app_env.lower() not in {"local", "development", "test", "demo"}: raise HTTPException(status_code=404, detail="Not found")
    if confirm != "RESET SANDBOX": raise HTTPException(status_code=422, detail="Type RESET SANDBOX to confirm")
    campaign = reset_demo_data(db, user)
    return RedirectResponse(f"/campaigns/{campaign.id}?reset=1", status_code=303)


@router.post("/settings/legal/{document_id}/publish")
def publish_legal(document_id: str, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    owner(current_user); document = db.query(LegalDocument).filter(LegalDocument.id == document_id).first()
    if not document: raise HTTPException(status_code=404, detail="Legal document not found")
    db.query(LegalDocument).filter(LegalDocument.document_type == document.document_type).update({LegalDocument.is_published: False})
    document.is_published = True; db.commit()
    return RedirectResponse("/settings/portability?legal_published=1", status_code=303)


async def read_bundle(file: UploadFile) -> bytes:
    raw = await file.read()
    if len(raw) > 1_000_000: raise HTTPException(status_code=413, detail="Bundle exceeds 1 MB")
    return raw


def validate_bundle(schema, raw: bytes):
    try: return schema.model_validate_json(raw)
    except Exception as exc: raise HTTPException(status_code=422, detail="Invalid or unsupported JSON bundle") from exc
