# Playwright TypeScript / JavaScript Reference

This document details how the `regression-test-selector` parses, indexes, and targets Playwright automation test repositories.

---

## 1. Project Detection
A repository is recognized as a Playwright project when any of the following files are present:
- `playwright.config.ts`
- `playwright.config.js`
- `playwright.config.mjs`

---

## 2. Test Structure and Metadata Extraction

### Test Annotations and Tagging
In Playwright, tags are specified directly within the test title string or via the tag option:
```typescript
test('[PAY-101] Process Credit Card with 3DS verification @regression @smoke', async ({ page }) => {
  // ...
});
```
The parser extracts:
- **Title Hierarchy**: Chain of `test.describe('Parent', () => { test.describe('Child', () => { test('My Test') }) })` is preserved as `Parent > Child > My Test`.
- **Tags**: Any word starting with `@` (e.g. `@regression`, `@smoke`, `@payments`).
- **Jira Keys**: Regex pattern `\b[A-Z]{2,10}-\d+\b` in the title, preceding comments, or the test body.

---

## 3. Page Object Resolution (1-Level Indirection)

Tests frequently delegate UI interactions and API mocking to Page Objects:
```typescript
// tests/payment.spec.ts
const paymentPage = new PaymentPage(page);
await paymentPage.navigate();
await paymentPage.submitPayment(cardToken, amount);
```

The index builder automatically:
1. Catalogs all classes ending in `*Page.ts` or residing in `pages/`.
2. Scans the Page Object for:
   - Routes: `page.goto('/checkout/payment')`
   - Endpoints: `page.route('/api/v1/payments/process', ...)`
   - Selectors: `getByRole('button', { name: 'Pay Now' })`, `getByTestId('card-number-input')`
3. Injects those routes, endpoints, and selectors into any test instantiating or referencing `PaymentPage`.

---

## 4. Execution Command Generation

### Grep Filter
The standard Playwright execution command uses `--grep`:
```bash
npx playwright test --grep "\[PAY\-101\]\ Process\ Credit\ Card|\[PAY\-102\]\ Handle\ card\ decline"
```

### Command Length Fallback
If the generated regular expression exceeds command-line buffer limits (> 500 characters), the selector falls back to passing space-delimited spec file paths:
```bash
npx playwright test tests/payments/checkout.spec.ts tests/unlinked-edge-cases.spec.ts
```
