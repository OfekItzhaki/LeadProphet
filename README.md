# LeadProphet

LeadProphet is a campaign-driven lead generation and outreach engine. It is designed so each campaign defines its vertical, region, ICP, services, scoring rules, languages, lead sources, and outreach tone while the core pipeline stays generic.

## LeadProphet 1.0

- FastAPI backend with server-rendered dashboard
- SQLAlchemy 2.0 models for campaigns, leads, outreach templates, outreach messages, and AI call logs
- Alembic migration for the initial PostgreSQL schema
- Manual lead creation flow
- Campaign-aware analyzer, scorer, and outreach generator
- Deterministic local AI fallback when `OPENAI_API_KEY` is not set
- Google OpenID Connect login with LeadProphet access and rotating refresh tokens
- Per-user campaigns, leads, outreach, AI logs, and cache keys
- Database-backed refresh-session revocation and strict ownership checks
- Campaign create/edit UI with configurable vertical, region, languages, services, ICP, tone, and search patterns
- Validated CSV ingestion and a deterministic search-provider stub
- Externalized campaign-aware AI prompts and optional ingestion-to-analysis orchestration
- Per-user and per-campaign metrics backed by structured lifecycle events
- Factor-based campaign scoring with transparent score reasons and custom weights
- Lead deduplication by domain, contact email, or normalized business/location
- Internal domain and business-size enrichment with an external-provider hook
- Daily triage filters, bulk analysis/contact actions, duplicate clusters, and recent activity
- A sales pipeline stage independent from processing status
- Lead tasks, notes, activity timelines, sent-outreach tracking, and follow-up reminders
- Structured ICP firmographics, technographics, pains, triggers, and target personas
- Ordered multichannel sequences that plan email drafts and LinkedIn, call, or research tasks
- Balanced messaging variants with usage and positive-outcome attribution
- Campaign and sequence outbound metrics for pipeline, cadence position, and sent channels
- Validated `CampaignConfig` as the shared input to discovery, analysis, scoring, outreach, and rules
- Configurable decision rules for ICP gates, high-score call tasks, and duplicate protection
- A default Daily view and campaign cockpit for repeated outbound work
- Runtime-selected email, search, and enrichment provider interfaces with deterministic defaults
- Dev/test identity, deep integration tests, synthetic demo data, and a local load harness
- Public Home, About, Contact, and Legal pages with CMS-backed copy and versioned legal templates
- Persisted contact requests with validation, event logging, and optional provider notification

## Run Locally

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m alembic upgrade head
python scripts/seed_demo_data.py --email demo@leadprophet.local --leads 100
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

## Owner Go-Live Workflow

After sign-in, open `/setup` for named required, recommended, and optional readiness checks. `/settings` manages the deployment-wide public profile and reports environment, OAuth, email, database, version, and migration state without storing provider secrets. `/campaigns/wizard` creates a complete starter campaign with ICP, scoring, sequence, and variant defaults.

Use `/settings/portability` to export or additively import campaign and site-content JSON bundles, publish legal versions, or reset deterministic sandbox data in local/test/demo environments. Imports never overwrite existing records and campaign records are always scoped to the current owner. See [OPERATIONS.md](OPERATIONS.md) for the operating checklist.

## Public Website And Content

Public routes are available without authentication:

- `/` and `/home`: product landing page.
- `/about`: mission, product, team, and roadmap content.
- `/contact`: contact details, validated contact form, and FAQ.
- `/legal`: versioned Terms of Service and Privacy Policy templates.

The authenticated operating dashboard is at `/daily`. Successful Google login redirects there.

Marketing copy is stored in `cms_content` and initialized on first public request. Owners can retrieve and update copy without editing templates:

```bash
curl http://127.0.0.1:8000/api/cms/about_mission
curl -X PUT http://127.0.0.1:8000/api/cms/about_mission \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"body":"Updated mission copy"}'
```

Built-in slugs are `home_hero_title`, `home_hero_body`, `about_mission`, `about_product`, `about_team`, and `about_roadmap`. Additional slugs can be created through the same owner-only endpoint.

