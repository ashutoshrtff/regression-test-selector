# Architecture Decision Record (ADR-004): Idempotency & Downstream Resilience

## Context
Payment processing operations across public internet APIs are prone to packet drops and client-side retries. In addition, downstream clearing schemes experience transient connection reset storms.

## Decision
1. **Idempotency Key Cache**:
   - Every `POST /api/v1/payments/process` must provide an `Idempotency-Key` header.
   - Redis distributed cache stores the processed transaction outcome with a 24-hour TTL.
   - Replaying the identical key short-circuits execution and returns the cached result without invoking the ledger.

2. **Business Duplicate Detection vs Idempotency**:
   - `Idempotency-Key` handles identical technical retries.
   - A separate in-memory sliding window checks for duplicate business attributes (`debtorAccount + creditorAccount + amount + reference`) within 60 seconds.
   - Collisions return `HTTP 409 Conflict` (`DUPLICATE_PAYMENT`).

3. **Downstream Transient Retry & Circuit Breaker**:
   - Transient `HTTP 503` or TCP socket timeout triggers an automated Spring Retry backoff (100ms, 200ms, 400ms).
   - Maximum retry attempts = 3.
   - If downstream fails 5 consecutive times, Resilience4j circuit breaker opens.

## Consequences & Test Obligations
- Automated test suites must explicitly demonstrate:
  1. Replaying the same `Idempotency-Key` produces identical response and 0 duplicate debits.
  2. Submitting two distinct requests with identical payment details within 60s returns `HTTP 409 Conflict`.
  3. Transient 503 triggers retry and succeeds on downstream recovery.
