from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Campaign, Lead, MessageVariant, OutreachMessage, Sequence, SequenceStep, User
from app.schemas import MessageVariantCreate, MessageVariantRead, MessageVariantUpdate, SequenceCreate, SequenceRead, SequenceUpdate
from app.services.cache import cache
from app.services.events import record_event
from app.services.metrics import outbound_campaign_metrics, sequence_metrics, variant_metrics
from app.services.sequences import advance_sequence, attach_sequence

router = APIRouter(tags=["outbound"])


def owned_campaign(db: Session, user_id: str, campaign_id: str) -> Campaign:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == user_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def owned_sequence(db: Session, user_id: str, sequence_id: str) -> Sequence:
    sequence = db.query(Sequence).options(selectinload(Sequence.steps), selectinload(Sequence.campaign)).filter(Sequence.id == sequence_id, Sequence.user_id == user_id).first()
    if not sequence:
        raise HTTPException(status_code=404, detail="Sequence not found")
    return sequence


def sequence_payload(sequence: Sequence) -> dict:
    return {
        "id": sequence.id, "campaign_id": sequence.campaign_id, "name": sequence.name,
        "description": sequence.description, "is_active": sequence.is_active,
        "created_at": sequence.created_at, "updated_at": sequence.updated_at,
        "steps": [{"id": step.id, "order_index": step.order_index, "channel": step.channel,
                   "offset_days": step.offset_days, "template_ref": step.template_ref, "metadata": step.step_metadata}
                  for step in sequence.steps],
    }


def replace_steps(db: Session, sequence: Sequence, steps) -> None:
    sequence.steps.clear()
    db.flush()
    for item in sorted(steps, key=lambda step: step.order_index):
        sequence.steps.append(SequenceStep(
            order_index=item.order_index, channel=item.channel, offset_days=item.offset_days,
            template_ref=item.template_ref, step_metadata=item.metadata,
        ))


@router.post("/campaigns/{campaign_id}/sequences", response_model=SequenceRead, status_code=201)
def create_sequence(campaign_id: str, payload: SequenceCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    campaign = owned_campaign(db, current_user.id, campaign_id)
    if len({step.order_index for step in payload.steps}) != len(payload.steps):
        raise HTTPException(status_code=422, detail="Step order indexes must be unique")
    sequence = Sequence(user_id=current_user.id, campaign_id=campaign.id, name=payload.name, description=payload.description, is_active=payload.is_active)
    db.add(sequence); db.flush(); replace_steps(db, sequence, payload.steps)
    record_event(db, "sequence_created", user=current_user, campaign=campaign, details={"sequence_id": sequence.id})
    db.commit(); db.refresh(sequence)
    return sequence_payload(owned_sequence(db, current_user.id, sequence.id))


@router.get("/campaigns/{campaign_id}/sequences", response_model=list[SequenceRead])
def list_sequences(campaign_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    owned_campaign(db, current_user.id, campaign_id)
    rows = db.query(Sequence).options(selectinload(Sequence.steps)).filter(Sequence.campaign_id == campaign_id, Sequence.user_id == current_user.id).order_by(Sequence.created_at.desc()).all()
    return [sequence_payload(row) for row in rows]


@router.get("/sequences/{sequence_id}", response_model=SequenceRead)
def get_sequence(sequence_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return sequence_payload(owned_sequence(db, current_user.id, sequence_id))


@router.patch("/sequences/{sequence_id}", response_model=SequenceRead)
def update_sequence(sequence_id: str, payload: SequenceUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sequence = owned_sequence(db, current_user.id, sequence_id)
    data = payload.model_dump(exclude_unset=True, exclude={"steps"})
    for key, value in data.items(): setattr(sequence, key, value)
    if payload.steps is not None:
        if len({step.order_index for step in payload.steps}) != len(payload.steps):
            raise HTTPException(status_code=422, detail="Step order indexes must be unique")
        replace_steps(db, sequence, payload.steps)
    db.commit()
    return sequence_payload(owned_sequence(db, current_user.id, sequence.id))


@router.post("/leads/{lead_id}/attach-sequence/{sequence_id}")
def attach(lead_id: str, sequence_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == current_user.id).first()
    sequence = owned_sequence(db, current_user.id, sequence_id)
    if not lead or lead.campaign_id != sequence.campaign_id:
        raise HTTPException(status_code=404, detail="Lead or compatible sequence not found")
    try: created = attach_sequence(db, current_user, lead, sequence)
    except ValueError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit(); cache.invalidate_user(current_user.id)
    return {"lead_id": lead.id, "sequence_id": sequence.id, "sequence_position": lead.sequence_position, "created_type": "outreach" if isinstance(created, OutreachMessage) else "task"}


@router.post("/leads/{lead_id}/advance-sequence")
def advance(lead_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == current_user.id).first()
    if not lead or not lead.sequence_id:
        raise HTTPException(status_code=404, detail="Lead has no sequence")
    sequence = owned_sequence(db, current_user.id, lead.sequence_id)
    try: created = advance_sequence(db, current_user, lead, sequence)
    except ValueError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc
    if created is None: raise HTTPException(status_code=409, detail="Sequence is complete")
    db.commit(); cache.invalidate_user(current_user.id)
    return {"lead_id": lead.id, "sequence_position": lead.sequence_position, "created_type": "outreach" if isinstance(created, OutreachMessage) else "task"}


@router.post("/campaigns/{campaign_id}/variants", response_model=MessageVariantRead, status_code=201)
def create_variant(campaign_id: str, payload: MessageVariantCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    campaign = owned_campaign(db, current_user.id, campaign_id)
    if payload.sequence_id:
        sequence = owned_sequence(db, current_user.id, payload.sequence_id)
        if sequence.campaign_id != campaign.id: raise HTTPException(status_code=404, detail="Sequence not found")
    variant = MessageVariant(user_id=current_user.id, campaign_id=campaign.id, **payload.model_dump())
    db.add(variant); db.commit(); db.refresh(variant)
    return {**variant.__dict__, "times_used": 0, "positive_outcomes": 0}


@router.get("/campaigns/{campaign_id}/variants", response_model=list[MessageVariantRead])
def list_variants(campaign_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    owned_campaign(db, current_user.id, campaign_id)
    return variant_metrics(db, current_user.id, campaign_id)


@router.patch("/variants/{variant_id}", response_model=MessageVariantRead)
def update_variant(variant_id: str, payload: MessageVariantUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    variant = db.query(MessageVariant).filter(MessageVariant.id == variant_id, MessageVariant.user_id == current_user.id).first()
    if not variant: raise HTTPException(status_code=404, detail="Variant not found")
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(variant, key, value)
    db.commit(); db.refresh(variant)
    metrics = {row["id"]: row for row in variant_metrics(db, current_user.id, variant.campaign_id)}
    return metrics[variant.id]


@router.get("/campaigns/{campaign_id}/outbound-metrics")
def campaign_outbound_metrics(campaign_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    owned_campaign(db, current_user.id, campaign_id)
    return outbound_campaign_metrics(db, current_user.id, campaign_id)


@router.get("/sequences/{sequence_id}/metrics")
def metrics_for_sequence(sequence_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sequence = owned_sequence(db, current_user.id, sequence_id)
    return sequence_metrics(db, current_user.id, sequence)
