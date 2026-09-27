import { test, expect } from './fixtures';

test.describe('operator readiness and setup', () => {
  test('owner can inspect readiness and update public profile', async ({ authenticatedPage: page }) => {
    await page.goto('/setup');
    await expect(page.getByRole('heading', { name: 'Setup readiness' })).toBeVisible();
    await expect(page.getByText('Required to go live')).toBeVisible();
    await page.goto('/settings');
    await page.getByLabel('City').fill('Operator test city');
    await page.getByRole('button', { name: 'Save profile' }).click();
    await expect(page.locator('.notice.success')).toContainText('Company profile updated');
  });

  test('wizard creates a campaign with a starter sequence', async ({ authenticatedPage: page }) => {
    await page.goto('/campaigns/wizard');
    await expect(page.getByRole('heading', { name: 'Build a usable campaign' })).toBeVisible();
    await page.getByLabel('Name').fill('Operator launch campaign');
    await page.getByRole('button', { name: 'Create campaign and sequence' }).click();
    await expect(page).toHaveURL(/\/campaigns\/.+created=1/);
    await expect(page.getByRole('link', { name: /Starter outreach/ })).toBeVisible();
  });
});
