import { test, expect } from '@playwright/test';

test('production-like public and operational surfaces', async ({ page, request }) => {
  await expect((await request.get('/health')).status()).toBe(200);
  await expect((await request.get('/ready')).status()).toBe(200);
  await expect((await request.get('/docs')).status()).toBe(404);
  await expect((await request.get('/redoc')).status()).toBe(404);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /Turn good prospects/ })).toBeVisible();
  await page.goto('/does-not-exist');
  await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible();
  await page.goto('/contact');
  await page.getByLabel('Name').fill('Production rehearsal');
  await page.getByLabel('Email').fill('rehearsal@example.com');
  await page.getByLabel('Message').fill('Production rehearsal contact submission.');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByText('Thanks for reaching out')).toBeVisible();
});
