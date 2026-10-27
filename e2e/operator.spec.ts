import { test, expect } from './fixtures';
import AxeBuilder from '@axe-core/playwright';

test.describe('operator readiness and setup', () => {
  test('owner can inspect readiness and update public profile', async ({ authenticatedPage: page }) => {
    await page.goto('/setup');
    await expect(page.getByRole('heading', { name: 'Setup readiness' })).toBeVisible();
    await expect(page.getByText('Required to go live')).toBeVisible();
    expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze()).violations.filter(v => ['critical', 'serious'].includes(v.impact ?? ''))).toEqual([]);
    await page.goto('/settings');
    await page.getByLabel('City').fill('Operator test city');
    await page.getByLabel('Support email').fill('operator@leadprophet.example');
    await page.getByLabel('Footer text').fill('Operator verified footer');
    await page.getByRole('button', { name: 'Save profile' }).click();
    await expect(page.locator('.notice.success')).toContainText('Company profile updated');
    await page.goto('/contact');
    await expect(page.getByRole('link', { name: 'operator@leadprophet.example' }).first()).toBeVisible();
    await expect(page.getByText('Operator verified footer')).toBeVisible();
  });

  test('wizard creates a campaign with a starter sequence', async ({ authenticatedPage: page }) => {
    await page.goto('/campaigns/wizard');
    await expect(page.getByRole('heading', { name: 'Build a usable campaign' })).toBeVisible();
    await page.getByLabel('Name').fill('Operator launch campaign');
    await page.getByRole('button', { name: 'Create campaign and sequence' }).click();
    await expect(page).toHaveURL(/\/campaigns\/.+created=1/);
    await expect(page.getByRole('link', { name: /Starter outreach/ })).toBeVisible();
  });

  test('campaign bundles, content export, and sandbox reset are available to the owner', async ({ authenticatedPage: page }) => {
    await page.goto('/daily');
    await page.getByRole('link', { name: /E2E Automation Campaign/ }).click();
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('link', { name: 'Export', exact: true }).click();
    const campaignDownload = await downloadPromise;
    expect(campaignDownload.suggestedFilename()).toMatch(/campaign-.+\.json/);
    page.on('dialog', dialog => dialog.accept());
    await page.getByRole('button', { name: 'Clone' }).click();
    await expect(page.locator('.notice.success')).toContainText('Campaign cloned');
    await page.goto('/settings/portability');
    await expect(page.getByRole('heading', { name: 'Import and export' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Legal publication' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Reset local sandbox' })).toBeVisible();
    expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze()).violations.filter(v => ['critical', 'serious'].includes(v.impact ?? ''))).toEqual([]);
    const downloadPath = await campaignDownload.path();
    if (!downloadPath) throw new Error('Campaign download path was unavailable');
    await page.getByLabel('Campaign JSON').setInputFiles(downloadPath);
    await page.getByRole('button', { name: 'Preview campaign import' }).click();
    await expect(page.locator('.import-preview').first()).toContainText('Ready to import campaign');
    await page.getByRole('button', { name: 'Confirm additive import' }).first().click();
    await expect(page.locator('.notice.success')).toContainText('Campaign bundle imported');
    await page.goto('/settings/portability');
    const contentDownload = page.waitForEvent('download');
    await page.getByRole('link', { name: 'Export site content' }).click();
    expect((await contentDownload).suggestedFilename()).toBe('leadprophet-site-content.json');
  });
});
