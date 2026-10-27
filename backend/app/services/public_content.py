from sqlalchemy.orm import Session

from app.models import CmsContent, LegalDocument


DEFAULT_CONTENT = {
    "home_hero_title": "Turn good prospects into relevant conversations.",
    "home_hero_body": "LeadProphet brings campaign research, ICP qualification, outreach drafts, and pipeline follow-through into one focused workspace.",
    "about_mission": "LeadProphet helps independent developers, agencies, and founders discover and qualify the right opportunities systematically, instead of relying on indiscriminate cold-email volume.",
    "about_product": "Build ICP-driven campaigns, analyze and score leads with evidence, prepare relevant outreach, and keep every sequence, task, reminder, and pipeline decision in context.",
    "about_team": "LeadProphet was created by an independent developer building practical tools for smarter, more responsible outbound.",
    "about_roadmap": "Provider-backed email delivery and reply tracking\nExpanded search and enrichment integrations\nDeeper experiment and revenue attribution",
}

TERMS_BODY = """## Introduction
These Terms of Service govern access to and use of LeadProphet, a software service for lead research, qualification, outreach preparation, and outbound operations.

## Accounts and access
You must provide accurate account information, protect your credentials, and remain responsible for activity under your account. You may not probe, disrupt, reverse engineer, or misuse the service.

## Subscriptions and usage
Features, usage allowances, and fees may vary by plan. Any paid terms presented at purchase form part of these terms. Unless required by law or stated otherwise, fees are non-refundable.

## Acceptable use
You must comply with privacy, anti-spam, consumer-protection, and communications laws. Do not use LeadProphet for unlawful content, deceptive identity claims, harassment, purchased-list blasting, or abusive outbound behavior.

## Customer data and content
You retain ownership of lead, campaign, and message data you submit. You grant us the limited rights needed to host, process, secure, and display that data to provide the service. You are responsible for having a lawful basis to process and contact prospects.

## Service availability and liability
The service is provided on an as-available basis without guarantees that every lead, score, draft, or integration result is accurate. To the extent permitted by law, indirect and consequential damages are excluded and aggregate liability is limited to fees paid for the service during the preceding twelve months.

## Termination and data
You may stop using the service at any time. We may suspend access for material breach, security risk, or unlawful use. Following termination, account data may remain available for a short export grace period and then be deleted or anonymized, subject to legal and backup obligations.

## Changes
We may update these terms as the product develops. Material changes will be communicated through the service or account contact details, with the effective date and version shown here.
"""

PRIVACY_BODY = """## Introduction and scope
This Privacy Policy explains how LeadProphet collects, uses, stores, and protects information across its web application and related services.

## Data we collect
We process account data such as name and email; authentication and security records; usage logs and product events; contact requests; and campaign, lead, note, task, outreach, and other customer-hosted data.

## Why we use data
We use information to provide and secure the service, authenticate users, operate requested workflows, communicate about support, understand reliability, prevent abuse, and improve features.

## Legal bases
Depending on location and context, processing may rely on performance of a contract, legitimate interests in operating and securing the service, legal obligations, or consent where required. Customers remain responsible for the legal basis covering prospect data they upload.

## Retention
Account and customer data is generally retained while an account is active and for a limited grace period after closure. Security, billing, backup, and legal records may be retained longer where reasonably necessary.

## Processors and transfers
Hosting, authentication, email, analytics, AI, search, and support vendors may process limited data on our behalf. Providers and hosting regions may change. Where data crosses borders, appropriate contractual or legal safeguards should be used.

## Your rights and choices
Subject to applicable law, individuals may request access, correction, deletion, restriction, portability, or objection. Contact the address listed on this site. We may need to verify identity before fulfilling a request.

## Security
LeadProphet uses access controls, scoped tenancy, encrypted transport in production, protected credentials, and operational logging. No system can guarantee absolute security.

## Changes
This policy may be revised as services and legal requirements evolve. Material updates will show a new version and updated date and may be communicated in-product or by email.
"""


def ensure_public_content(db: Session) -> tuple[dict[str, str], dict[str, LegalDocument]]:
    existing = {item.slug: item for item in db.query(CmsContent).all()}
    changed = False
    for slug, body in DEFAULT_CONTENT.items():
        if slug not in existing:
            item = CmsContent(slug=slug, body=body); db.add(item); existing[slug] = item; changed = True
    legal: dict[str, LegalDocument] = {}
    for document_type, body in (("terms_of_service", TERMS_BODY), ("privacy_policy", PRIVACY_BODY)):
        item = db.query(LegalDocument).filter(LegalDocument.document_type == document_type).order_by(LegalDocument.updated_at.desc(), LegalDocument.version.desc()).first()
        if not item:
            item = LegalDocument(document_type=document_type, version="1.0", body=body, is_published=True); db.add(item); changed = True
        elif item.version == "1.0-template":
            item.version = "1.0"
            item.body = item.body.replace(
                "LeadProphet is a software tool for lead research, qualification, outreach preparation, and outbound operations. These terms are a general template and do not constitute legal advice.",
                "These Terms of Service govern access to and use of LeadProphet, a software service for lead research, qualification, outreach preparation, and outbound operations.",
            ).replace(
                "This template describes how LeadProphet handles information across its web application and related services. It is general information, not legal advice.",
                "This Privacy Policy explains how LeadProphet collects, uses, stores, and protects information across its web application and related services.",
            )
            changed = True
        legal[document_type] = item
    if changed: db.commit()
    return {slug: item.body for slug, item in existing.items()}, legal


def paragraphs(body: str) -> list[str]:
    parts: list[str] = []
    for chunk in body.split("\n\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if chunk.startswith("## ") and "\n" in chunk:
            heading, text = chunk.split("\n", 1)
            parts.extend([heading.strip(), text.strip()])
        else:
            parts.append(chunk)
    return parts
