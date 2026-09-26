from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import Event, Lead, LeadTask, OutreachMessage, Sequence


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def daily_view(db: Session, user_id: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    tasks = db.query(LeadTask, Lead).join(Lead, Lead.id == LeadTask.lead_id).filter(
        LeadTask.user_id == user_id, LeadTask.completed_at.is_(None), LeadTask.due_date.is_not(None), LeadTask.due_date < day_end
    ).order_by(LeadTask.due_date).all()
    action_leads = db.query(Lead).filter(
        Lead.user_id == user_id, Lead.priority == "high", Lead.duplicate_of_id.is_(None),
        ~Lead.outreach_messages.any(OutreachMessage.sent_at.is_not(None)),
    ).order_by(Lead.score.desc()).all()
    attached = db.query(Lead).filter(Lead.user_id == user_id, Lead.sequence_id.is_not(None), Lead.sequence_position.is_not(None)).all()
    sequence_steps = []
    for lead in attached:
        sequence = db.query(Sequence).filter(Sequence.id == lead.sequence_id, Sequence.user_id == user_id).first()
        if not sequence or lead.sequence_position is None or lead.sequence_position >= len(sequence.steps):
            continue
        event = db.query(Event).filter(Event.user_id == user_id, Event.lead_id == lead.id, Event.event_type == "sequence_attached").order_by(Event.created_at.desc()).first()
        anchor = _aware(event.created_at if event else lead.updated_at)
        step = sequence.steps[lead.sequence_position]
        scheduled_at = anchor + timedelta(days=step.offset_days)
        if day_start <= scheduled_at < day_end:
            sequence_steps.append({"lead": lead, "sequence": sequence, "step": step, "scheduled_at": scheduled_at})
    return {
        "tasks": [{"task": task, "lead": lead} for task, lead in tasks],
        "action_leads": action_leads,
        "sequence_steps": sorted(sequence_steps, key=lambda item: item["scheduled_at"]),
        "date": day_start,
    }
