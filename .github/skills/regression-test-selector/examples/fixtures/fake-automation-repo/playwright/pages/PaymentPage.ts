import { Page, Locator } from '@playwright/test';

export class PaymentPage {
  readonly page: Page;
  readonly checkoutRoute = '/checkout/payment';
  readonly processEndpoint = '/api/v1/payments/process';
  readonly payButton: Locator;
  readonly cardNumberInput: Locator;
  readonly securityCodeInput: Locator;
  readonly threeDsModal: Locator;

  constructor(page: Page) {
    this.page = page;
    this.payButton = page.getByRole('button', { name: 'Pay Now' });
    this.cardNumberInput = page.getByTestId('card-number-input');
    this.securityCodeInput = page.getByTestId('cvv-input');
    this.threeDsModal = page.locator('#three-ds-challenge');
  }

  async navigate() {
    await this.page.goto('/checkout/payment');
  }

  async submitPayment(cardToken: string, amount: number) {
    await this.page.route('/api/v1/payments/process', route => route.continue());
    await this.payButton.click();
  }
}
