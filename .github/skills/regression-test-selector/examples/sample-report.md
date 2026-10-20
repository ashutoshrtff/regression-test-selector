# Regression Test Selector Report

## 1. Change Request Summary
This change updates `PaymentController.java` to support 3DS 2.2.0 authentication verification via the `X-3DS-Version` request header on `POST /api/v1/payments/process`. In addition, `checkout.html` has been updated to standardize the primary call-to-action button to "Pay Now" with `data-testid="pay-button"`. Edge condition handled: backward compatibility for clients omitting the header defaulting to version 2.2.0.

## 2. Must Run Tests

| Test Name | In Regression Suite | Evidence Tier | Confidence | Reason |
| :--- | :---: | :---: | :---: | :--- |
| `Payments API & Checkout > [PAY-101] Process Credit Card with 3DS verification @regression @smoke @payments` | Yes | Tier 1 (Direct Endpoint) | High | Exercises modified endpoint `POST /api/v1/payments/process`, route `/checkout/payment`, and button 'Pay Now'; matches Jira key `PAY-101`. |
| `Payments API & Checkout > [PAY-102] Handle card decline with error message @regression` | Yes | Tier 1 (Direct Endpoint) | High | Exercises `POST /api/v1/payments/process` on `/checkout/payment` with declined card flow. |
| `Unlinked Payment Edge Cases > [PAY-8821] Decline transaction when cardToken returns ERR_CARD_EXPIRED` | **No (Outside)** | Tier 1 (Direct Endpoint) | High | Exercises `POST /api/v1/payments/process` and `cardToken` error condition; verifies edge handling outside standard regression pack. |

## 3. Should Run Tests

*No additional tests categorized as Should Run.*

## 4. Risk Widening & Smoke Triggers

No risk widening rules triggered. Standard selective regression applies. (No auth filters, DB migrations, or core dependency version changes detected).

## 5. Coverage Gaps

No coverage gaps detected. The modified endpoint `POST /api/v1/payments/process` and checkout route `/checkout/payment` are comprehensively exercised by the selected suite.

## 6. Insufficient Evidence & Human Verification Items

- **3DS Fallback Header**: Diff introduces default value `2.2.0` when `X-3DS-Version` is missing. Verify in QA that legacy payment SDK clients sending 2.1.0 payloads do not encounter schema validation rejections.
- **Visual Regression**: Button text was changed from "Submit" to "Pay Now". Confirm localization bundles for non-English locales render without text truncation in mobile viewports.

## 7. Execution Statistics & Estimated Impact

- **Total Automation Suite Size**: 5 tests
- **Selected Tests**: 3 tests
- **Tests Skipped Safely**: 2 tests (40.0% reduction)
- **Estimated Time Saved**: ~1.5 minutes
- **Estimated Run Duration**: ~2.2 minutes

## 8. Ready-to-paste Execution Command

```bash
npx playwright test --grep "\[PAY\-101\]\ Process\ Credit\ Card\ with\ 3DS\ verification|\[PAY\-102\]\ Handle\ card\ decline\ with\ error\ message|\[PAY\-8821\]\ Decline\ transaction\ when\ cardToken\ returns\ ERR_CARD_EXPIRED"
```
