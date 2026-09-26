import { test, expect } from './fixtures';

test('cross-browser public navigation and authenticated smoke', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /Turn good prospects/ })).toBeVisible();
  await page.getByRole('navigation', { name: 'Primary navigation' }).getByRole('link', { name: 'Contact Us' }).click();
  await expect(page.getByRole('heading', { name: /Tell us what/ })).toBeVisible();
});