Terms and privacy content is stored in `legal_documents`. Public retrieval uses `GET /api/legal/{document_type}`; owners publish a version with `PUT /api/legal/{document_type}` and a JSON body containing `version` and `body`. Supported document types are `terms_of_service` and `privacy_policy`. The supplied text is explicitly a general template, not legal advice.

Contact submissions are validated and stored in `contact_messages` with `new` status, optional authenticated `user_id`, and a `contact_message_created` event. The default email stub never sends externally. Set `EMAIL_PROVIDER=smtp` and the SMTP fields described in [OPERATIONS.md](OPERATIONS.md) to send contact notifications. Campaign outreach and reply fetching remain manual.

Configure public details in `.env`:

```env
PUBLIC_CONTACT_EMAIL=hello@leadprophet.app
PUBLIC_CONTACT_PHONE=
PUBLIC_CONTACT_CITY=Netanya, Israel
PUBLIC_CONTACT_TIMEZONE=Asia/Jerusalem
PUBLIC_RESPONSE_HOURS=24-48 hours on weekdays
ADMIN_NOTIFICATION_EMAIL=
```

The dashboard shows a Google login screen until authentication succeeds. API clients send the access token as `Authorization: Bearer <token>`. The browser UI keeps both tokens in `HttpOnly`, `SameSite=Lax` cookies so scripts cannot read them; this is safer than local storage and still uses the same JWT access token.

## Google OAuth Setup

1. In Google Cloud Console, create an OAuth 2.0 Client ID with application type **Web application**.
2. Add `http://127.0.0.1:8000/auth/google/callback` as an authorized redirect URI. The host must exactly match the one used in the browser.
3. Set the following values in `backend/.env`:

```env
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/auth/google/callback
JWT_SECRET_KEY=generate-a-long-random-secret-here
FRONTEND_ORIGIN=http://127.0.0.1:8000
```

Google is used only to establish identity. The callback verifies Google OpenID Connect claims, upserts the user by normalized email, and creates LeadProphet-owned sessions. Access tokens expire after 30 minutes by default; refresh tokens expire after 14 days, are stored only as SHA-256 hashes, rotate on use, and are revoked on logout.

## Data Ownership

Every campaign, lead, outreach template, and outreach message has a required `user_id`. AI logs also retain user context. API and UI lookups include that owner ID, including nested operations such as creating a lead under a campaign or running analysis. Migration `0002_auth_multitenancy` assigns pre-auth MVP rows to a legacy workspace account so existing data is preserved.

The process-local TTL cache uses keys such as `user:<user_id>:campaigns:list`. Its small interface in `backend/app/services/cache.py` is intentionally replaceable with Redis when multiple application processes are introduced.

## Lead Quality

Every newly created lead runs through the same creation service, whether it came from the API, UI, CSV, or search stub. The service adds internal enrichment and checks canonical leads in the same user/campaign using these signals, in order:

- normalized website domain
- case-insensitive contact email
- normalized business name plus city/country

Duplicates are preserved for auditability with `status=duplicate` and `duplicate_of_id` pointing to the canonical lead. `GET /campaigns/{id}/duplicates` returns grouped clusters. Duplicate rows are excluded from batch analysis.

Enrichment currently derives domain, TLD, country-TLD usage, domain keywords, contact availability, and an inferred business-size category. Add external providers through `EnrichmentProvider` in `backend/app/providers/enrichment.py` without changing ingestion.

Scoring uses normalized factors for website quality, location, ICP/service fit, pain points, language, and inferred business-size fit. Campaigns can override weights with:

```json
{
  "version": 2,
  "weights": {
    "website_quality": 15,
    "location_match": 20,
    "icp_match": 25,
    "pain_points": 20,
    "language_match": 10,
    "business_size_fit": 10
  },
  "priority_thresholds": {"high": 75, "medium": 50}
}
```

## Production Configuration

Set `APP_ENV=production`, use PostgreSQL, serve only over HTTPS, and provide a unique `JWT_SECRET_KEY`. Local development uses a process-ephemeral JWT secret when none is provided; production refuses to start without an explicit secret. Production mode marks auth cookies secure and removes `/docs` and `/redoc`. `CORS_ALLOWED_ORIGINS` accepts a comma-separated allowlist, `COOKIE_SAMESITE` configures session cookies, and `DOCS_ENABLED` controls docs in non-production environments. Secrets belong in the deployment secret store, never source control.

