import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db import get_db
from app.dependencies import get_optional_user
from app.models import Campaign, MessageVariant, OperatorSettings, Sequence, SequenceStep, User
from app.services.operator import get_operator_settings, readiness
from app.services.scoring import DEFAULT_SCORING_PROFILE

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
    diagnostics = {"environment": settings.app_env, "app_version": settings.app_version, "api_version": settings.app_version, "database": settings.database_url.split(":", 1)[0], "oauth": bool(settings.google_client_id and settings.google_client_secret), "oauth_callback": settings.google_redirect_uri, "email_mode": settings.email_provider if settings.email_provider != "stub" else "stub/test mode"}
    return request.app.state.templates.TemplateResponse(request=request, name="settings.html", context={"current_user": user, "profile": profile, "readiness": report, "diagnostics": diagnostics, "demo_mode": settings.app_env in {"local", "test", "demo"}})


@router.post("/settings/profile")
def update_profile(product_name: str = Form(...), support_email: str = Form(...), phone: str = Form(""), city: str = Form(""), timezone: str = Form(...), response_time: str = Form(""), company_description: str = Form(""), footer_text: str = Form(""), db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    user = owner(current_user); profile = get_operator_settings(db, user.id)
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


def bundle(campaign: Campaign) -> dict:
    return {"schema_version": 1, "campaign": {key: getattr(campaign, key) for key in ("name", "vertical", "region", "languages", "services_offered", "search_patterns", "lead_sources_enabled", "ai_icp_description", "ai_value_proposition", "ai_tone_guidelines", "scoring_profile", "icp_firmographics", "icp_technographics", "icp_pains", "icp_triggers", "icp_personas", "campaign_rules")}, "sequences": [{"name": seq.name, "description": seq.description, "steps": [{"channel": step.channel, "offset_days": step.offset_days, "metadata": step.step_metadata} for step in seq.steps]} for seq in campaign.sequences], "variants": [{"channel": row.channel, "variant_key": row.variant_key, "content": row.content} for row in campaign_variants(campaign)]}


def campaign_variants(campaign: Campaign):
    db = Session.object_session(campaign)
    return db.query(MessageVariant).filter(MessageVariant.campaign_id == campaign.id, MessageVariant.user_id == campaign.user_id).all()


@router.get("/campaigns/{campaign_id}/export")
def export_campaign(campaign_id: str, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    user = owner(current_user); campaign = db.query(Campaign).options(selectinload(Campaign.sequences).selectinload(Sequence.steps)).filter(Campaign.id == campaign_id, Campaign.user_id == user.id).first()
    if not campaign: raise HTTPException(status_code=404, detail="Campaign not found")
    return JSONResponse(bundle(campaign), headers={"Content-Disposition": f'attachment; filename="{campaign.id}.json"'})


@router.post("/campaigns/{campaign_id}/clone")
def clone_campaign(campaign_id: str, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    user = owner(current_user); source = db.query(Campaign).options(selectinload(Campaign.sequences).selectinload(Sequence.steps)).filter(Campaign.id == campaign_id, Campaign.user_id == user.id).first()
    if not source: raise HTTPException(status_code=404, detail="Campaign not found")
    return import_bundle(bundle(source), db, user, f"{source.name} (copy)")


@router.post("/campaigns/import")
async def import_campaign(file: UploadFile = File(...), confirm: bool = Form(False), db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    user = owner(current_user); raw = await file.read()
    if len(raw) > 1_000_000: raise HTTPException(status_code=413, detail="Bundle exceeds 1 MB")
    try: data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc: raise HTTPException(status_code=422, detail="Invalid JSON bundle") from exc
    if data.get("schema_version") != 1 or not isinstance(data.get("campaign"), dict): raise HTTPException(status_code=422, detail="Unsupported campaign bundle")
    if not confirm: return JSONResponse({"preview": {"campaign": data["campaign"].get("name"), "sequences": len(data.get("sequences", [])), "variants": len(data.get("variants", []))}, "requires_confirmation": True})
    return import_bundle(data, db, user)


def import_bundle(data: dict, db: Session, user: User, override_name: str | None = None):
    fields = {key for key in Campaign.__table__.columns.keys()} - {"id", "user_id", "created_at", "updated_at"}
    payload = {key: value for key, value in data["campaign"].items() if key in fields}
    payload["name"] = override_name or f"{payload.get('name', 'Imported campaign')} (imported)"
    campaign = Campaign(user_id=user.id, **payload); db.add(campaign); db.flush()
    sequence_map = []
    for item in data.get("sequences", []):
        seq = Sequence(user_id=user.id, campaign_id=campaign.id, name=item.get("name", "Imported sequence"), description=item.get("description")); db.add(seq); db.flush(); sequence_map.append(seq)
        for index, step in enumerate(item.get("steps", [])): db.add(SequenceStep(sequence_id=seq.id, order_index=index, channel=step.get("channel", "task"), offset_days=int(step.get("offset_days", 0)), step_metadata=step.get("metadata", {})))
    for item in data.get("variants", []): db.add(MessageVariant(user_id=user.id, campaign_id=campaign.id, sequence_id=sequence_map[0].id if sequence_map else None, channel=item.get("channel", "email"), variant_key=item.get("variant_key", "imported"), content=item.get("content", "")))
    db.commit(); return RedirectResponse(f"/campaigns/{campaign.id}?imported=1", status_code=303)
