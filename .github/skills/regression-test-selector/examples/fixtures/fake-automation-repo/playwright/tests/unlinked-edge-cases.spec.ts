import { test, expect } from '@playwright/test';
import { PaymentPage } from '../pages/PaymentPage';

test.describe('Unlinked Payment Edge Cases', () => {
  // Test outside standard regression suite to catch specific card token lifecycle edge cases
  test('[PAY-8821] Decline transaction when cardToken returns ERR_CARD_EXPIRED', async ({ page }) => {
    const paymentPage = new PaymentPage(page);
    await paymentPage.navigate();

    await page.route('**/api/v1/payments/process', async (route) => {
      await route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ERROR',
          errorCode: 'ERR_CARD_EXPIRED',
          message: 'The submitted card has expired'
        })
      });
    });

    await paymentPage.submitPayment('tok_expired_card', 25.00);
    await expect(page.getByText('Card has expired')).toBeVisible();
  });
});
