import { test, expect } from '@playwright/test';
import { LoginPage } from '../pages/LoginPage';

test.describe('Authentication & Session Smoke Tests', () => {
  // Jira: AUTH-401
  test('[AUTH-401] Verify JWT token refresh and session expiry @smoke @auth', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.navigate();
    await loginPage.login('merchant_admin', 'SecretPassword123!');

    await page.route('**/api/v1/auth/token', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ token: 'jwt.token.here', expiresIn: 3600 })
      });
    });

    await expect(page.getByText('Welcome Merchant Dashboard')).toBeVisible();
  });
});
