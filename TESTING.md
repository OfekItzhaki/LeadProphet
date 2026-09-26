# Testing LeadProphet

Install development dependencies and run the complete suite from `backend`:

```bash
pip install -r requirements-dev.txt
python -m alembic upgrade head
python -m alembic check
python -m pytest -q
```

The suite uses temporary SQLite databases and deterministic providers. It covers JWT and refresh rotation, Google callback mocking, tenant isolation, campaign and ICP configuration, CSV validation, search discovery, analysis/scoring/outreach, deduplication, pipeline stages, sequences, variants, tasks, notes, reminders, timelines, metrics, provider stubs, rule decisions, UI rendering, and simulated AI failure.

## Test Identity

`create_test_user_if_not_exists()` creates `test+leadprophet@example.com` with role `test`. In `local`, `development`, or `test` environments, `POST /auth/dev/test-login` issues normal access and refresh credentials for that account. The route is hidden from OpenAPI and returns 404 in production.

Shared integration data is available through `tests/utils/seed_data.py`. It creates two tenant-scoped campaigns with different ICPs plus leads, sequences, variants, tasks, notes, reminders, and events.

## Demo And Load Data

```bash
python scripts/seed_demo_data.py --leads 100
python scripts/load_test.py --limit 25
```

The demo seed is idempotent and creates 200 synthetic leads across two campaigns by default. The load script runs the configured pipeline; leave `OPENAI_API_KEY` empty for deterministic local performance measurements.

## Playwright E2E

From the repository root:

```bash
npm install
npx playwright install chromium
npm run test:e2e
```

Useful modes are `npm run test:e2e:headed`, `npm run test:e2e:ui`, and `npm run test:e2e:report`.

Playwright starts FastAPI on `127.0.0.1:8005` with `APP_ENV=test` and an isolated `backend/leadprophet-e2e.db`. The web-server command resets and seeds that database before each test run. The `POST /auth/dev/test-login` helper issues normal JWT cookies only in local, development, or test environments; it is unavailable in production. The E2E seed includes a primary and second user for tenant-isolation checks, deterministic providers, campaigns, leads, sequences, variants, tasks, notes, and public CMS content.

Coverage includes public navigation and contact validation/persistence, authenticated daily view, campaign and lead creation, CSV import, deterministic discovery and analysis, sequence advancement, tasks, notes, metrics, cross-tenant access, axe WCAG A/AA scans, and desktop/mobile screenshots. CI runs backend pytest and Chromium E2E, then uploads the Playwright HTML report and failure artifacts.

Real Google OAuth credentials are not required for this suite. Configure Google OAuth only to test the external provider flow manually. Configure an email provider only to test real contact notifications; the suite uses the no-send stub.

## Release and security checks

```bash
npm run test:e2e:all-browsers
npm run test:e2e:production
npm run test:e2e:flaky
python -m pip_audit -r backend/requirements.txt
python -m bandit -q -r backend/app -x backend/app/static
```

For local production rehearsal, copy `.env.example` to `.env`, set real secrets, then run `docker compose up --build`. The app waits for PostgreSQL, runs `alembic upgrade head`, and exposes `/health` and `/ready` on port 8000. Stop it with `docker compose down`; the named database volume is retained unless explicitly removed.

SQLite backup/restore:

```bash
python backend/scripts/sqlite_backup.py backup backend/leadprophet.db backups/leadprophet.db
python backend/scripts/sqlite_backup.py restore backups/leadprophet.db backend/leadprophet-restored.db
```

PostgreSQL backup/restore uses `scripts/backup_postgres.sh` and `scripts/restore_postgres.sh` with `DATABASE_URL`. Use custom-format dumps, retain encrypted copies according to the deployment policy, and restore into a clean database before switching traffic. Backups include application tables and data, not provider credentials or infrastructure secrets.
