# Feature Specification: Real-Time Payment Submission Service

- **Feature Key**: `PAY-900`
- **Domain**: `PAYMENTS`
- **Service**: `payment-submission-service`
- **Interface**: `POST /api/v1/payments/process`
- **Target Standard**: ISO 20022 / pacs.008

## 1. Overview
The Real-Time Payment Submission API allows authorized corporate merchants and financial institutions to dispatch real-time credit transfer payments into national clearing networks.

## 2. Business Requirements & Expected Outcomes

### Requirement 1: Authentication and Tenant Authorization
- Every request must include an authorized `Authorization: Bearer <JWT>` token issued by the corporate identity provider.
- Unauthenticated requests must immediately be rejected with `HTTP 401 Unauthorized`.
- Callers attempting to submit payments without merchant disbursement rights must be rejected with `HTTP 403 Forbidden`.

### Requirement 2: Request Idempotency (Technical Duplicate Prevention)
- Every submission must provide an `Idempotency-Key` HTTP header containing a unique UUIDv4 string.
- When an identical request is re-submitted with the same `Idempotency-Key`, the service must return the original cached HTTP response with the identical transaction ID.
- The financial ledger must record exactly one debit.

### Requirement 3: Business Duplicate Detection (Semantic Transaction Collision)
- Independent payment requests containing identical business attributes (`debtorAccountNumber`, `creditorAccountNumber`, `amount`, and `currency`) submitted within a **60-second velocity window** must be detected as a duplicate submission.
- The service must reject the second submission with `HTTP 409 Conflict` and error code `DUPLICATE_PAYMENT`.
- The rejected transaction must NOT be debited.

### Requirement 4: Transient Downstream Failure Resilience and Retry Recovery
- The clearing scheme backend frequently experiences transient TCP socket timeouts and `HTTP 503 Service Unavailable` bursts.
- The payment submission service must automatically execute up to 3 retry attempts with exponential backoff before terminating.
- If the downstream scheme recovers on retry 1 or 2, the payment must complete successfully with `HTTP 200 OK`.
- If all 3 retry attempts fail, the service must return `HTTP 504 Gateway Timeout` and log a high-priority operational alert.

### Requirement 5: Payload Schema and Amount Integrity
- Payment amounts must be strictly positive (> 0.00) with minor-unit limits corresponding to ISO 4217 currencies (e.g. 2 decimal places for USD/EUR).
- Negative or zero amounts must be rejected with `HTTP 400 Bad Request`.
