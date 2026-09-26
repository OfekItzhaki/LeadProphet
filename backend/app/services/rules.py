from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.campaign_config import CampaignConfig, RuleConfig
from app.models import Lead, LeadTask, User
from app.services.events import record_event


@dataclass
class RuleResult:
    allowed: bool = True
    reasons: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


class Rule(Protocol):
    def apply(self, db: Session, user: User | None, lead: Lead, config: CampaignConfig, context: dict[str, Any]) -> RuleResult: ...


class MinimumIcpFitRule:
    def __init__(self, rule: RuleConfig): self.threshold = int(rule.params.get("threshold", 60))

    def apply(self, db, user, lead, config, context) -> RuleResult:
        if context.get("phase") != "before_attach" or not context.get("automatic", False): return RuleResult()
        fit = (lead.ai_analysis or {}).get("icp_fit_score")
        if fit is None or int(fit) < self.threshold:
            return RuleResult(False, [f"ICP fit must be at least {self.threshold}"])
        return RuleResult()


class HighScoreCallRule:
    title = "High-priority qualification call"

    def __init__(self, rule: RuleConfig): self.threshold = int(rule.params.get("threshold", 80))

    def apply(self, db, user, lead, config, context) -> RuleResult:
        if context.get("phase") != "after_analysis" or (lead.score or 0) <= self.threshold or lead.pipeline_stage != "new":
            return RuleResult()
        exists = db.query(LeadTask).filter(LeadTask.lead_id == lead.id, LeadTask.user_id == lead.user_id, LeadTask.title == self.title, LeadTask.completed_at.is_(None)).first()
        if not exists:
            db.add(LeadTask(lead_id=lead.id, user_id=lead.user_id, title=self.title, due_date=datetime.now(timezone.utc)))
            return RuleResult(actions=["high_priority_call_created"])
        return RuleResult()


class DuplicateGuardRule:
    def __init__(self, rule: RuleConfig):
        self.rule = rule

    def apply(self, db, user, lead, config, context) -> RuleResult:
        if not lead.duplicate_of_id and lead.status != "duplicate": return RuleResult()
        if lead.pipeline_stage != "lost": lead.pipeline_stage = "lost"
        if context.get("phase") in {"before_attach", "before_advance"}:
            return RuleResult(False, ["Duplicate leads cannot enter or advance through sequences"], ["pipeline_stage_lost"])
        return RuleResult(actions=["pipeline_stage_lost"])


RULE_TYPES = {
    "minimum_icp_fit": MinimumIcpFitRule,
    "high_score_call": HighScoreCallRule,
    "duplicate_guard": DuplicateGuardRule,
}


class RuleEngine:
    def __init__(self, config: CampaignConfig):
        self.config = config
        self.rules = [RULE_TYPES[item.type](item) for item in config.rules if item.enabled]

    def apply(self, db: Session, lead: Lead, context: dict[str, Any], user: User | None = None) -> RuleResult:
        combined = RuleResult()
        for rule in self.rules:
            result = rule.apply(db, user, lead, self.config, context)
            combined.allowed = combined.allowed and result.allowed
            combined.reasons.extend(result.reasons)
            combined.actions.extend(result.actions)
        if combined.reasons or combined.actions:
            record_event(db, "rules_applied", user=user, user_id=lead.user_id if not user else None, lead=lead, details={
                "phase": context.get("phase"), "allowed": combined.allowed,
                "reasons": combined.reasons, "actions": combined.actions,
            })
        return combined
