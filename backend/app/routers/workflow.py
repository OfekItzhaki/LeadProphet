from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Lead, LeadNote, LeadTask, OutreachMessage, User
from app.schemas import (
    LeadNoteCreate, LeadNoteRead, LeadTaskCreate, LeadTaskRead, LeadTaskUpdate, OutreachMessageRead,
    OutreachMessageUpdate, OutreachSendRequest, PipelineStageBulkUpdate, PipelineStageUpdate,
    ReminderItem, TimelineItem,
)
from app.services.cache import cache
from app.services.events import record_event
from app.services.workflow import lead_timeline, upcoming_reminders

router = APIRouter(prefix="/api", tags=["workflow"])


def owned_lead(db: Session, user_id: str, lead_id: str) -> Lead:
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.user_id == user_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.patch("/leads/{lead_id}/pipeline-stage", response_model=dict)
def update_pipeline_stage(lead_id: str, payload: PipelineStageUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    lead = owned_lead(db, current_user.id, lead_id)
    previous = lead.pipeline_stage
    lead.pipeline_stage = payload.pipeline_stage
    if previous != lead.pipeline_stage:
        record_event(db, "pipeline_stage_changed", user=current_user, lead=lead, details={"from": previous, "to": lead.pipeline_stage})
    db.commit()
    cache.invalidate_user(current_user.id)
    return {"id": lead.id, "pipeline_stage": lead.pipeline_stage}


@router.patch("/leads/pipeline-stage/bulk", response_model=dict)
def bulk_pipeline_stage(payload: PipelineStageBulkUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    leads = db.query(Lead).filter(Lead.user_id == current_user.id, Lead.id.in_(payload.lead_ids)).all()
    if len(leads) != len(set(payload.lead_ids)):
        raise HTTPException(status_code=404, detail="One or more leads not found")
    for lead in leads:
        previous = lead.pipeline_stage
        lead.pipeline_stage = payload.pipeline_stage
        if previous != lead.pipeline_stage:
            record_event(db, "pipeline_stage_changed", user=current_user, lead=lead, details={"from": previous, "to": lead.pipeline_stage})
    db.commit()
    cache.invalidate_user(current_user.id)
    return {"updated": len(leads), "pipeline_stage": payload.pipeline_stage}


@router.get("/leads/{lead_id}/tasks", response_model=list[LeadTaskRead])
def list_tasks(lead_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    owned_lead(db, current_user.id, lead_id)
    return db.query(LeadTask).filter(LeadTask.lead_id == lead_id, LeadTask.user_id == current_user.id).order_by(LeadTask.completed_at, LeadTask.due_date).all()


@router.post("/leads/{lead_id}/tasks", response_model=LeadTaskRead, status_code=201)
def create_task(lead_id: str, payload: LeadTaskCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    lead = owned_lead(db, current_user.id, lead_id)
    task = LeadTask(lead_id=lead.id, user_id=current_user.id, **payload.model_dump())
    db.add(task)
    db.flush()
    record_event(db, "task_created", user=current_user, lead=lead, details={"task_id": task.id, "title": task.title})
    db.commit()
    db.refresh(task)
    return task


@router.patch("/tasks/{task_id}", response_model=LeadTaskRead)
def update_task(task_id: str, payload: LeadTaskUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = db.query(LeadTask).filter(LeadTask.id == task_id, LeadTask.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    data = payload.model_dump(exclude_unset=True)
    completed = data.pop("completed", None)
    for key, value in data.items():
        setattr(task, key, value)
    if completed is not None:
        task.completed_at = datetime.now(timezone.utc) if completed else None
    lead = owned_lead(db, current_user.id, task.lead_id)
    record_event(db, "task_completed" if completed else "task_updated", user=current_user, lead=lead, details={"task_id": task.id, "title": task.title})
    db.commit()
    db.refresh(task)
    return task


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = db.query(LeadTask).filter(LeadTask.id == task_id, LeadTask.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    lead = owned_lead(db, current_user.id, task.lead_id)
    record_event(db, "task_deleted", user=current_user, lead=lead, details={"task_id": task.id, "title": task.title})
    db.delete(task)
    db.commit()


@router.get("/leads/{lead_id}/notes", response_model=list[LeadNoteRead])
def list_notes(lead_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    owned_lead(db, current_user.id, lead_id)
    return db.query(LeadNote).filter(LeadNote.lead_id == lead_id, LeadNote.user_id == current_user.id).order_by(LeadNote.created_at.desc()).all()


@router.post("/leads/{lead_id}/notes", response_model=LeadNoteRead, status_code=201)
def create_note(lead_id: str, payload: LeadNoteCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    lead = owned_lead(db, current_user.id, lead_id)
    note = LeadNote(lead_id=lead.id, user_id=current_user.id, body=payload.body.strip())
    db.add(note)
    db.flush()
    record_event(db, "note_created", user=current_user, lead=lead, details={"note_id": note.id})
    db.commit()
    db.refresh(note)
    return note


@router.get("/leads/{lead_id}/timeline", response_model=list[TimelineItem])
def timeline(lead_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    owned_lead(db, current_user.id, lead_id)
    return lead_timeline(db, current_user.id, lead_id)


@router.post("/leads/{lead_id}/outreach/send", response_model=OutreachMessageRead)
def mark_outreach_sent(lead_id: str, payload: OutreachSendRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    lead = owned_lead(db, current_user.id, lead_id)
    message = db.query(OutreachMessage).filter(OutreachMessage.id == payload.message_id, OutreachMessage.lead_id == lead.id, OutreachMessage.user_id == current_user.id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Outreach message not found")
    message.sent_at = datetime.now(timezone.utc)
    message.sent_via = payload.sent_via
    message.sent_by_user_id = current_user.id
    message.follow_up_due_at = payload.follow_up_due_at
    message.delivery_status = "sent"
    previous_status = lead.status
    lead.status = "contacted"
    record_event(db, "outreach_sent", user=current_user, lead=lead, details={"message_id": message.id, "sent_via": message.sent_via})
    if previous_status != lead.status:
        record_event(db, "status_changed", user=current_user, lead=lead, details={"from": previous_status, "to": lead.status})
    db.commit()
    db.refresh(message)
    cache.invalidate_user(current_user.id)
    return message


@router.patch("/outreach/{message_id}", response_model=OutreachMessageRead)
def update_tracking(message_id: str, payload: OutreachMessageUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    message = db.query(OutreachMessage).filter(OutreachMessage.id == message_id, OutreachMessage.user_id == current_user.id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Outreach message not found")
    old_due = message.follow_up_due_at
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(message, key, value)
    if message.follow_up_due_at != old_due:
        lead = owned_lead(db, current_user.id, message.lead_id)
        record_event(db, "follow_up_updated", user=current_user, lead=lead, details={"message_id": message.id, "follow_up_due_at": message.follow_up_due_at.isoformat() if message.follow_up_due_at else None})
    db.commit()
    db.refresh(message)
    return message


@router.get("/reminders/upcoming", response_model=list[ReminderItem])
def reminders(days: int = Query(default=7, ge=1, le=90), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return upcoming_reminders(db, current_user.id, days)
