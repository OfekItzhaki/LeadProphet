from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models import Campaign, Lead, MessageVariant, OutreachMessage, Sequence
from app.services.sequences import variant_usage


TRACKED_STATUSES = ("new", "analysis_pending", "contact_draft_ready", "contacted", "responded", "closed_won", "closed_lost", "analysis_failed", "duplicate")


def campaign_metrics(db: Session, user_id: str, campaign_id: str) -> dict:
    status_rows = db.query(Lead.status, func.count(Lead.id)).filter(
        Lead.user_id == user_id, Lead.campaign_id == campaign_id
    ).group_by(Lead.status).all()
    statuses = {status: 0 for status in TRACKED_STATUSES}
    statuses.update({status: count for status, count in status_rows})
    scores = db.query(
        func.count(Lead.id),
        func.avg(Lead.score),
        func.sum(case((Lead.score >= 75, 1), else_=0)),
    ).filter(Lead.user_id == user_id, Lead.campaign_id == campaign_id).one()
    scored = db.query(Lead.score, func.count(Lead.id)).filter(
        Lead.user_id == user_id, Lead.campaign_id == campaign_id, Lead.score.is_not(None)
    ).group_by(Lead.score).all()
    distribution = {"0-49": 0, "50-74": 0, "75-100": 0}
    for score, count in scored:
        bucket = "75-100" if score >= 75 else "50-74" if score >= 50 else "0-49"
        distribution[bucket] += count
    size_rows = db.query(Lead.enrichment).filter(
        Lead.user_id == user_id, Lead.campaign_id == campaign_id
    ).all()
    size_distribution: dict[str, int] = {}
    for (enrichment,) in size_rows:
        size = (enrichment or {}).get("inferred_business_size", "unknown")
        size_distribution[size] = size_distribution.get(size, 0) + 1
    return {
        "campaign_id": campaign_id,
        "total_leads": scores[0] or 0,
        "average_score": round(float(scores[1]), 1) if scores[1] is not None else None,
        "high_priority_leads": scores[2] or 0,
        "leads_by_status": statuses,
        "score_distribution": distribution,
        "business_size_distribution": size_distribution,
    }


def user_metrics(db: Session, user_id: str) -> dict:
    campaigns = db.query(Campaign).filter(Campaign.user_id == user_id).order_by(Campaign.created_at.desc()).all()
    campaign_data = []
    for campaign in campaigns:
        item = campaign_metrics(db, user_id, campaign.id)
        item.update({"name": campaign.name, "active": campaign.is_active})
        campaign_data.append(item)
    statuses = {status: 0 for status in TRACKED_STATUSES}
    for item in campaign_data:
        for status, count in item["leads_by_status"].items():
            statuses[status] = statuses.get(status, 0) + count
    return {
        "campaign_count": len(campaigns),
        "total_leads": sum(item["total_leads"] for item in campaign_data),
        "high_priority_leads": sum(item["high_priority_leads"] for item in campaign_data),
        "leads_by_status": statuses,
        "campaigns": campaign_data,
    }


def sequence_metrics(db: Session, user_id: str, sequence: Sequence) -> dict:
    rows = db.query(Lead.sequence_position, func.count(Lead.id)).filter(
        Lead.user_id == user_id, Lead.sequence_id == sequence.id
    ).group_by(Lead.sequence_position).all()
    distribution = {str(position): count for position, count in rows}
    return {
        "sequence_id": sequence.id,
        "name": sequence.name,
        "lead_count": sum(distribution.values()),
        "step_distribution": distribution,
        "steps": [{"order_index": step.order_index, "channel": step.channel, "lead_count": distribution.get(str(step.order_index), 0)} for step in sequence.steps],
    }


def variant_metrics(db: Session, user_id: str, campaign_id: str) -> list[dict]:
    variants = db.query(MessageVariant).filter(MessageVariant.user_id == user_id, MessageVariant.campaign_id == campaign_id).order_by(MessageVariant.created_at).all()
    usage = variant_usage(db, campaign_id)
    positive: dict[str, int] = {}
    rows = db.query(OutreachMessage.variant_ids, Lead.pipeline_stage, Lead.status).join(Lead, Lead.id == OutreachMessage.lead_id).filter(
        OutreachMessage.user_id == user_id, OutreachMessage.campaign_id == campaign_id
    ).all()
    for ids, stage, status in rows:
        if stage == "won" or status in ("responded", "closed_won"):
            for variant_id in ids or []: positive[variant_id] = positive.get(variant_id, 0) + 1
    return [{
        "id": variant.id, "campaign_id": variant.campaign_id, "sequence_id": variant.sequence_id,
        "channel": variant.channel, "variant_key": variant.variant_key, "content": variant.content,
        "is_active": variant.is_active, "created_at": variant.created_at, "updated_at": variant.updated_at,
        "times_used": usage.get(variant.id, 0), "positive_outcomes": positive.get(variant.id, 0),
    } for variant in variants]


def outbound_campaign_metrics(db: Session, user_id: str, campaign_id: str) -> dict:
    stage_rows = db.query(Lead.pipeline_stage, func.count(Lead.id)).filter(
        Lead.user_id == user_id, Lead.campaign_id == campaign_id
    ).group_by(Lead.pipeline_stage).all()
    sent_rows = db.query(OutreachMessage.channel, func.count(OutreachMessage.id)).filter(
        OutreachMessage.user_id == user_id, OutreachMessage.campaign_id == campaign_id,
        OutreachMessage.sent_at.is_not(None),
    ).group_by(OutreachMessage.channel).all()
    sequences = db.query(Sequence).filter(Sequence.user_id == user_id, Sequence.campaign_id == campaign_id).all()
    sequence_data = [sequence_metrics(db, user_id, sequence) for sequence in sequences]
    icp_distribution = {"low": 0, "medium": 0, "high": 0, "unscored": 0}
    for (analysis,) in db.query(Lead.ai_analysis).filter(Lead.user_id == user_id, Lead.campaign_id == campaign_id).all():
        fit = (analysis or {}).get("icp_fit_score")
        bucket = "unscored" if fit is None else "high" if fit >= 75 else "medium" if fit >= 50 else "low"
        icp_distribution[bucket] += 1
    return {
        "campaign_id": campaign_id,
        "leads_attached_to_sequences": db.query(func.count(Lead.id)).filter(Lead.user_id == user_id, Lead.campaign_id == campaign_id, Lead.sequence_id.is_not(None)).scalar() or 0,
        "pipeline_stages": {stage: count for stage, count in stage_rows},
        "icp_fit_distribution": icp_distribution,
        "sent_by_channel": {channel: count for channel, count in sent_rows},
        "sequences": sequence_data,
        "variants": variant_metrics(db, user_id, campaign_id),
    }
