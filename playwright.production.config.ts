import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: /production\.spec\.ts/,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { baseURL: 'http://127.0.0.1:8006', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: {
    command: 'python -m alembic upgrade head && python -m uvicorn app.main:app --host 127.0.0.1 --port 8006',
    cwd: 'backend',
    url: 'http://127.0.0.1:8006/ready',
    timeout: 120_000,
    reuseExistingServer: false,
    env: {
      APP_ENV: 'production', DATABASE_URL: 'sqlite:///./leadprophet-production-rehearsal.db',
      ALLOW_SQLITE_IN_PRODUCTION_REHEARSAL: 'true', JWT_SECRET_KEY: 'production-rehearsal-secret',
      FRONTEND_ORIGIN: 'http://127.0.0.1:8006', CORS_ALLOWED_ORIGINS: 'http://127.0.0.1:8006',
      DOCS_ENABLED: 'true', SEARCH_PROVIDER: 'stub', EMAIL_PROVIDER: 'stub', ENRICHMENT_PROVIDER: 'internal', OPENAI_API_KEY: '',
    },
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
