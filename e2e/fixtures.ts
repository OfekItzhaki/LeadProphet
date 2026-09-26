import { test as base, expect, type Page } from '@playwright/test';

type Fixtures = {
  authenticatedPage: Page;
  secondUserPage: Page;
};

const resetState = base.extend({
  resetState: [async ({ request }, use) => {
    const response = await request.post('/auth/dev/reset');
    expect(response.ok()).toBeTruthy();
    await use(undefined);
  }, { auto: true }],
});

async function login(page: Page, user = 'primary') {
  const response = await page.request.post(`/auth/dev/test-login?user=${user}`);
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  await page.context().addCookies([
    { name: 'leadprophet_access', value: payload.access_token, url: 'http://127.0.0.1:8005' },
    { name: 'leadprophet_refresh', value: payload.refresh_token, url: 'http://127.0.0.1:8005' },
  ]);
}

export const test = resetState.extend<Fixtures>({
  authenticatedPage: async ({ page }, use) => {
    await login(page);
    await use(page);
  },
  secondUserPage: async ({ browser }, use) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    await login(page, 'second');
    await use(page);
    await context.close();
  },
});

export { expect };
