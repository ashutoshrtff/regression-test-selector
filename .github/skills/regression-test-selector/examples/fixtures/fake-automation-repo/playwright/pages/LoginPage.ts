import { Page, Locator } from '@playwright/test';

export class LoginPage {
  readonly page: Page;
  readonly loginRoute = '/auth/login';
  readonly tokenEndpoint = '/api/v1/auth/token';
  readonly usernameInput: Locator;
  readonly passwordInput: Locator;
  readonly submitButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.usernameInput = page.getByTestId('username-field');
    this.passwordInput = page.getByTestId('password-field');
    this.submitButton = page.getByRole('button', { name: 'Log In' });
  }

  async navigate() {
    await this.page.goto('/auth/login');
  }

  async login(user: string, pass: string) {
    await this.usernameInput.fill(user);
    await this.passwordInput.fill(pass);
    await this.submitButton.click();
  }
}
