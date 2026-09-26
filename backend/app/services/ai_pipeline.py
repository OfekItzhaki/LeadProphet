from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from app.ai.prompts import PROMPTS
from app.config import settings
from app.exceptions import PipelineError
from app.models import AICallLog, Campaign, Lead, OutreachMessage
from app.services.events import record_event
from app.services.heuristics import inspect_website
from app.services.scoring import score_campaign_fit
from app.services.enrichment import enrich_lead
from app.services.sequences import select_variants
from app.schemas import ImportedLeadRow
from app.campaign_config import CampaignConfig
from app.services.rules import RuleEngine


class LeadPipeline:
    def __init__(self, db: Session):
        self.db = db
        self.client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    async def process_lead(self, lead: Lead) -> Lead:
        lead.status = "analysis_pending"
        lead.last_error = None
        record_event(self.db, "analysis_started", user_id=lead.user_id, lead=lead)
        self.db.commit()

        try:
            campaign = lead.campaign
            config = CampaignConfig.load(self.db, campaign)
            if not lead.enrichment:
                lead.enrichment = enrich_lead(ImportedLeadRow(
                    business_name=lead.business_name,
                    website_url=lead.website_url,
                    contact_email=lead.contact_email,
                    contact_phone=lead.contact_phone,
                    location_city=lead.location_city,
                    location_country=lead.location_country,
                ))
            heuristics = await inspect_website(lead.website_url)
            lead.tech_stack_detected = heuristics.get("tech_stack", {})

            analysis = await self.analyze(config, lead, heuristics)
            score = await self.score(config, lead, analysis, heuristics)
            outreach = await self.generate_outreach(config, lead, analysis, score)

            lead.ai_analysis = {
                **analysis,
                "score_factors": score.get("factors", {}),
                "icp_fit_score": score.get("icp_fit_score"),
                "icp_explanation": score.get("icp_explanation"),
                "icp_signals": score.get("icp_signals", {}),
            }
            lead.ai_business_summary = analysis["business_description"]
            lead.ai_problem_summary = {"pain_points": analysis["pain_points"]}
            lead.ai_proposed_value = "; ".join(analysis["opportunities_for_services"])
            lead.detected_language = analysis["detected_language"]
            lead.suggested_service_focus = analysis["suggested_service_focus"]
            lead.score = score["score"]
            lead.priority = score["priority"]
            lead.score_reason = score["reason_for_score"]
            lead.risk_flags = score.get("risk_flags", [])
            lead.status = "contact_draft_ready"
            RuleEngine(config).apply(self.db, lead, {"phase": "after_analysis", "score": score})

            for existing_message in list(lead.outreach_messages):
                if existing_message.sequence_step_id is None:
                    lead.outreach_messages.remove(existing_message)
            for message in outreach:
                lead.outreach_messages.append(
                    OutreachMessage(
                        user_id=lead.user_id,
                        campaign_id=campaign.id,
                        channel=message["channel"],
                        language=message["language"],
                        subject=message.get("subject"),
                        ai_draft_body=message["body"],
                        final_body=message["body"],
                        variant_ids=message.get("variant_ids", []),
                    )
                )

            record_event(self.db, "analysis_completed", user_id=lead.user_id, lead=lead, details={"score": lead.score})
            record_event(
                self.db,
                "outreach_generated",
                user_id=lead.user_id,
                lead=lead,
                details={
                    "draft_count": len(outreach),
                    "variant_ids": sorted({variant_id for message in outreach for variant_id in message.get("variant_ids", [])}),
                },
            )
            self.db.commit()
            self.db.refresh(lead)
            return lead
        except Exception as exc:
            lead_id = lead.id
            self.db.rollback()
            lead = self.db.get(Lead, lead_id)
            if not lead:
                raise
            lead.status = "analysis_failed"
            lead.last_error = str(exc)
            self._log_ai_call(lead, lead.campaign, "pipeline", "local", "failed", error=str(exc))
            record_event(self.db, "analysis_failed", user_id=lead.user_id, lead=lead, details={"error": str(exc)[:1000]})
            self.db.commit()
            raise PipelineError("Lead analysis failed", lead_id=lead.id) from exc

    async def analyze(self, campaign: CampaignConfig, lead: Lead, heuristics: dict[str, Any]) -> dict[str, Any]:
        if self.client:
            return await self._openai_json("lead_analyzer", campaign, lead, heuristics)

        notes = (lead.raw_source_reference or {}).get("notes") or (lead.raw_source_reference or {}).get("rough_notes") or ""
        content = f"{lead.business_name} {notes} {heuristics.get('html_excerpt', '')}"
        has_hebrew = any("\u0590" <= char <= "\u05ff" for char in content)
        language = "he" if has_hebrew and "he" in campaign.languages else (campaign.languages[0] if campaign.languages else "en")
        website_quality = "medium" if heuristics.get("available") else "low"
        normalized_content = content.lower().replace("_", " ")
        service_focus = max(
            campaign.services_offered,
            key=lambda service: sum(token in normalized_content for token in service.lower().replace("_", " ").split()),
            default="other",
        )
        pain_points = []
        if not heuristics.get("available"):
            pain_points.append("Website is missing or not reachable, which can reduce trust and inbound leads.")
        if heuristics.get("tech_stack", {}).get("wordpress") or heuristics.get("tech_stack", {}).get("wix"):
            pain_points.append("Online presence may be hard to evolve into faster lead capture or automations.")
        if not pain_points:
            pain_points.append("Current digital funnel may not clearly turn visitors into qualified conversations.")

        result = {
            "business_description": f"{lead.business_name} appears to be a {campaign.vertical} lead in {campaign.region}.",
            "services_or_products": [campaign.vertical],
            "target_customers": "Local or remote customers matching the campaign ICP.",
            "pain_points": pain_points,
            "opportunities_for_services": [
                f"Use {service_focus} to improve conversion, trust, and operational speed.",
                campaign.ai_value_proposition,
            ],
            "suggested_service_focus": service_focus,
            "current_online_presence_quality": {"level": website_quality, "explanation": heuristics.get("notes") or "Basic heuristic review."},
            "detected_language": language,
            "icp_fit_level": "high" if campaign.region.casefold() in (lead.location_country or "").casefold() else "medium",
            "icp_fit_explanation": f"Compared against {', '.join(campaign.icp_firmographics.get('industries', []))} in {', '.join(campaign.icp_firmographics.get('regions', []))}.",
        }
        self._log_ai_call(lead, campaign, "lead_analyzer", "local-fallback", "succeeded")
        return result

    async def score(self, campaign: CampaignConfig, lead: Lead, analysis: dict[str, Any], heuristics: dict[str, Any]) -> dict[str, Any]:
        if self.client:
            return await self._openai_json("lead_scorer", campaign, lead, {"analysis": analysis, "heuristics": heuristics})
        self._log_ai_call(lead, campaign, "lead_scorer", "local-fallback", "succeeded")
        return score_campaign_fit(campaign, lead, analysis, heuristics)

    async def generate_outreach(
        self, campaign: CampaignConfig, lead: Lead, analysis: dict[str, Any], score: dict[str, Any]
    ) -> list[dict]:
        if self.client:
            data = await self._openai_json("outreach_generator", campaign, lead, {"analysis": analysis, "score": score})
            allowed = {(language, channel) for language in campaign.languages for channel in ("email", "whatsapp")}
            messages = [message for message in data["messages"] if (message.get("language"), message.get("channel")) in allowed]
            return self._apply_variants(campaign, messages)

        service = analysis["suggested_service_focus"].replace("_", " ")
        pain = analysis["pain_points"][0]
        tone = campaign.ai_tone_guidelines.lower()
        casual = any(word in tone for word in ("casual", "warm", "friendly"))
        messages: list[dict[str, str]] = []
        if "en" in campaign.languages:
            greeting = "Hi" if casual else "Hello"
            body = (
                f"{greeting} {lead.business_name},\n\n"
                f"I noticed one possible growth bottleneck: {pain}\n\n"
                f"I build {service} solutions for {campaign.vertical} teams, with a focus on practical outcomes: "
                f"{campaign.ai_value_proposition}\n\n"
                "Would it be useful if I sent over 2-3 concrete improvement ideas for your current site or workflow?"
            )
            whatsapp = (
                f"{greeting} {lead.business_name} - I noticed {pain} "
                f"I help {campaign.vertical} teams with {service}. Open to 2-3 practical ideas?"
            )
            messages.extend(
                [
                    {"language": "en", "channel": "email", "subject": f"Quick idea for {lead.business_name}", "body": body},
                    {"language": "en", "channel": "whatsapp", "body": whatsapp},
                ]
            )
        if "he" in campaign.languages:
            greeting = "היי" if casual else "שלום"
            body = (
                f"{greeting} {lead.business_name},\n\n"
                f"שמתי לב לנקודת שיפור אפשרית: {pain}\n\n"
                f"אני בונה פתרונות {service} לעסקים בתחום {campaign.vertical}, עם דגש על תוצאה פרקטית: "
                f"{campaign.ai_value_proposition}\n\n"
                "רוצה שאשלח 2-3 רעיונות קונקרטיים לשיפור האתר או תהליך העבודה שלכם?"
            )
            whatsapp = (
                f"{greeting} {lead.business_name}, שמתי לב לעניין שעשוי לעכב צמיחה: {pain} "
                f"אני עוזר לעסקים בתחום {campaign.vertical} עם {service}. לשלוח 2-3 רעיונות מעשיים?"
            )
            messages.extend(
                [
                    {"language": "he", "channel": "email", "subject": f"רעיון קצר עבור {lead.business_name}", "body": body},
                    {"language": "he", "channel": "whatsapp", "body": whatsapp},
                ]
            )
        self._log_ai_call(lead, campaign, "outreach_generator", "local-fallback", "succeeded")
        return self._apply_variants(campaign, messages)

    def _apply_variants(self, campaign: CampaignConfig, messages: list[dict]) -> list[dict]:
        selected_by_channel = {
            channel: select_variants(self.db, campaign.id, channel)
            for channel in {message["channel"] for message in messages}
        }
        for message in messages:
            variants = selected_by_channel[message["channel"]]
            for variant in variants:
                if variant.variant_key == "subject_line" and message["channel"] == "email":
                    message["subject"] = variant.content
                elif variant.variant_key == "opening_line":
                    message["body"] = f"{variant.content}\n\n{message['body']}"
                elif variant.variant_key == "cta":
                    message["body"] = f"{message['body']}\n\n{variant.content}"
            message["variant_ids"] = [variant.id for variant in variants]
        return messages

    async def _openai_json(self, step_name: str, campaign: CampaignConfig, lead: Lead, context: dict[str, Any]) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("OpenAI client is not configured")
        payload = {
            "campaign": {
                "name": campaign.name,
                "vertical": campaign.vertical,
                "region": campaign.region,
                "languages": campaign.languages,
                "services_offered": campaign.services_offered,
                "icp": campaign.ai_icp_description,
                "value_proposition": campaign.ai_value_proposition,
                "tone": campaign.ai_tone_guidelines,
                "scoring_profile": campaign.scoring_profile,
                "icp_firmographics": campaign.icp_firmographics,
                "icp_technographics": campaign.icp_technographics,
                "icp_pains": campaign.icp_pains,
                "icp_triggers": campaign.icp_triggers,
                "icp_personas": campaign.icp_personas,
            },
            "lead": {
                "business_name": lead.business_name,
                "website_url": lead.website_url,
                "location_city": lead.location_city,
                "location_country": lead.location_country,
                "source_type": lead.source_type,
                "enrichment": lead.enrichment,
            },
            "context": context,
            "requested_outreach": [
                {"language": language, "channel": channel}
                for language in campaign.languages
                for channel in ("email", "whatsapp")
            ],
        }
        response = await self.client.chat.completions.create(
            model=settings.openai_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": PROMPTS[step_name]},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        )
        usage = response.usage
        self._log_ai_call(
            lead,
            lead.campaign,
            step_name,
            settings.openai_model,
            "succeeded",
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
        )
        result = json.loads(response.choices[0].message.content or "{}")
        if step_name == "lead_analyzer":
            if result.get("suggested_service_focus") not in campaign.services_offered:
                result["suggested_service_focus"] = campaign.services_offered[0] if campaign.services_offered else "other"
            if result.get("detected_language") not in campaign.languages:
                result["detected_language"] = campaign.languages[0] if campaign.languages else "en"
            if result.get("icp_fit_level") not in {"high", "medium", "low"}:
                result["icp_fit_level"] = "medium"
            result.setdefault("icp_fit_explanation", "ICP fit was inferred from the supplied campaign and lead evidence.")
        if step_name == "lead_scorer":
            result["score"] = max(0, min(100, int(result["score"])))
            result["priority"] = "high" if result["score"] >= 75 else "medium" if result["score"] >= 50 else "low"
        return result

    def _log_ai_call(
        self,
        lead: Lead | None,
        campaign: Campaign | None,
        step_name: str,
        model: str,
        status: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        error: str | None = None,
    ) -> None:
        self.db.add(
            AICallLog(
                user_id=lead.user_id if lead else (campaign.user_id if campaign else None),
                lead_id=lead.id if lead else None,
                campaign_id=campaign.id if campaign else None,
                step_name=step_name,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                status=status,
                error=error,
            )
        )
