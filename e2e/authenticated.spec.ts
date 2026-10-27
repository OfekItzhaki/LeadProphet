import AxeBuilder from '@axe-core/playwright';
import { test, expect } from './fixtures';

test.describe('authenticated workspace', () => {
  test('test auth lands on daily view with seeded workspace', async ({ authenticatedPage: page }) => {
    await page.goto('/daily');
    await expect(page.getByRole('heading', { name: 'Daily' })).toBeVisible();
    await expect(page.getByText('E2E Automation Campaign')).toBeVisible();
    await expect(page.getByRole('link', { name: /Seeded Service Company other/ })).toBeVisible();
    await expect(page.getByText('LeadProphet Test User')).toBeVisible();
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
    expect(results.violations.filter(v => ['critical', 'serious'].includes(v.impact ?? '')).map(v => v.id)).toEqual([]);
    if (process.platform === 'win32') {
      await expect(page).toHaveScreenshot('daily-desktop.png', { fullPage: false, animations: 'disabled', maxDiffPixels: 100 });
    }
  });

  test('creates campaign and lead, then reaches lead detail', async ({ authenticatedPage: page }) => {
    await page.goto('/campaigns/new');
    await page.getByLabel('Name').fill('E2E New Campaign');
    await page.getByLabel('Vertical').fill('professional services');
    await page.getByLabel('Region').fill('Israel');
    await page.getByLabel('Languages').fill('en');
    await page.getByLabel('Services offered').fill('automation');
    await page.getByLabel('Ideal customer profile').fill('Small service companies with manual workflows');
    await page.getByLabel('Value proposition').fill('Make follow-up faster');
    await page.getByLabel('Tone guidelines').fill('Direct and useful');
    await page.getByRole('button', { name: 'Create campaign' }).click();
    await expect(page.getByRole('heading', { name: 'E2E New Campaign Cockpit' })).toBeVisible();
    await page.getByLabel('Business name').fill('E2E Manual Lead');
    await page.getByLabel('Website URL').fill('https://manual.example');
    await page.getByRole('button', { name: 'Create lead' }).click();
    await expect(page.getByRole('heading', { name: 'E2E Manual Lead' })).toBeVisible();
  });

  test('runs deterministic analysis, sequence work, and lead follow-up actions', async ({ authenticatedPage: page }) => {
    await page.goto('/daily');
    await page.getByRole('link', { name: /Seeded Service Company other/ }).click();
    await page.getByRole('button', { name: 'Run analysis' }).click();
    await expect(page.getByText(/\/100/).first()).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Outreach Drafts' })).toBeVisible();
    await page.getByLabel('Sequence').selectOption({ label: 'E2E Follow-up · 2 steps' });
    await page.getByRole('button', { name: 'Attach sequence' }).click();
    await expect(page.getByText(/Current step 1 of 2/)).toBeVisible();
    await page.getByRole('button', { name: 'Advance sequence' }).click();
    await expect(page.getByText(/Current step 2 of 2/)).toBeVisible();
    await page.getByPlaceholder('Task title').fill('E2E follow-up task');
    await page.getByRole('button', { name: 'Add task' }).click();
    await expect(page.getByText('E2E follow-up task')).toBeVisible();
    await page.getByPlaceholder('Add context or call notes').fill('E2E timeline note');
    await page.getByRole('button', { name: 'Add note' }).click();
    await expect(page.locator('.activity-row').filter({ hasText: 'E2E timeline note' }).last()).toBeVisible();
    const metrics = await page.request.get('/metrics/summary');
    expect(metrics.ok()).toBeTruthy();
    expect((await metrics.json()).total_leads).toBeGreaterThan(0);
  });

  test('imports CSV and discovers deterministic search leads', async ({ authenticatedPage: page }) => {
    await page.goto('/daily');
    await page.getByRole('link', { name: /E2E Automation Campaign/ }).click();
    await page.locator('input[type="file"]').setInputFiles({
      name: 'leads.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from('business_name,website_url,location_city\nCSV Test Business,https://csv.example,Tel Aviv\n'),
    });
    await page.getByRole('button', { name: 'Import CSV' }).click();
    await expect(page.getByText(/1 created/)).toBeVisible();
    await page.getByRole('button', { name: 'Discover leads' }).click();
    await expect(page.getByText(/created/)).toBeVisible();
  });

  test('tenant isolation prevents the second user from opening the primary campaign', async ({ authenticatedPage: primary, secondUserPage: second }) => {
    await primary.goto('/daily');
    const campaignLink = primary.getByRole('link', { name: /E2E Automation Campaign/ });
    await expect(campaignLink).toBeVisible();
    const href = await campaignLink.getAttribute('href');
    await second.goto(href!);
    await expect(second.getByRole('heading', { name: 'Page not found' })).toBeVisible();
  });
});
