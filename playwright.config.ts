import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testIgnore: /production\.spec\.ts/,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env.BASE_URL ?? 'http://127.0.0.1:8005',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: {
    command: 'python scripts/seed_e2e.py && python -m uvicorn app.main:app --host 127.0.0.1 --port 8005',
    cwd: 'backend',
    url: 'http://127.0.0.1:8005/health',
    timeout: 120_000,
    reuseExistingServer: !process.env.CI,
    env: {
      APP_ENV: 'test',
      DATABASE_URL: 'sqlite:///./leadprophet-e2e.db',
      JWT_SECRET_KEY: 'e2e-only-secret',
      FRONTEND_ORIGIN: 'http://127.0.0.1:8005',
      SEARCH_PROVIDER: 'stub',
      EMAIL_PROVIDER: 'stub',
      ENRICHMENT_PROVIDER: 'internal',
      OPENAI_API_KEY: '',
    },
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox-smoke', testMatch: /smoke\.spec\.ts/, use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit-smoke', testMatch: /smoke\.spec\.ts/, use: { ...devices['Desktop Safari'] } },
  ],
});