API errors use a stable JSON envelope with `detail` and `code`. Validation responses also include field-level `errors`; AI failures use `code=pipeline_error` and preserve the failed lead ID.

### Authlib transport and JOSE status

The previous warning came from Authlib 1.8's `authlib.integrations.httpx_client._compat`: when `httpx2` was absent, it fell back to legacy `httpx` and emitted `AuthlibDeprecationWarning`. v0.3 installs `httpx2>=2,<3`, which removes that warning while retaining `httpx` for LeadProphet's website inspection.

LeadProphet's session JWTs use PyJWT, not `authlib.jose`, so no application JOSE migration is currently required. Authlib's Google OIDC client internally uses its supported `joserfc` dependency. If application code later imports `authlib.jose`, migrate that code to `joserfc` following the [Authlib migration guide](https://docs.authlib.org/en/latest/upgrades/jose.html); do not introduce new `authlib.jose` usage.

Run the automated ownership and refresh-token checks with:

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

For PostgreSQL, set `DATABASE_URL` in `backend/.env`, for example:

```env
DATABASE_URL=postgresql+psycopg://leadprophet:leadprophet@localhost:5432/leadprophet
```

## Campaigns

A campaign owns the business context used by the pipeline:

- vertical and region
- languages such as `["he", "en"]`
- services offered such as `["web_app_rebuild", "ai_automation", "mvp_build"]`
- search patterns and enabled lead sources
- ICP, value proposition, and tone guidelines
- scoring profile weights and rules

Adding a new vertical should usually mean creating a new campaign and templates, not changing pipeline code.

### Unified Campaign Config

`CampaignConfig` in `backend/app/campaign_config.py` is the validated operating definition for a campaign. It combines ICP descriptors, scoring, enabled sources, search patterns, AI context, decision rules, sequences, and variants. Legacy campaigns are normalized from their vertical, region, and narrative ICP; new or updated campaigns are validated before commit. Discovery, analysis, scoring, outreach, and sequence decisions consume this abstraction rather than assembling independent settings.

Campaign rules are stored as JSON and compiled by `RuleEngine`. Supported rules are:

- `minimum_icp_fit`: blocks automatic sequence attachment below a configurable threshold.
- `high_score_call`: creates one due call task after analysis when score exceeds its threshold.
- `duplicate_guard`: moves duplicates out of the active pipeline and blocks sequence attachment or advancement.

When `campaign_rules` is empty, LeadProphet uses conservative defaults for all three rules. Rule outcomes are persisted as `rules_applied` events.

### ICP Configuration

Each campaign stores an explicit Ideal Customer Profile: target industries, regions and company sizes; expected technologies; pains; buying triggers; and target personas. Analysis compares lead enrichment, location, detected technology, service fit, and pain evidence against these fields. Lead detail shows an independent ICP fit score from 0 to 100 with match and miss reasons.

The campaign page includes the ICP editor. API clients provide `icp_firmographics`, `icp_technographics`, `icp_pains`, `icp_triggers`, and `icp_personas` through the normal campaign create or update endpoints.

## Sequences And Variants

Sequences are ordered campaign cadences across `email`, `linkedin`, `call`, and `task` steps. Attaching a sequence to a lead plans step zero. Advancing plans the next step: email creates a manual-send draft, while other channels create a dated lead task. A step can include `metadata.pipeline_stage` to move the lead as the cadence progresses.

```json
{
  "name": "Founder cadence",
  "steps": [
    {"order_index": 0, "channel": "email", "offset_days": 0, "metadata": {"pipeline_stage": "qualified"}},
    {"order_index": 1, "channel": "linkedin", "offset_days": 2, "metadata": {"title": "Connect with founder"}},
    {"order_index": 2, "channel": "call", "offset_days": 5, "metadata": {"title": "Call founder", "pipeline_stage": "waiting_response"}}
  ]
}
```

Message variants target `subject_line`, `opening_line`, or `cta` for a channel. LeadProphet selects the least-used active variant per element, tags drafts with its IDs, and reports usage. A positive outcome currently means the attributed lead reached `responded`, `won`, or `closed_won`.

Daily flow: create an ICP-driven campaign, define variants and a sequence, import and analyze leads, attach qualified leads to the sequence, then work tasks and advance steps from each lead page.

Campaigns can be created and edited from the dashboard. API clients use `POST /api/campaigns`, `PUT /api/campaigns/{id}`, and `DELETE /api/campaigns/{id}`. Delete currently deactivates a campaign so its lead history and metrics remain available.

## Lead Ingestion

CSV files must be UTF-8, no larger than 2 MB, and include `business_name`. Supported optional columns are `website_url`, `contact_email`, `contact_phone`, `location_city`, `location_country`, and `notes`. Invalid rows are skipped and returned with row-specific errors.

```bash
curl -X POST http://127.0.0.1:8000/campaigns/CAMPAIGN_ID/leads/import-csv \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -F "file=@leads.csv"
```

Search discovery uses campaign search patterns and deterministic `.example` prospects, making the whole flow testable without external services:

```bash
curl -X POST http://127.0.0.1:8000/campaigns/CAMPAIGN_ID/leads/discover-from-search \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

Both endpoints create leads in `new` status for the existing scoped batch processor. Add `?analyze=true` to synchronously run website inspection, analysis, scoring, and outreach immediately. The `LeadSource` interface in `backend/app/services/lead_sources.py` is the adapter boundary for a future Google, Bing, or directory provider.

## AI Pipeline

Prompts live in `backend/app/ai/prompts.py`. Every request includes campaign ICP, value proposition, tone, languages, services, scoring profile, lead data, and website heuristics. The analyzer constrains service focus and language to campaign configuration; the scorer applies campaign weights; outreach produces email and WhatsApp drafts for every supported Hebrew/English language.

When no `OPENAI_API_KEY` is configured, the deterministic local pipeline remains available. Pipeline lifecycle and failures are persisted in `events`, while model usage remains in `ai_call_logs`.

## Metrics

`GET /metrics/summary` returns campaign count, total and high-priority leads, statuses, and per-campaign aggregates for the authenticated user. `GET /campaigns/{id}/metrics` adds average score and score distribution for one owned campaign. The dashboard and campaign detail views show the same aggregates.

## Daily View And Campaign Cockpit

The signed-in home page is the Daily view. It prioritizes high-score leads without sent outreach, incomplete tasks due today or overdue, seven-day reminders, and sequence steps scheduled today from cadence offsets. Campaign pages are cockpits with ICP configuration, status and stage metrics, ICP-fit distribution, sequence utilization, CSV import, deterministic discovery, bulk analysis, and bulk sequence attachment.

## Provider Interfaces

Provider contracts live in `backend/app/providers`:

- `EmailProvider.send()` defaults to a no-send stub, with optional SMTP delivery for contact notifications. `fetch_replies()` remains a no-op.
- `SearchProvider.search_businesses()` defaults to deterministic synthetic results.
- `EnrichmentProvider.enrich_lead()` defaults to internal domain and business-size heuristics.

Select providers with `EMAIL_PROVIDER`, `SEARCH_PROVIDER`, and `ENRICHMENT_PROVIDER`. Unknown configured providers fail explicitly until their adapter is installed. Credentials use the corresponding environment variables; core campaign and lead logic has no provider-specific imports.

## Testing And Synthetic Data

See [TESTING.md](TESTING.md) for the backend and Playwright test matrix, test-only identity, reusable seed utility, and commands. The dev/test-only `POST /auth/dev/test-login` endpoint issues normal JWT sessions for the seeded test users, is omitted from OpenAPI, and returns 404 outside local/development/test environments. Playwright runs against an isolated resettable SQLite database on port 8005.

`scripts/seed_demo_data.py` creates two campaigns with different ICPs and 200 synthetic leads by default. `scripts/load_test.py` measures deterministic pipeline latency and throughput against seeded unprocessed leads.

```bash
curl http://127.0.0.1:8000/metrics/summary \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

## Daily Triage

Campaign lead lists provide views for high-priority leads, leads needing outreach, duplicates, and failed analysis. “Run analysis on new” processes canonical new/failed leads for that campaign. Select rows and use “Mark selected contacted” for a scoped bulk status update.

```bash
curl -X POST http://127.0.0.1:8000/campaigns/CAMPAIGN_ID/leads/analyze-new \
  -H "Authorization: Bearer ACCESS_TOKEN"

curl -X POST http://127.0.0.1:8000/campaigns/CAMPAIGN_ID/leads/mark-contacted \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"lead_ids":["LEAD_ID"]}'
```

### v0.4 Daily Workflow

1. Open the dashboard and work through tasks and follow-ups due in the next seven days.
2. Open a lead, move its pipeline stage independently of processing status, and add notes or tasks.
3. Review an outreach draft, send it externally, then use **Mark sent** to record the channel and next follow-up date.
4. Use the lead timeline as the chronological record of stage, status, outreach, note, and task activity.

Pipeline stages are `new`, `qualified`, `negotiation`, `proposal_sent`, `waiting_response`, `won`, and `lost`. Processing status remains available for analysis and delivery state.

## Events

Standard lifecycle events include `lead_created`, `lead_imported_csv`, `lead_discovered_stub`, `analysis_started`, `analysis_completed`, `analysis_failed`, `outreach_generated`, `status_changed`, `login`, `logout`, and `refresh_failed`.

- `GET /events/recent?limit=20&campaign_id=...` returns the authenticated user's activity.
- `GET /events/stats?campaign_id=...` returns counts grouped by event type.

## Example Workflows

**CSV outreach:** create a campaign in the dashboard, upload a UTF-8 CSV, filter to new leads, run campaign analysis, review each score reason, copy an outreach draft, then mark selected leads contacted.

**Search triage:** add campaign search patterns, run search discovery, inspect duplicate clusters, analyze canonical new leads, then use the high-priority and needs-outreach views for daily follow-up.

## Vertical Slice

1. Create or seed a campaign.
2. Add a manual lead for that campaign.
3. Run analysis from the lead detail page or via the API.
4. Review score, priority, summaries, and generated Hebrew/English outreach drafts.

Useful endpoints:

- `GET /auth/google/login`
- `GET /auth/google/callback`
- `POST /auth/refresh`
- `POST /auth/logout`
- `GET /me`
- `GET /api/campaigns`
- `POST /api/campaigns`
- `GET /api/leads`
- `POST /api/leads`
- `POST /api/leads/{lead_id}/analyze`
- `PATCH /api/leads/{lead_id}/pipeline-stage`
- `PATCH /api/leads/pipeline-stage/bulk`
- `GET|POST /api/leads/{lead_id}/tasks`
- `PATCH|DELETE /api/tasks/{task_id}`
- `GET|POST /api/leads/{lead_id}/notes`
- `GET /api/leads/{lead_id}/timeline`
- `POST /api/leads/{lead_id}/outreach/send`
- `PATCH /api/outreach/{message_id}`
- `GET /api/reminders/upcoming?days=7`
- `POST|GET /campaigns/{campaign_id}/sequences`
- `GET|PATCH /sequences/{sequence_id}`
- `POST /leads/{lead_id}/attach-sequence/{sequence_id}`
- `POST /leads/{lead_id}/advance-sequence`
- `POST|GET /campaigns/{campaign_id}/variants`
- `PATCH /variants/{variant_id}`
- `GET /campaigns/{campaign_id}/outbound-metrics`
- `GET /sequences/{sequence_id}/metrics`
- `POST /api/jobs/process-new-leads`
- `GET /api/outreach/messages`
- `POST /campaigns/{campaign_id}/leads/import-csv`
- `POST /campaigns/{campaign_id}/leads/discover-from-search`
- `GET /metrics/summary`
- `GET /campaigns/{campaign_id}/metrics`
- `GET /campaigns/{campaign_id}/duplicates`
- `POST /campaigns/{campaign_id}/leads/analyze-new`
- `POST /campaigns/{campaign_id}/leads/mark-contacted`
- `GET /events/recent`
- `GET /events/stats`
