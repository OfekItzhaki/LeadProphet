from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Event, Lead, LeadNote, LeadTask, OutreachMessage


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def lead_timeline(db: Session, user_id: str, lead_id: str) -> list[dict]:
    items: list[dict] = []
    for event in db.query(Event).filter(Event.user_id == user_id, Event.lead_id == lead_id).all():
        items.append({
            "type": "event", "title": event.event_type.replace("_", " "),
            "timestamp": event.created_at, "details": event.details or {},
        })
    for note in db.query(LeadNote).filter(LeadNote.user_id == user_id, LeadNote.lead_id == lead_id).all():
        items.append({"type": "note", "title": "Note added", "timestamp": note.created_at, "details": {"body": note.body}})
    for task in db.query(LeadTask).filter(
        LeadTask.user_id == user_id, LeadTask.lead_id == lead_id, LeadTask.completed_at.is_not(None)
    ).all():
        items.append({
            "type": "task", "title": "Task completed", "timestamp": task.completed_at,
            "details": {"task_id": task.id, "title": task.title},
        })
    for message in db.query(OutreachMessage).filter(
        OutreachMessage.user_id == user_id, OutreachMessage.lead_id == lead_id, OutreachMessage.sent_at.is_not(None)
    ).all():
        items.append({
            "type": "outreach", "title": "Outreach sent", "timestamp": message.sent_at,
            "details": {"message_id": message.id, "channel": message.channel, "sent_via": message.sent_via},
        })

    def sort_key(item: dict) -> datetime:
        value = item["timestamp"]
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

    return sorted(items, key=sort_key, reverse=True)


def upcoming_reminders(db: Session, user_id: str, days: int = 7) -> list[dict]:
    end = utc_now() + timedelta(days=days)
    tasks = db.query(LeadTask, Lead).join(Lead, Lead.id == LeadTask.lead_id).filter(
        LeadTask.user_id == user_id, LeadTask.completed_at.is_(None), LeadTask.due_date.is_not(None),
        LeadTask.due_date <= end,
    ).all()
    messages = db.query(OutreachMessage, Lead).join(Lead, Lead.id == OutreachMessage.lead_id).filter(
        OutreachMessage.user_id == user_id, OutreachMessage.follow_up_due_at.is_not(None),
        OutreachMessage.follow_up_due_at <= end,
        or_(OutreachMessage.delivery_status.is_(None), OutreachMessage.delivery_status != "followed_up"),
    ).all()
    reminders = [
        {"type": "task", "id": task.id, "lead_id": lead.id, "business_name": lead.business_name,
         "title": task.title, "due_at": task.due_date}
        for task, lead in tasks
    ]
    reminders.extend(
        {"type": "follow_up", "id": message.id, "lead_id": lead.id, "business_name": lead.business_name,
         "title": f"Follow up via {message.sent_via or message.channel}", "due_at": message.follow_up_due_at}
        for message, lead in messages
    )
    return sorted(reminders, key=lambda item: item["due_at"])
