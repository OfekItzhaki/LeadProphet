from datetime import datetime, timezone
import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, selectinload
from starlette import status

from app.db import get_db
from app.dependencies import get_optional_user
from app.models import Campaign, Event, Lead, LeadNote, LeadTask, MessageVariant, OutreachMessage, Sequence, SequenceStep, User
from app.schemas import CampaignCreate, ImportedLeadRow
from app.services.ai_pipeline import LeadPipeline
from app.services.cache import cache
from app.services.events import record_event
from app.services.metrics import campaign_metrics, user_metrics
from app.services.lead_creation import LeadCreationService
from app.services.scoring import DEFAULT_SCORING_PROFILE
from app.services.workflow import lead_timeline, upcoming_reminders
from app.services.metrics import outbound_campaign_metrics, sequence_metrics, variant_metrics
from app.services.sequences import advance_sequence, attach_sequence
from app.services.daily import daily_view
from app.config import settings
from app.services.operator import readiness

router = APIRouter(tags=["ui"])


def parse_local_datetime(value: str) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


@router.get("/daily")
def dashboard(request: Request, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    if not current_user:
        return RedirectResponse("/", status_code=303)
    campaigns = db.query(Campaign).filter(Campaign.user_id == current_user.id).order_by(Campaign.created_at.desc()).all()
    leads = db.query(Lead).filter(Lead.user_id == current_user.id).order_by(Lead.created_at.desc()).limit(12).all()
    recent_events = db.query(Event).filter(Event.user_id == current_user.id).order_by(Event.created_at.desc()).limit(8).all()
    metrics = user_metrics(db, current_user.id)
    reminders = upcoming_reminders(db, current_user.id, 7)
    daily = daily_view(db, current_user.id)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "campaigns": campaigns,
            "leads": leads,
            "metrics": metrics,
            "campaign_metrics": {item["campaign_id"]: item for item in metrics["campaigns"]},
            "recent_events": recent_events,
            "reminders": reminders,
            "daily": daily,
            "current_user": current_user,
            "readiness": readiness(db, current_user.id) if current_user.role == "owner" else None,
            "demo_mode": settings.app_env in {"local", "test", "demo"},
        },
    )


@router.get("/campaigns/new")
def new_campaign(request: Request, current_user: User | None = Depends(get_optional_user)):
    if not current_user:
        return RedirectResponse("/", status_code=303)
    return request.app.state.templates.TemplateResponse(
        request=request, name="campaign_form.html", context={"campaign": None, "current_user": current_user}
    )


