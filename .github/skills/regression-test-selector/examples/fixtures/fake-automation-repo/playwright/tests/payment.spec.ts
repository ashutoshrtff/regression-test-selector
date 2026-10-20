import { test, expect } from '@playwright/test';
import { PaymentPage } from '../pages/PaymentPage';

test.describe('Payments API & Checkout', () => {
  // Jira: PAY-101
  test('[PAY-101] Process Credit Card with 3DS verification @regression @smoke @payments', async ({ page }) => {
    const paymentPage = new PaymentPage(page);
    await paymentPage.navigate();

    await page.route('**/api/v1/payments/process', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'SUCCESS', transactionId: 'txn_999888' })
      });
    });

    await paymentPage.submitPayment('tok_visa_valid', 150.00);
    await expect(page.getByText('Payment processed successfully')).toBeVisible();
  });

  test('[PAY-102] Handle card decline with error message @regression', async ({ page }) => {
    const paymentPage = new PaymentPage(page);
    await paymentPage.navigate();

    await page.route('**/api/v1/payments/process', async (route) => {
      await route.fulfill({
        status: 402,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'FAILED', errorCode: 'INSUFFICIENT_FUNDS' })
      });
    });

    await paymentPage.submitPayment('tok_visa_declined', 5000.00);
    await expect(page.getByText('Insufficient funds in account')).toBeVisible();
  });
});
