import { test, expect } from '@playwright/test';

test.describe('Real-Time Payment Submission Tests', () => {

  test('[PAY-900] Successfully submit real-time credit payment @regression', async ({ request }) => {
    const response = await request.post('/api/v1/payments/process', {
      headers: {
        'Authorization': 'Bearer valid_merchant_token',
        'Idempotency-Key': 'd8f33d71-5511-4041-9494-b2099955aaaa'
      },
      data: {
        amount: 250.00,
        currency: 'USD',
        debtorAccount: 'ACC_US_1001',
        creditorAccount: 'ACC_US_9999',
        reference: 'INV-2026-001'
      }
    });

    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body.status).toBe('ACCEPTED');
  });

  test('[PAY-900] Replaying request with same Idempotency-Key returns cached response without duplicate debit @regression', async ({ request }) => {
    const idempotencyKey = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';
    // First call
    const res1 = await request.post('/api/v1/payments/process', {
      headers: {
        'Authorization': 'Bearer valid_merchant_token',
        'Idempotency-Key': idempotencyKey
      },
      data: { amount: 100.00, currency: 'USD', debtorAccount: 'ACC_1', creditorAccount: 'ACC_2' }
    });
    expect(res1.status).toBe(200);
    const body1 = await res1.json();

    // Replay call with exact same Idempotency-Key header
    const res2 = await request.post('/api/v1/payments/process', {
      headers: {
        'Authorization': 'Bearer valid_merchant_token',
        'Idempotency-Key': idempotencyKey
      },
      data: { amount: 100.00, currency: 'USD', debtorAccount: 'ACC_1', creditorAccount: 'ACC_2' }
    });
    expect(res2.status).toBe(200);
    const body2 = await res2.json();
    expect(body2.transactionId).toBe(body1.transactionId);
    expect(body2.idempotency_verified).toBe(true);
  });

  test('[PAY-900] Reject duplicate payment with 409 Conflict within 60s window @regression', async ({ request }) => {
    // Separate submission with different key but duplicate business attributes
    const res1 = await request.post('/api/v1/payments/process', {
      headers: { 'Authorization': 'Bearer valid_token', 'Idempotency-Key': 'key-submission-A' },
      data: { amount: 500.00, currency: 'USD', debtorAccount: 'ACC_DUP_1', creditorAccount: 'ACC_DUP_2', reference: 'REF-DUP-99' }
    });
    expect(res1.status).toBe(200);

    const res2 = await request.post('/api/v1/payments/process', {
      headers: { 'Authorization': 'Bearer valid_token', 'Idempotency-Key': 'key-submission-B' },
      data: { amount: 500.00, currency: 'USD', debtorAccount: 'ACC_DUP_1', creditorAccount: 'ACC_DUP_2', reference: 'REF-DUP-99' }
    });
    expect(res2.status).toBe(409);
    const body2 = await res2.json();
    expect(body2.errorCode).toBe('DUPLICATE_PAYMENT');
  });

  test('[PAY-900] Reject unauthenticated payment with 401 Unauthorized @regression', async ({ request }) => {
    const response = await request.post('/api/v1/payments/process', {
      data: { amount: 100.00, currency: 'USD', debtorAccount: 'ACC_1', creditorAccount: 'ACC_2' }
    });
    expect(response.status).toBe(401);
  });

  test('[PAY-900] Reject negative payment amount with 400 Bad Request @regression', async ({ request }) => {
    const response = await request.post('/api/v1/payments/process', {
      headers: { 'Authorization': 'Bearer valid_token', 'Idempotency-Key': 'key-negative' },
      data: { amount: -50.00, currency: 'USD', debtorAccount: 'ACC_1', creditorAccount: 'ACC_2' }
    });
    expect(response.status).toBe(400);
  });

});
