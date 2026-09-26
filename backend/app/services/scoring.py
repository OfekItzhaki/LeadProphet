from typing import Any

from app.campaign_config import CampaignConfig
from app.models import Campaign, Lead


DEFAULT_SCORING_PROFILE = {
    "version": 2,
    "weights": {
        "website_quality": 15,
        "location_match": 20,
        "icp_match": 25,
        "pain_points": 20,
        "language_match": 10,
        "business_size_fit": 10,
    },
    "priority_thresholds": {"high": 75, "medium": 50},
}


def resolved_profile(raw_profile: dict | None) -> dict:
    profile = raw_profile or {}
    supplied_weights = profile.get("weights") if isinstance(profile.get("weights"), dict) else {}
    weights = {**DEFAULT_SCORING_PROFILE["weights"], **supplied_weights}
    weights = {key: max(0.0, float(value)) for key, value in weights.items()}
    thresholds = {**DEFAULT_SCORING_PROFILE["priority_thresholds"], **(profile.get("priority_thresholds") or {})}
    return {"version": 2, "weights": weights, "priority_thresholds": thresholds}


def score_campaign_fit(
    campaign: Campaign | CampaignConfig,
    lead: Lead,
    analysis: dict[str, Any],
    heuristics: dict[str, Any],
) -> dict[str, Any]:
    profile = resolved_profile(campaign.scoring_profile)
    weights = profile["weights"]
    website_quality = 0.2
    if heuristics.get("available"):
        website_quality = 0.7 + (0.2 if heuristics.get("uses_https") else 0) + (
            0.1 if lead.enrichment.get("domain") else 0
        )

    country = (lead.location_country or "").casefold()
    region = campaign.region.casefold()
    location_match = 1.0 if region and (region in country or country in region) else (0.45 if lead.location_city else 0.15)

    service_match = analysis.get("suggested_service_focus") in campaign.services_offered
    vertical_terms = [term for term in campaign.vertical.casefold().replace("_", " ").split() if len(term) > 2]
    description = str(analysis.get("business_description", "")).casefold()
    vertical_match = any(term in description for term in vertical_terms)
    firmographics = campaign.icp_firmographics or {}
    target_industries = firmographics.get("industries") or firmographics.get("industry") or []
    if isinstance(target_industries, str):
        target_industries = [target_industries]
    target_regions = firmographics.get("regions") or firmographics.get("region") or []
    if isinstance(target_regions, str):
        target_regions = [target_regions]
    target_sizes = firmographics.get("company_sizes") or firmographics.get("company_size") or []
    if isinstance(target_sizes, str):
        target_sizes = [target_sizes]
    inferred_size = lead.enrichment.get("inferred_business_size", "unknown")
    industry_match = not target_industries or any(str(item).casefold() in description for item in target_industries)
    region_match = not target_regions or any(str(item).casefold() in f"{lead.location_city} {lead.location_country}".casefold() for item in target_regions)
    size_match = not target_sizes or inferred_size in target_sizes
    desired_tech = {str(item).casefold() for item in (campaign.icp_technographics or {}).get("technologies", [])}
    observed_tech = {str(key).casefold() for key, value in (lead.tech_stack_detected or {}).items() if value}
    tech_match = not desired_tech or bool(desired_tech & observed_tech)
    desired_pains = [str(item).casefold() for item in (campaign.icp_pains or [])]
    analyzed_pains = " ".join(map(str, analysis.get("pain_points") or [])).casefold()
    icp_pain_match = not desired_pains or any(pain in analyzed_pains or any(word in analyzed_pains for word in pain.split()) for pain in desired_pains)
    icp_signals = {
        "industry": industry_match, "region": region_match, "company_size": size_match,
        "technographics": tech_match, "pain": icp_pain_match, "service": service_match or vertical_match,
    }
    icp_match = sum(icp_signals.values()) / len(icp_signals)

    pain_points = analysis.get("pain_points") or []
    pain_count = min(len(pain_points) / 3, 1.0)
    intensity_terms = ("missing", "failed", "manual", "outdated", "bottleneck", "unreachable")
    intensity = 1.0 if any(term in " ".join(map(str, pain_points)).casefold() for term in intensity_terms) else 0.5
    pain_factor = min(1.0, pain_count * 0.7 + intensity * 0.3)

    language_match = 1.0 if analysis.get("detected_language") in campaign.languages else 0.0
    icp_text = campaign.ai_icp_description.casefold()
    size_fit = 1.0 if (
        (inferred_size == "small_business" and any(term in icp_text for term in ("small", "smb", "local", "independent")))
        or (inferred_size == "larger_org" and any(term in icp_text for term in ("enterprise", "large", "corporate")))
    ) else 0.55

    factors = {
        "website_quality": min(1.0, website_quality),
        "location_match": min(1.0, location_match),
        "icp_match": min(1.0, icp_match),
        "pain_points": min(1.0, pain_factor),
        "language_match": language_match,
        "business_size_fit": size_fit,
    }
    total_weight = sum(weights.values()) or 1.0
    contributions = {key: round(factors[key] * weights[key], 2) for key in weights}
    score = round(sum(contributions.values()) / total_weight * 100)
    score = max(0, min(100, score))
    thresholds = profile["priority_thresholds"]
    priority = "high" if score >= int(thresholds["high"]) else "medium" if score >= int(thresholds["medium"]) else "low"
    strongest = sorted(contributions, key=contributions.get, reverse=True)[:4]
    reason = f"ICP fit {round(icp_match * 100)}%; " + "; ".join(
        f"{name.replace('_', ' ')} {round(factors[name] * 100)}% ({contributions[name]:g} pts)"
        for name in strongest
    )
    return {
        "score": score,
        "priority": priority,
        "reason_for_score": reason + ".",
        "risk_flags": [name.replace("_", " ") for name, value in factors.items() if value < 0.35],
        "factors": factors,
        "icp_fit_score": round(icp_match * 100),
        "icp_explanation": "Matches ICP on " + ", ".join(name.replace("_", " ") for name, matched in icp_signals.items() if matched) + "; misses " + ", ".join(name.replace("_", " ") for name, matched in icp_signals.items() if not matched) + ".",
        "icp_signals": icp_signals,
        "profile_version": profile["version"],
    }
