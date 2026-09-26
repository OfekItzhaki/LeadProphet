from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Campaign, OutreachMessage, OutreachTemplate, User
from app.schemas import OutreachMessageRead, OutreachMessageUpdate, OutreachTemplateCreate, OutreachTemplateRead

router = APIRouter(prefix="/api/outreach", tags=["outreach"])


@router.get("/messages", response_model=list[OutreachMessageRead])
def list_messages(
    lead_id: str | None = None,
    campaign_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[OutreachMessage]:
    query = db.query(OutreachMessage).filter(OutreachMessage.user_id == current_user.id)
    if lead_id:
        query = query.filter(OutreachMessage.lead_id == lead_id)
    if campaign_id:
        query = query.filter(OutreachMessage.campaign_id == campaign_id)
    return query.order_by(OutreachMessage.created_at.desc()).all()


@router.get("/messages/{message_id}", response_model=OutreachMessageRead)
def get_message(message_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> OutreachMessage:
    message = db.query(OutreachMessage).filter(
        OutreachMessage.id == message_id, OutreachMessage.user_id == current_user.id
    ).first()
    if not message:
        raise HTTPException(status_code=404, detail="Outreach message not found")
    return message


@router.patch("/messages/{message_id}", response_model=OutreachMessageRead)
def update_message(
    message_id: str,
    payload: OutreachMessageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OutreachMessage:
    message = db.query(OutreachMessage).filter(
        OutreachMessage.id == message_id, OutreachMessage.user_id == current_user.id
    ).first()
    if not message:
        raise HTTPException(status_code=404, detail="Outreach message not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(message, key, value)
    db.commit()
    db.refresh(message)
    return message


@router.get("/templates", response_model=list[OutreachTemplateRead])
def list_templates(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[OutreachTemplate]:
    return db.query(OutreachTemplate).filter(OutreachTemplate.user_id == current_user.id).order_by(
        OutreachTemplate.created_at.desc()
    ).all()


@router.post("/templates", response_model=OutreachTemplateRead)
def create_template(
    payload: OutreachTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OutreachTemplate:
    if payload.campaign_id:
        campaign = db.query(Campaign).filter(
            Campaign.id == payload.campaign_id, Campaign.user_id == current_user.id
        ).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
    template = OutreachTemplate(user_id=current_user.id, **payload.model_dump())
    db.add(template)
    db.commit()
    db.refresh(template)
    return template
