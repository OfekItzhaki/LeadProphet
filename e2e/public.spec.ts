import AxeBuilder from '@axe-core/playwright';
import { test, expect } from './fixtures';

const pages = [
  { path: '/', heading: 'Turn good prospects into relevant conversations.' },
  { path: '/about', heading: 'Outbound should begin with judgment, not volume.' },
  { path: '/contact', heading: 'Tell us what you are trying to improve.' },
  { path: '/legal', heading: 'Terms & Privacy' },
];

test.describe('public marketing site', () => {
  for (const item of pages) {
    test(`${item.path} renders expected content and passes accessibility`, async ({ page }) => {
      await page.goto(item.path);
      await expect(page.getByRole('heading', { name: item.heading })).toBeVisible();
      await expect(page.getByRole('navigation', { name: 'Primary navigation' })).toContainText('Home');
      const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
      const serious = results.violations.filter(v => ['critical', 'serious'].includes(v.impact ?? ''));
      expect(serious, JSON.stringify(serious.map(v => ({ id: v.id, nodes: v.nodes.map(n => n.target) })), null, 2)).toEqual([]);
    });
  }

  test('navbar navigates and mobile layout remains usable', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');
    await expect(page.getByRole('banner').getByRole('link', { name: 'LeadProphet home' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Contact us for early access' })).toBeVisible();
    await page.getByRole('navigation', { name: 'Primary navigation' }).getByRole('link', { name: 'About' }).click();
    await expect(page).toHaveURL(/\/about$/);
    await expect(page.getByRole('heading', { name: /judgment, not volume/ })).toBeVisible();
    await expect(page.locator('body')).toHaveScreenshot('about-mobile.png', { animations: 'disabled' });
  });

  test('contact form validates and persists a valid submission', async ({ page }) => {
    await page.goto('/contact');
    await page.getByRole('button', { name: 'Send message' }).click();
    await expect(page.getByLabel('Name')).toBeFocused();
    await expect(page.getByLabel('Name')).toHaveJSProperty('validity.valid', false);
    await page.getByLabel('Name').fill('E2E Visitor');
    await page.getByLabel('Email').fill('invalid');
    await page.getByLabel('Message').fill('A valid enough message for the test.');
    await page.getByRole('button', { name: 'Send message' }).click();
    await expect(page.getByLabel('Email')).toHaveJSProperty('validity.valid', false);
    await page.getByLabel('Email').fill('e2e@example.com');
    await page.getByRole('button', { name: 'Send message' }).click();
    await expect(page.getByText('Thanks for reaching out')).toBeVisible();
  });

  test('home has stable desktop visual baseline', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');
    await expect(page).toHaveScreenshot('home-desktop.png', { fullPage: false, animations: 'disabled' });
  });
});
