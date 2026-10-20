import { test, expect } from '@playwright/test';

test.describe('Settlement Reporting', () => {
  // Jira: REP-505
  test('[REP-505] Download daily settlement CSV report @regression @reporting', async ({ page }) => {
    await page.goto('/reports/settlement');
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export CSV' }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toContain('settlement_report');
  });
});