@router.get("/campaigns/{campaign_id}/edit")
def edit_campaign(campaign_id: str, request: Request, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    if not current_user:
        return RedirectResponse("/", status_code=303)
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == current_user.id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return request.app.state.templates.TemplateResponse(
        request=request, name="campaign_form.html", context={"campaign": campaign, "current_user": current_user}
    )


@router.get("/campaigns/{campaign_id}")
def campaign_detail(campaign_id: str, request: Request, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    if not current_user:
        return RedirectResponse("/", status_code=303)
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == current_user.id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    lead_filter = request.query_params.get("view", "all")
    query = db.query(Lead).filter(Lead.campaign_id == campaign_id, Lead.user_id == current_user.id)
    if lead_filter == "high_priority":
        query = query.filter(Lead.priority == "high", Lead.duplicate_of_id.is_(None))
    elif lead_filter == "needs_outreach":
        query = query.filter(Lead.status == "contact_draft_ready", Lead.duplicate_of_id.is_(None))
    elif lead_filter == "duplicates":
        query = query.filter(Lead.duplicate_of_id.is_not(None))
    elif lead_filter == "failed_analysis":
        query = query.filter(Lead.status == "analysis_failed")
    elif lead_filter == "needs_follow_up":
        query = query.filter(Lead.outreach_messages.any(OutreachMessage.follow_up_due_at.is_not(None)))
    leads = query.order_by(Lead.created_at.desc()).all()
    sequences = db.query(Sequence).options(selectinload(Sequence.steps)).filter(Sequence.user_id == current_user.id, Sequence.campaign_id == campaign.id).order_by(Sequence.created_at.desc()).all()
    variants = variant_metrics(db, current_user.id, campaign.id)
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="campaign_detail.html",
        context={
            "campaign": campaign,
            "leads": leads,
            "metrics": campaign_metrics(db, current_user.id, campaign.id),
            "lead_filter": lead_filter,
            "current_user": current_user,
            "sequences": sequences,
            "variants": variants,
            "outbound_metrics": outbound_campaign_metrics(db, current_user.id, campaign.id),
        },
    )


def campaign_form_data(
    name: str,
    vertical: str,
    region: str,
    languages: str,
    services_offered: str,
    search_patterns: str,
    ai_icp_description: str,
    ai_value_proposition: str,
    ai_tone_guidelines: str,
    is_active: bool,
) -> dict:
    return CampaignCreate(
        name=name.strip(),
        vertical=vertical.strip(),
        region=region.strip(),
        languages=[item.strip() for item in languages.split(",") if item.strip()],
        services_offered=[item.strip() for item in services_offered.split(",") if item.strip()],
        search_patterns=[{"query": line.strip()} for line in search_patterns.splitlines() if line.strip()],
        lead_sources_enabled={"manual_import": True, "csv": True, "search_stub": True},
        ai_icp_description=ai_icp_description.strip(),
        ai_value_proposition=ai_value_proposition.strip(),
        ai_tone_guidelines=ai_tone_guidelines.strip(),
        scoring_profile=DEFAULT_SCORING_PROFILE,
        is_active=is_active,
    ).model_dump()


@router.get("/sequences/{sequence_id}/view")
def sequence_detail_view(sequence_id: str, request: Request, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    if not current_user: return RedirectResponse("/", status_code=303)
    sequence = db.query(Sequence).options(selectinload(Sequence.steps), selectinload(Sequence.campaign)).filter(Sequence.id == sequence_id, Sequence.user_id == current_user.id).first()
    if not sequence: raise HTTPException(status_code=404, detail="Sequence not found")
    leads = db.query(Lead).filter(Lead.user_id == current_user.id, Lead.sequence_id == sequence.id).order_by(Lead.sequence_position, Lead.business_name).all()
    return request.app.state.templates.TemplateResponse(request=request, name="sequence_detail.html", context={
        "sequence": sequence, "leads": leads, "metrics": sequence_metrics(db, current_user.id, sequence), "current_user": current_user,
    })


@router.post("/campaigns")
def create_campaign_from_ui(
    name: str = Form(...), vertical: str = Form(...), region: str = Form(...), languages: str = Form(...),
    services_offered: str = Form(...), search_patterns: str = Form(""), ai_icp_description: str = Form(...),
    ai_value_proposition: str = Form(...), ai_tone_guidelines: str = Form(...), db: Session = Depends(get_db),
    is_active: str | None = Form(None),
    current_user: User | None = Depends(get_optional_user),
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    campaign = Campaign(user_id=current_user.id, **campaign_form_data(
        name, vertical, region, languages, services_offered, search_patterns,
        ai_icp_description, ai_value_proposition, ai_tone_guidelines, is_active is not None,
    ))
    db.add(campaign)
    db.flush()
    record_event(db, "campaign_created", user=current_user, campaign=campaign)
    db.commit()
    cache.invalidate_user(current_user.id)
    return RedirectResponse(f"/campaigns/{campaign.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/campaigns/{campaign_id}")
def update_campaign_from_ui(
    campaign_id: str, name: str = Form(...), vertical: str = Form(...), region: str = Form(...),
    languages: str = Form(...), services_offered: str = Form(...), search_patterns: str = Form(""),
    ai_icp_description: str = Form(...), ai_value_proposition: str = Form(...),
    ai_tone_guidelines: str = Form(...), db: Session = Depends(get_db),
    is_active: str | None = Form(None),
    current_user: User | None = Depends(get_optional_user),
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == current_user.id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    for key, value in campaign_form_data(
        name, vertical, region, languages, services_offered, search_patterns,
        ai_icp_description, ai_value_proposition, ai_tone_guidelines, is_active is not None,
    ).items():
        setattr(campaign, key, value)
    record_event(db, "campaign_updated", user=current_user, campaign=campaign)
    db.commit()
    cache.invalidate_user(current_user.id)
    return RedirectResponse(f"/campaigns/{campaign.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/campaigns/seed")
def seed_campaign_from_ui(db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    from app.routers.campaigns import seed_default_campaign

    campaign = seed_default_campaign(db, current_user)
    return RedirectResponse(f"/campaigns/{campaign.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/leads")
def create_lead_from_ui(
    campaign_id: str = Form(...),
    business_name: str = Form(...),
    website_url: str = Form(""),
    location_city: str = Form(""),
    location_country: str = Form(""),
    rough_notes: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == current_user.id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    candidate = ImportedLeadRow(
        business_name=business_name,
        website_url=website_url or None,
        location_city=location_city or None,
        location_country=location_country or None,
        notes=rough_notes or None,
    )
    lead = LeadCreationService(db).create(candidate, campaign, current_user, "manual")
    db.commit()
    db.refresh(lead)
    return RedirectResponse(f"/leads/{lead.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/leads/{lead_id}")
def lead_detail(lead_id: str, request: Request, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    if not current_user:
        return RedirectResponse("/", status_code=303)
    lead = db.query(Lead).options(selectinload(Lead.outreach_messages), selectinload(Lead.tasks), selectinload(Lead.notes)).filter(Lead.id == lead_id, Lead.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    attached_sequence = db.query(Sequence).options(selectinload(Sequence.steps)).filter(Sequence.id == lead.sequence_id, Sequence.user_id == current_user.id).first() if lead.sequence_id else None
    available_sequences = db.query(Sequence).options(selectinload(Sequence.steps)).filter(Sequence.campaign_id == lead.campaign_id, Sequence.user_id == current_user.id, Sequence.is_active.is_(True)).all()
    return request.app.state.templates.TemplateResponse(
        request=request, name="lead_detail.html", context={
            "lead": lead, "current_user": current_user,
            "pipeline_stages": ["new", "qualified", "negotiation", "proposal_sent", "waiting_response", "won", "lost"],
            "timeline": lead_timeline(db, current_user.id, lead.id),
            "attached_sequence": attached_sequence, "available_sequences": available_sequences,
        }
    )


@router.post("/leads/{lead_id}/analyze")
async def analyze_lead_from_ui(lead_id: str, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    lead = db.query(Lead).options(selectinload(Lead.outreach_messages)).filter(Lead.id == lead_id, Lead.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if lead.duplicate_of_id:
        raise HTTPException(status_code=409, detail="Analyze the canonical lead instead of its duplicate")
    await LeadPipeline(db).process_lead(lead)
    return RedirectResponse(f"/leads/{lead_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/leads/{lead_id}/status")
def update_status_from_ui(lead_id: str, status_value: str = Form(...), db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == current_user.id).first()
    if lead:
        previous_status = lead.status
        lead.status = status_value
        if previous_status != status_value:
            record_event(
                db, "status_changed", user=current_user, lead=lead,
                details={"from": previous_status, "to": status_value},
            )
        db.commit()
    return RedirectResponse(f"/leads/{lead_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/leads/{lead_id}/pipeline-stage")
def update_pipeline_stage_from_ui(lead_id: str, pipeline_stage: str = Form(...), db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    previous = lead.pipeline_stage
    lead.pipeline_stage = pipeline_stage
    if previous != pipeline_stage:
        record_event(db, "pipeline_stage_changed", user=current_user, lead=lead, details={"from": previous, "to": pipeline_stage})
    db.commit()
    return RedirectResponse(f"/leads/{lead_id}", status_code=303)


@router.post("/leads/{lead_id}/tasks")
def create_task_from_ui(lead_id: str, title: str = Form(...), description: str = Form(""), due_date: str = Form(""), db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    task = LeadTask(lead_id=lead.id, user_id=current_user.id, title=title.strip(), description=description.strip() or None, due_date=parse_local_datetime(due_date))
    db.add(task)
    db.flush()
    record_event(db, "task_created", user=current_user, lead=lead, details={"task_id": task.id, "title": task.title})
    db.commit()
    return RedirectResponse(f"/leads/{lead_id}", status_code=303)


@router.post("/leads/{lead_id}/tasks/{task_id}/complete")
def complete_task_from_ui(lead_id: str, task_id: str, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    task = db.query(LeadTask).filter(LeadTask.id == task_id, LeadTask.lead_id == lead_id, LeadTask.user_id == current_user.id).first()
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == current_user.id).first()
    if not task or not lead:
        raise HTTPException(status_code=404, detail="Task not found")
    task.completed_at = datetime.now(timezone.utc)
    record_event(db, "task_completed", user=current_user, lead=lead, details={"task_id": task.id, "title": task.title})
    db.commit()
    return RedirectResponse(f"/leads/{lead_id}", status_code=303)


@router.post("/leads/{lead_id}/notes")
def create_note_from_ui(lead_id: str, body: str = Form(...), db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    note = LeadNote(lead_id=lead.id, user_id=current_user.id, body=body.strip())
    db.add(note)
    db.flush()
    record_event(db, "note_created", user=current_user, lead=lead, details={"note_id": note.id})
    db.commit()
    return RedirectResponse(f"/leads/{lead_id}", status_code=303)


@router.post("/leads/{lead_id}/outreach/{message_id}/send")
def mark_outreach_sent_from_ui(lead_id: str, message_id: str, sent_via: str = Form(...), follow_up_due_at: str = Form(""), db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == current_user.id).first()
    message = db.query(OutreachMessage).filter(OutreachMessage.id == message_id, OutreachMessage.lead_id == lead_id, OutreachMessage.user_id == current_user.id).first()
    if not lead or not message:
        raise HTTPException(status_code=404, detail="Outreach message not found")
    message.sent_at = datetime.now(timezone.utc)
    message.sent_via = sent_via
    message.sent_by_user_id = current_user.id
    message.follow_up_due_at = parse_local_datetime(follow_up_due_at)
    message.delivery_status = "sent"
    lead.status = "contacted"
    record_event(db, "outreach_sent", user=current_user, lead=lead, details={"message_id": message.id, "sent_via": sent_via})
    db.commit()
    cache.invalidate_user(current_user.id)
    return RedirectResponse(f"/leads/{lead_id}", status_code=303)


@router.post("/campaigns/{campaign_id}/icp")
def update_icp_from_ui(campaign_id: str, company_sizes: str = Form(""), industries: str = Form(""), regions: str = Form(""), technologies: str = Form(""), pains: str = Form(""), triggers: str = Form(""), personas: str = Form(""), db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    if not current_user: raise HTTPException(status_code=401, detail="Authentication required")
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == current_user.id).first()
    if not campaign: raise HTTPException(status_code=404, detail="Campaign not found")
    split = lambda value: [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]
    campaign.icp_firmographics = {"company_sizes": split(company_sizes), "industries": split(industries), "regions": split(regions)}
    campaign.icp_technographics = {"technologies": split(technologies)}
    campaign.icp_pains = split(pains); campaign.icp_triggers = split(triggers); campaign.icp_personas = split(personas)
    record_event(db, "campaign_icp_updated", user=current_user, campaign=campaign)
    db.commit(); cache.invalidate_user(current_user.id)
    return RedirectResponse(f"/campaigns/{campaign_id}", status_code=303)


@router.post("/campaigns/{campaign_id}/sequences/ui")
def create_sequence_from_ui(campaign_id: str, name: str = Form(...), description: str = Form(""), steps: str = Form(...), db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    if not current_user: raise HTTPException(status_code=401, detail="Authentication required")
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == current_user.id).first()
    if not campaign: raise HTTPException(status_code=404, detail="Campaign not found")
    sequence = Sequence(user_id=current_user.id, campaign_id=campaign.id, name=name.strip(), description=description.strip() or None)
    db.add(sequence); db.flush()
    for index, line in enumerate(line for line in steps.splitlines() if line.strip()):
        parts = [part.strip() for part in line.split(",", 2)]
        channel = parts[0].lower(); offset = int(parts[1]) if len(parts) > 1 and parts[1] else 0; title = parts[2] if len(parts) > 2 else ""
        if channel not in {"email", "linkedin", "call", "task"}: raise HTTPException(status_code=422, detail=f"Unsupported channel: {channel}")
        sequence.steps.append(SequenceStep(order_index=index, channel=channel, offset_days=offset, step_metadata={"title": title} if title else {}))
    if not sequence.steps: raise HTTPException(status_code=422, detail="At least one step is required")
    db.commit()
    return RedirectResponse(f"/campaigns/{campaign_id}", status_code=303)


@router.post("/campaigns/{campaign_id}/variants/ui")
def create_variant_from_ui(campaign_id: str, channel: str = Form(...), variant_key: str = Form(...), content: str = Form(...), db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    if not current_user: raise HTTPException(status_code=401, detail="Authentication required")
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == current_user.id).first()
    if not campaign: raise HTTPException(status_code=404, detail="Campaign not found")
    db.add(MessageVariant(user_id=current_user.id, campaign_id=campaign.id, channel=channel, variant_key=variant_key, content=content.strip()))
    db.commit()
    return RedirectResponse(f"/campaigns/{campaign_id}", status_code=303)


@router.post("/leads/{lead_id}/attach-sequence-ui")
def attach_sequence_from_ui(lead_id: str, sequence_id: str = Form(...), db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    if not current_user: raise HTTPException(status_code=401, detail="Authentication required")
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == current_user.id).first()
    sequence = db.query(Sequence).options(selectinload(Sequence.steps), selectinload(Sequence.campaign)).filter(Sequence.id == sequence_id, Sequence.user_id == current_user.id).first()
    if not lead or not sequence or lead.campaign_id != sequence.campaign_id: raise HTTPException(status_code=404, detail="Lead or sequence not found")
    attach_sequence(db, current_user, lead, sequence); db.commit()
    return RedirectResponse(f"/leads/{lead_id}", status_code=303)


@router.post("/leads/{lead_id}/advance-sequence-ui")
def advance_sequence_from_ui(lead_id: str, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    if not current_user: raise HTTPException(status_code=401, detail="Authentication required")
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == current_user.id).first()
    sequence = db.query(Sequence).options(selectinload(Sequence.steps), selectinload(Sequence.campaign)).filter(Sequence.id == (lead.sequence_id if lead else None), Sequence.user_id == current_user.id).first()
    if not lead or not sequence: raise HTTPException(status_code=404, detail="Lead has no sequence")
    try: created = advance_sequence(db, current_user, lead, sequence)
    except ValueError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc
    if created is None: raise HTTPException(status_code=409, detail="Sequence is complete")
    db.commit()
    return RedirectResponse(f"/leads/{lead_id}", status_code=303)
