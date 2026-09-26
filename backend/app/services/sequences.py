from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import Campaign, Lead, LeadTask, MessageVariant, OutreachMessage, Sequence, SequenceStep, User
from app.services.events import record_event
from app.campaign_config import CampaignConfig
from app.services.rules import RuleEngine


def variant_usage(db: Session, campaign_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for (ids,) in db.query(OutreachMessage.variant_ids).filter(OutreachMessage.campaign_id == campaign_id).all():
        for variant_id in ids or []:
            counts[variant_id] = counts.get(variant_id, 0) + 1
    return counts


def select_variants(db: Session, campaign_id: str, channel: str, sequence_id: str | None = None) -> list[MessageVariant]:
    variants = db.query(MessageVariant).filter(
        MessageVariant.campaign_id == campaign_id, MessageVariant.channel == channel, MessageVariant.is_active.is_(True)
    ).filter((MessageVariant.sequence_id == sequence_id) | (MessageVariant.sequence_id.is_(None))).all()
    usage = variant_usage(db, campaign_id)
    selected: list[MessageVariant] = []
    for key in ("subject_line", "opening_line", "cta"):
        choices = [variant for variant in variants if variant.variant_key == key]
        if choices:
            selected.append(min(choices, key=lambda variant: (usage.get(variant.id, 0), variant.created_at, variant.id)))
    return selected


def render_step_email(campaign: Campaign, lead: Lead, step: SequenceStep, variants: list[MessageVariant]) -> OutreachMessage:
    by_key = {variant.variant_key: variant.content for variant in variants}
    subject = by_key.get("subject_line") or step.step_metadata.get("subject") or f"A quick idea for {lead.business_name}"
    opening = by_key.get("opening_line") or f"Hi {lead.business_name},"
    cta = by_key.get("cta") or "Would a short conversation next week be useful?"
    body = f"{opening}\n\n{step.step_metadata.get('body') or campaign.ai_value_proposition}\n\n{cta}"
    return OutreachMessage(
        user_id=lead.user_id, campaign_id=campaign.id, lead_id=lead.id, channel="email", language="en",
        subject=subject, ai_draft_body=body, final_body=body, delivery_status="planned",
        sequence_step_id=step.id, variant_ids=[variant.id for variant in variants],
    )


def materialize_step(db: Session, user: User, campaign: Campaign, lead: Lead, sequence: Sequence, step: SequenceStep):
    due = datetime.now(timezone.utc) + timedelta(days=step.offset_days)
    target_stage = step.step_metadata.get("pipeline_stage")
    allowed_stages = {"new", "qualified", "negotiation", "proposal_sent", "waiting_response", "won", "lost"}
    if target_stage in allowed_stages and target_stage != lead.pipeline_stage:
        previous = lead.pipeline_stage
        lead.pipeline_stage = target_stage
        record_event(db, "pipeline_stage_changed", user=user, lead=lead, details={"from": previous, "to": target_stage, "sequence_step_id": step.id})
    created: OutreachMessage | LeadTask
    if step.channel == "email":
        variants = select_variants(db, campaign.id, "email", sequence.id)
        created = render_step_email(campaign, lead, step, variants)
        db.add(created)
        details = {"sequence_id": sequence.id, "step_id": step.id, "channel": step.channel, "variant_ids": created.variant_ids}
    else:
        defaults = {
            "linkedin": "Send LinkedIn connection or message",
            "call": "Make call",
            "task": "Complete sequence task",
        }
        created = LeadTask(
            user_id=user.id, lead_id=lead.id, title=step.step_metadata.get("title") or defaults[step.channel],
            description=step.step_metadata.get("description"), due_date=due,
        )
        db.add(created)
        details = {"sequence_id": sequence.id, "step_id": step.id, "channel": step.channel}
    record_event(db, "sequence_step_planned", user=user, lead=lead, details=details)
    return created


def attach_sequence(db: Session, user: User, lead: Lead, sequence: Sequence, *, automatic: bool = False):
    if not sequence.steps:
        raise ValueError("Sequence has no steps")
    decision = RuleEngine(CampaignConfig.load(db, sequence.campaign)).apply(
        db, lead, {"phase": "before_attach", "automatic": automatic, "sequence_id": sequence.id}, user
    )
    if not decision.allowed:
        raise ValueError("; ".join(decision.reasons))
    lead.sequence_id = sequence.id
    lead.sequence_position = 0
    created = materialize_step(db, user, sequence.campaign, lead, sequence, sequence.steps[0])
    record_event(db, "sequence_attached", user=user, lead=lead, details={"sequence_id": sequence.id, "position": 0})
    return created


def advance_sequence(db: Session, user: User, lead: Lead, sequence: Sequence):
    decision = RuleEngine(CampaignConfig.load(db, sequence.campaign)).apply(
        db, lead, {"phase": "before_advance", "sequence_id": sequence.id}, user
    )
    if not decision.allowed:
        raise ValueError("; ".join(decision.reasons))
    next_position = (lead.sequence_position if lead.sequence_position is not None else -1) + 1
    if next_position >= len(sequence.steps):
        return None
    lead.sequence_position = next_position
    created = materialize_step(db, user, sequence.campaign, lead, sequence, sequence.steps[next_position])
    record_event(db, "sequence_advanced", user=user, lead=lead, details={"sequence_id": sequence.id, "position": next_position})
    return created
