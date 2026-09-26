import logging
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.dependencies import get_current_user, get_optional_user
from app.models import CmsContent, ContactMessage, LegalDocument, User
from app.providers.email import EmailMessage, get_email_provider
from app.schemas import CmsContentRead, CmsContentUpdate, ContactMessageCreate, LegalDocumentRead, LegalDocumentUpdate
from app.services.events import record_event
from app.services.public_content import ensure_public_content, paragraphs

router = APIRouter(tags=["public"])
logger = logging.getLogger(__name__)
_contact_attempts: dict[str, list[float]] = {}
CONTACT_WINDOW_SECONDS = 600
CONTACT_MAX_ATTEMPTS = 5


def public_context(db: Session, current_user: User | None, active_page: str) -> dict:
    content, legal = ensure_public_content(db)
    return {
        "content": content, "legal_documents": legal, "current_user": current_user, "active_page": active_page,
        "contact": {
            "email": settings.public_contact_email, "phone": settings.public_contact_phone,
            "city": settings.public_contact_city, "timezone": settings.public_contact_timezone,
            "response_hours": settings.public_response_hours,
        },
        "google_enabled": bool(settings.google_client_id and settings.google_client_secret),
    }


@router.get("/")
@router.get("/home")
def home(request: Request, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    return request.app.state.templates.TemplateResponse(request=request, name="public_home.html", context=public_context(db, current_user, "home"))


@router.get("/about")
def about(request: Request, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    context = public_context(db, current_user, "about")
    context["roadmap"] = [line for line in context["content"]["about_roadmap"].splitlines() if line.strip()]
    return request.app.state.templates.TemplateResponse(request=request, name="about.html", context=context)


@router.get("/contact")
def contact(request: Request, sent: bool = False, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    context = public_context(db, current_user, "contact")
    context.update({"sent": sent, "form": {}, "form_error": None})
    return request.app.state.templates.TemplateResponse(request=request, name="contact.html", context=context)


@router.post("/contact")
async def submit_contact(
    request: Request, name: str = Form(...), email: str = Form(...), topic: str = Form("general"),
    message: str = Form(...), website: str = Form(""), db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user),
):
    if website.strip():
        return RedirectResponse("/contact?sent=true", status_code=303)
    now = time.time()
    address = request.client.host if request.client else "unknown"
    recent = [stamp for stamp in _contact_attempts.get(address, []) if now - stamp < CONTACT_WINDOW_SECONDS]
    if len(recent) >= CONTACT_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many contact requests. Please try again later.")
    recent.append(now)
    _contact_attempts[address] = recent
    raw = {"name": name, "email": email, "topic": topic, "message": message}
    try:
        payload = ContactMessageCreate.model_validate(raw)
    except ValidationError as exc:
        context = public_context(db, current_user, "contact")
        context.update({"sent": False, "form": raw, "form_error": exc.errors()[0]["msg"]})
        return request.app.state.templates.TemplateResponse(request=request, name="contact.html", context=context, status_code=422)
    duplicate_since = datetime.now(timezone.utc) - timedelta(minutes=10)
    duplicate = db.query(ContactMessage).filter(
        ContactMessage.email == payload.email,
        ContactMessage.topic == payload.topic,
        ContactMessage.message == payload.message,
        ContactMessage.created_at >= duplicate_since,
    ).first()
    if duplicate:
        return RedirectResponse("/contact?sent=true", status_code=303)
    item = ContactMessage(user_id=current_user.id if current_user else None, **payload.model_dump())
    db.add(item); db.flush()
    record_event(db, "contact_message_created", user=current_user, details={"contact_message_id": item.id, "topic": item.topic})
    db.commit()
    if settings.admin_notification_email:
        try:
            await get_email_provider().send(EmailMessage(
                to=settings.admin_notification_email, subject=f"LeadProphet contact: {item.topic}",
                body=f"From {item.name} <{item.email}>\n\n{item.message}",
            ))
        except Exception as exc:
            logger.warning("Contact notification failed: %s", exc)
            record_event(db, "contact_notification_failed", user=current_user, details={"contact_message_id": item.id})
            db.commit()
    return RedirectResponse("/contact?sent=true", status_code=303)


@router.get("/legal")
def legal(request: Request, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    context = public_context(db, current_user, "legal")
    context["terms_sections"] = paragraphs(context["legal_documents"]["terms_of_service"].body)
    context["privacy_sections"] = paragraphs(context["legal_documents"]["privacy_policy"].body)
    return request.app.state.templates.TemplateResponse(request=request, name="legal.html", context=context)


def require_owner(user: User) -> None:
    if user.role != "owner": raise HTTPException(status_code=403, detail="Owner access required")


@router.get("/api/cms/{slug}", response_model=CmsContentRead)
def get_cms(slug: str, db: Session = Depends(get_db)):
    ensure_public_content(db)
    item = db.query(CmsContent).filter(CmsContent.slug == slug).first()
    if not item: raise HTTPException(status_code=404, detail="Content not found")
    return item


@router.put("/api/cms/{slug}", response_model=CmsContentRead)
def update_cms(slug: str, payload: CmsContentUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_owner(current_user); ensure_public_content(db)
    item = db.query(CmsContent).filter(CmsContent.slug == slug).first()
    if not item: item = CmsContent(slug=slug, body=payload.body); db.add(item)
    else: item.body = payload.body
    record_event(db, "cms_content_updated", user=current_user, details={"slug": slug})
    db.commit(); db.refresh(item)
    return item


@router.get("/api/legal/{document_type}", response_model=LegalDocumentRead)
def get_legal(document_type: str, db: Session = Depends(get_db)):
    ensure_public_content(db)
    item = db.query(LegalDocument).filter(LegalDocument.document_type == document_type).order_by(LegalDocument.updated_at.desc(), LegalDocument.version.desc()).first()
    if not item: raise HTTPException(status_code=404, detail="Legal document not found")
    return item


@router.put("/api/legal/{document_type}", response_model=LegalDocumentRead)
def update_legal(document_type: str, payload: LegalDocumentUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_owner(current_user)
    if document_type not in {"terms_of_service", "privacy_policy"}: raise HTTPException(status_code=422, detail="Unsupported legal document type")
    item = db.query(LegalDocument).filter(LegalDocument.document_type == document_type, LegalDocument.version == payload.version).first()
    if item: item.body = payload.body
    else: item = LegalDocument(document_type=document_type, version=payload.version, body=payload.body); db.add(item)
    record_event(db, "legal_document_updated", user=current_user, details={"document_type": document_type, "version": payload.version})
    db.commit(); db.refresh(item)
    return item
