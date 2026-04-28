# EXPLAINER

## 1. The Ledger

```python
result = LedgerEntry.objects.filter(merchant_id=merchant_id).aggregate(
    total_credits=Coalesce(
        Sum(Case(When(entry_type=LedgerEntryType.CREDIT, then='amount'),
            default=Value(0), output_field=BigIntegerField())),
        Value(0), output_field=BigIntegerField(),
    ),
    total_debits=Coalesce(
        Sum(Case(When(entry_type=LedgerEntryType.DEBIT, then='amount'),
            default=Value(0), output_field=BigIntegerField())),
        Value(0), output_field=BigIntegerField(),
    ),
)
balance = result['total_credits'] - result['total_debits']
```

Why this way: the balance is never stored as a mutable field. It's always derived from the append-only ledger via a DB-level `SUM`. This means there's no way for Python-side arithmetic bugs to silently corrupt the balance — the ledger *is* the source of truth. I used `BigIntegerField` as the output field because `IntegerField` would overflow at ~₹2.14 Cr in paise (32-bit signed int limit), which I caught during testing.

Credits and debits are separate `LedgerEntry` rows rather than positive/negative amounts on one field. This makes the audit trail dead simple — you can query all debits or all credits independently, and every entry is immutable (the model blocks `save()` on existing rows and raises on `delete()`).

---

## 2. The Lock

```python
with transaction.atomic():
    merchant = Merchant.objects.select_for_update().get(id=merchant_id, is_active=True)
    balance = get_balance(merchant_id)
    if balance < amount:
        raise InsufficientFundsError(...)
    # create payout + debit ledger entry
```

This is `SELECT ... FOR UPDATE` — a row-level exclusive lock in PostgreSQL. When two threads try to create payouts for the same merchant at the same time, the second thread physically blocks on the `select_for_update()` call until the first thread's transaction commits or rolls back. By the time thread B gets the lock, the balance has already been reduced by thread A's debit, so B's `get_balance()` call returns the updated value and correctly rejects if funds are insufficient.

The key thing is that the balance check and the debit happen inside the same `transaction.atomic()` block while holding the lock. There's no gap between "check balance" and "deduct balance" where another thread could sneak in.

---

## 3. The Idempotency

The `idempotency_keys` table has a `UNIQUE(merchant_id, key)` constraint. When a request comes in, I attempt a direct `INSERT`. If it succeeds, this is a new request. If the database throws `IntegrityError`, the key already exists — I fetch it and return the cached response.

I also hash the request body with SHA-256 and store it alongside the key. If a second request arrives with the same key but different payload (e.g., different amount), I reject it with a 409 Conflict. This prevents misuse where someone reuses a key to change the payout parameters.

**If the first request is still in-flight:** the `IdempotencyKey` row exists but `response_status` and `response_body` are still `NULL`. When thread B hits the `IntegrityError` path and fetches the key, it sees `cached_response=None` and returns a 202, telling the client "we got it, still working on it, try again shortly."

Keys are scoped per merchant and expire after 24 hours. Expired keys are cleaned up by a periodic Celery beat task rather than inline (deleting inline would create a TOCTOU race between concurrent requests).

---

## 4. The State Machine

```python
def complete_payout(payout, reference_id):
    rows = Payout.objects.filter(
        id=payout.id, status=PayoutStatus.PROCESSING,
    ).update(status=PayoutStatus.COMPLETED, ...)
    return rows == 1
```

This is a compare-and-swap. The `WHERE status='PROCESSING'` clause means the update only applies if the payout is currently in `PROCESSING`. If it's already `FAILED` or `COMPLETED`, `rows` is 0 and nothing happens. Same pattern in `fail_payout()`. There's no code path where you can go backwards (e.g., `FAILED` → `COMPLETED` or `COMPLETED` → `PENDING`) because every transition function filters on the expected current status.

The `fail_payout` function also wraps the state change and the fund reversal (CREDIT ledger entry) in a single `transaction.atomic()` with `select_for_update()` on the merchant row. If the process dies mid-way, the whole transaction rolls back — the payout stays in `PROCESSING` and the retry mechanism picks it up.

---

## 5. The AI Audit

When I asked the AI to implement idempotency, it gave me this:

```python
key_obj, created = IdempotencyKey.objects.get_or_create(
    merchant_id=merchant_id,
    key=idempotency_key
)
if not created:
    return key_obj.response_body
```

The problem: `get_or_create` does a `SELECT` first, then `INSERT` if not found. Under concurrency, two threads can both run the `SELECT`, both see "not found", and both attempt `INSERT`. Django catches the resulting `IntegrityError` internally and retries with another `SELECT`, but by that point both threads have already passed the `if not created` check and are proceeding to create payouts. You end up with duplicate payouts.

What I replaced it with:

```python
try:
    key_obj = IdempotencyKey.objects.create(
        merchant_id=merchant_id,
        key=key,
        request_hash=incoming_hash,
        expires_at=expires_at,
    )
    return IdempotencyResult(created=True, idempotency_key=key_obj)
except IntegrityError:
    key_obj = IdempotencyKey.objects.get(merchant_id=merchant_id, key=key)
    # ... validate hash, check expiry, return cached response
```

Straight `INSERT` first, let the DB constraint do the work. If it throws, we know the key exists and fall into the replay path. No SELECT-then-INSERT race.
