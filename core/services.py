"""
services.py — Business logic layer.

All DB-level computations live here. Views and tasks must never
directly aggregate the ledger; they must call these service functions.
"""
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Sum, Case, When, IntegerField, Value
from django.db.models.functions import Coalesce

from .models import (
    BankAccount,
    IdempotencyKey,
    LedgerEntry,
    LedgerEntryType,
    Merchant,
    Payout,
    PayoutStatus,
    PayoutMode,
)


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------

class IdempotencyConflictError(Exception):
    """
    Raised when the same Idempotency-Key is reused with a DIFFERENT
    request body. This signals a client programming error.
    """


class InsufficientFundsError(Exception):
    """
    Raised when a merchant does not have enough balance to cover a payout.
    The balance check is always done at the DB level, inside a locked
    transaction, so this error is authoritative — not a race artefact.
    """


# ---------------------------------------------------------------------------
# Result dataclass returned by resolve_idempotency()
# ---------------------------------------------------------------------------

@dataclass
class IdempotencyResult:
    """
    Returned by resolve_idempotency() to tell the caller what to do next.

    Fields:
        created (bool):
            True  → this key is brand new; proceed with payout creation.
            False → this key already exists; use cached_response.
        idempotency_key (IdempotencyKey):
            The DB record. After a successful payout, call
            store_idempotency_response() on this object.
        cached_response (dict | None):
            Populated only when created=False AND the original request
            already received a response. Can be None if the first request
            is still in-flight (client is retrying before we finished).
        cached_status (int | None):
            HTTP status code of the original response.
    """
    created: bool
    idempotency_key: IdempotencyKey
    cached_response: dict | None = None
    cached_status: int | None = None


# ---------------------------------------------------------------------------
# Balance Calculation
# ---------------------------------------------------------------------------

def get_balance(merchant_id: str) -> int:
    """
    Compute a merchant's current balance entirely at the database level.

    Strategy: conditional aggregation in a single SQL query.
      - SUM all amounts where entry_type = 'CREDIT'  → total_credits
      - SUM all amounts where entry_type = 'DEBIT'   → total_debits
      - balance = total_credits - total_debits

    Why NOT use balance_after snapshot?
      balance_after is a convenience field for point-in-time reporting.
      Using it for "current balance" would require fetching the LAST row,
      which needs an ORDER BY + LIMIT — more fragile than a full aggregate.

    Returns:
        int: Balance in paise. Can be 0 if no ledger entries exist.

    Raises:
        Merchant.DoesNotExist: if the merchant_id is invalid.

    Equivalent SQL:
        SELECT
            COALESCE(SUM(CASE WHEN entry_type = 'CREDIT' THEN amount ELSE 0 END), 0)
          - COALESCE(SUM(CASE WHEN entry_type = 'DEBIT'  THEN amount ELSE 0 END), 0)
            AS balance
        FROM ledger_entries
        WHERE merchant_id = %s;
    """
    # Validate merchant exists (fail fast on bad input)
    if not Merchant.objects.filter(id=merchant_id).exists():
        raise Merchant.DoesNotExist(f"Merchant {merchant_id} does not exist.")

    result = LedgerEntry.objects.filter(merchant_id=merchant_id).aggregate(
        total_credits=Coalesce(
            Sum(
                Case(
                    When(entry_type=LedgerEntryType.CREDIT, then='amount'),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            ),
            Value(0),  # Coalesce handles NULL when no rows match
        ),
        total_debits=Coalesce(
            Sum(
                Case(
                    When(entry_type=LedgerEntryType.DEBIT, then='amount'),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            ),
            Value(0),
        ),
    )

    balance = result['total_credits'] - result['total_debits']
    return balance


def get_balance_with_sql(merchant_id: str) -> tuple[int, str]:
    """
    Same as get_balance() but also returns the raw SQL for debugging.
    Do NOT use in production hot paths — str(queryset.query) is for
    inspection only.

    Returns:
        (balance: int, sql: str)
    """
    queryset = LedgerEntry.objects.filter(merchant_id=merchant_id).aggregate(
        total_credits=Coalesce(
            Sum(
                Case(
                    When(entry_type=LedgerEntryType.CREDIT, then='amount'),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            ),
            Value(0),
        ),
        total_debits=Coalesce(
            Sum(
                Case(
                    When(entry_type=LedgerEntryType.DEBIT, then='amount'),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            ),
            Value(0),
        ),
    )

    # Build raw SQL from the underlying queryset for inspection
    raw_qs = LedgerEntry.objects.filter(merchant_id=merchant_id).values('merchant_id').annotate(
        total_credits=Coalesce(
            Sum(
                Case(
                    When(entry_type=LedgerEntryType.CREDIT, then='amount'),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            ),
            Value(0),
        ),
        total_debits=Coalesce(
            Sum(
                Case(
                    When(entry_type=LedgerEntryType.DEBIT, then='amount'),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            ),
            Value(0),
        ),
    )

    balance = queryset['total_credits'] - queryset['total_debits']
    sql = str(raw_qs.query)
    return balance, sql


def get_held_balance(merchant_id: str) -> int:
    """
    Returns the total balance currently held in PENDING or PROCESSING payouts.
    This is required for the dashboard to show locked funds.
    """
    from django.db.models import Sum
    from .models import Payout, PayoutStatus
    
    held = Payout.objects.filter(
        merchant_id=merchant_id,
        status__in=[PayoutStatus.PENDING, PayoutStatus.PROCESSING]
    ).aggregate(total_held=Sum('amount'))['total_held']
    
    return held or 0



# ---------------------------------------------------------------------------
# Idempotency Handling
# ---------------------------------------------------------------------------

def compute_request_hash(payload: dict) -> str:
    """
    Produce a stable SHA-256 fingerprint of the request payload.

    Rules:
    - Keys are sorted before hashing so {"a":1,"b":2} == {"b":2,"a":1}.
    - Encoded as UTF-8 JSON (no spaces) before hashing.

    This fingerprint is stored alongside the IdempotencyKey so that
    a retry with the SAME key but DIFFERENT body can be detected and
    rejected (conflict).

    Args:
        payload: dict — the parsed request body (e.g. request.data).

    Returns:
        str — 64-character lowercase hex SHA-256 digest.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def resolve_idempotency(
    merchant_id: str,
    key: str,
    payload: dict,
) -> IdempotencyResult:
    """
    Idempotency gate. Validates if a request is a replay or a new transaction.
    
    Relies on database unique constraint (merchant_id, key) to handle race 
    conditions securely without TOCTOU windows.

    Args:
        merchant_id: UUID of the merchant.
        key: The raw Idempotency-Key header value.
        payload: Parsed request body dict.

    Returns:
        IdempotencyResult

    Raises:
        IdempotencyConflictError: If key is reused with a different payload.
        Merchant.DoesNotExist: If merchant_id is invalid.
    """
    if not Merchant.objects.filter(id=merchant_id).exists():
        raise Merchant.DoesNotExist(f"Merchant {merchant_id} does not exist.")

    incoming_hash = compute_request_hash(payload)

    try:
        with transaction.atomic():
            key_obj = IdempotencyKey.objects.create(
                merchant_id=merchant_id,
                key=key,
                request_hash=incoming_hash,
            )
        # INSERT succeeded — this is a fresh request.
        return IdempotencyResult(created=True, idempotency_key=key_obj)

    except IntegrityError:
        # Duplicate (merchant_id, key) — either a legitimate retry or a
        # conflicting request. Fetch the existing record to decide.
        key_obj = IdempotencyKey.objects.get(
            merchant_id=merchant_id,
            key=key,
        )

        # ── 24-HOUR EXPIRATION CHECK ──────────────────────────────────────
        from django.utils import timezone
        from datetime import timedelta
        if key_obj.created_at < timezone.now() - timedelta(hours=24):
            # Key has expired. It can be reused for a brand new request.
            # Delete the old record and try again.
            key_obj.delete()
            return resolve_idempotency(merchant_id, key, payload)

        if key_obj.request_hash != incoming_hash:
            # Same key, different payload → client bug / attack.
            raise IdempotencyConflictError(
                f"Idempotency key '{key}' was already used with a different "
                f"request payload. Reuse the same payload or use a new key."
            )

        # Same key, same payload → safe replay.
        return IdempotencyResult(
            created=False,
            idempotency_key=key_obj,
            cached_response=key_obj.response_body,
            cached_status=key_obj.response_status,
        )


def store_idempotency_response(
    idempotency_key: IdempotencyKey,
    status_code: int,
    response_body: dict,
) -> None:
    """
    Persist the API response so future duplicate requests get the
    exact same response replayed.

    Call this AFTER the payout has been created and the response is
    ready to send to the client. Only update the fields that matter
    for replay — never touch request_hash or merchant.

    Args:
        idempotency_key: The IdempotencyKey object from resolve_idempotency().
        status_code:     HTTP status code of the response (e.g. 201).
        response_body:   Serialized response dict to replay.
    """
    IdempotencyKey.objects.filter(pk=idempotency_key.pk).update(
        response_status=status_code,
        response_body=response_body,
    )
    # Use queryset .update() instead of key_obj.save() to avoid
    # touching updated_at or triggering unintended signals on the full object.


# ---------------------------------------------------------------------------
# Payout Creation — Core Business Transaction
# ---------------------------------------------------------------------------

@dataclass
class PayoutResult:
    """
    Returned by create_payout() to the API view.

    is_replay (bool): True if this was an idempotent duplicate request.
    status_code (int): HTTP status to use in the response.
    data (dict):       Serialised payout data to return as JSON.
    """
    is_replay: bool
    status_code: int
    data: dict


def create_payout(
    merchant_id: str,
    bank_account_id: str,
    amount: int,
    mode: str,
    idempotency_key_header: str,
    payload: dict,
) -> PayoutResult:
    """
    Create a payout atomically with full safety guarantees.

    Execution order (all inside ONE transaction):
    ┌────────────────────────────────────────────────────────────────────┐
    │ 1. BEGIN TRANSACTION                                               │
    │ 2. SELECT merchant FOR UPDATE  ← serialises concurrent requests   │
    │ 3. Resolve idempotency key     ← INSERT or detect duplicate        │
    │    └─ If duplicate & response cached → ROLLBACK + return replay   │
    │ 4. SELECT bank account         ← validate ownership               │
    │ 5. Compute balance via DB-level conditional aggregation            │
    │    └─ Safe: merchant lock prevents concurrent ledger writes        │
    │ 6. Insufficient funds check    ← pure integer comparison          │
    │ 7. INSERT Payout (PENDING)                                        │
    │ 8. INSERT LedgerEntry (DEBIT / PAYOUT_HOLD)                       │
    │ 9. UPDATE IdempotencyKey with response                            │
    │10. COMMIT                                                          │
    └────────────────────────────────────────────────────────────────────┘

    Why select_for_update() on Merchant?
        PostgreSQL acquires a row-level FOR UPDATE lock. Any other
        transaction attempting to lock the SAME merchant row (step 2)
        will block until this transaction commits or rolls back.
        This serialises all payout operations per merchant, making the
        balance check in step 5 race-free — no other transaction can
        INSERT a LedgerEntry for this merchant while we hold the lock.

    Equivalent SQL lock:
        SELECT * FROM merchants WHERE id = %s FOR UPDATE;

    Args:
        merchant_id:            UUID of the merchant.
        bank_account_id:        UUID of the destination bank account.
        amount:                 Amount in paise (must be positive).
        mode:                   PayoutMode value (IMPS/NEFT/RTGS/UPI).
        idempotency_key_header: Raw Idempotency-Key header value.
        payload:                Parsed request body dict for hash comparison.

    Returns:
        PayoutResult

    Raises:
        Merchant.DoesNotExist:     merchant_id is invalid or inactive.
        BankAccount.DoesNotExist:  account not found or not owned by merchant.
        InsufficientFundsError:    balance < amount.
        IdempotencyConflictError:  same key reused with different payload.
    """
    with transaction.atomic():
        # ── Step 2: Lock merchant row ──────────────────────────────────────
        # select_for_update() translates to:
        #   SELECT ... FROM merchants WHERE id = %s FOR UPDATE
        # All concurrent payout requests for this merchant will queue here.
        merchant = (
            Merchant.objects
            .select_for_update()
            .get(id=merchant_id, is_active=True)
        )

        # ── Step 3: Resolve idempotency ────────────────────────────────────
        # The inner transaction.atomic() in resolve_idempotency() becomes a
        # SAVEPOINT when nested inside our outer atomic block. An IntegrityError
        # from a duplicate INSERT only rolls back to the savepoint, leaving
        # the outer transaction intact and usable.
        idempotency_result = resolve_idempotency(
            merchant_id=merchant_id,
            key=idempotency_key_header,
            payload=payload,
        )

        if not idempotency_result.created:
            # Duplicate request — return the cached response without
            # creating anything. The outer transaction will be rolled back
            # cleanly since we raise no error; it just commits no writes.
            if idempotency_result.cached_response:
                return PayoutResult(
                    is_replay=True,
                    status_code=idempotency_result.cached_status,
                    data=idempotency_result.cached_response,
                )
            # First request is still in-flight (no cached response yet).
            # Tell the client to retry after a short delay.
            return PayoutResult(
                is_replay=True,
                status_code=202,
                data={
                    'detail': 'Payout is being processed. Retry with the same Idempotency-Key.',
                },
            )

        # ── Step 4: Validate bank account ownership ────────────────────────
        # Must belong to this merchant AND be verified.
        # Done inside the lock so we get a consistent view.
        try:
            bank_account = BankAccount.objects.get(
                id=bank_account_id,
                merchant=merchant,
                is_verified=True,
            )
        except BankAccount.DoesNotExist:
            raise BankAccount.DoesNotExist(
                f"Bank account {bank_account_id} not found, not verified, "
                f"or does not belong to merchant {merchant_id}."
            )

        # ── Step 5 & 6: DB-level balance check ────────────────────────────
        # get_balance() issues a single conditional-aggregate SQL query.
        # It is safe here because the merchant FOR UPDATE lock prevents any
        # concurrent transaction from writing a LedgerEntry for this merchant.
        #
        # Equivalent SQL:
        #   SELECT
        #     COALESCE(SUM(CASE WHEN entry_type='CREDIT' THEN amount ELSE 0 END),0)
        #   - COALESCE(SUM(CASE WHEN entry_type='DEBIT'  THEN amount ELSE 0 END),0)
        #   FROM ledger_entries WHERE merchant_id = %s;
        balance = get_balance(merchant_id)

        if balance < amount:
            raise InsufficientFundsError(
                f"Insufficient balance. "
                f"Available: {balance} paise (₹{balance/100:.2f}), "
                f"Requested: {amount} paise (₹{amount/100:.2f})."
            )

        # ── Step 7: Create Payout (PENDING) ───────────────────────────────
        payout = Payout.objects.create(
            merchant=merchant,
            bank_account=bank_account,
            amount=amount,
            mode=mode,
            status=PayoutStatus.PENDING,
            idempotency_key=idempotency_result.idempotency_key,
        )

        # ── Step 8: Create LedgerEntry (DEBIT / PAYOUT_HOLD) ──────────────
        # Debit the amount immediately to hold it. The funds will only be
        # released (credited back) if the payout FAILS or is CANCELLED.
        # On SUCCESS, the debit stands as the final settlement record.
        new_balance = balance - amount
        LedgerEntry.objects.create(
            merchant=merchant,
            payout=payout,
            entry_type=LedgerEntryType.DEBIT,
            amount=amount,
            balance_after=new_balance,
            description=(
                f"PAYOUT_HOLD: Payout {payout.id} "
                f"to account ending {bank_account.account_number[-4:]} "
                f"via {mode}"
            ),
        )

        # ── Step 9: Serialise response and store for idempotency replay ───
        response_data = {
            'id':              str(payout.id),
            'merchant_id':     str(merchant.id),
            'bank_account_id': str(bank_account.id),
            'amount':          payout.amount,
            'mode':            payout.mode,
            'status':          payout.status,
            'initiated_at':    payout.initiated_at.isoformat(),
        }
        store_idempotency_response(
            idempotency_result.idempotency_key,
            201,
            response_data,
        )

        # ── Step 10: COMMIT (implicit at end of with block) ────────────────
        return PayoutResult(is_replay=False, status_code=201, data=response_data)


# ---------------------------------------------------------------------------
# Payout Processing — Status Transitions (used by Celery worker)
# ---------------------------------------------------------------------------

def transition_payout_to_processing(payout_id: str) -> 'Payout | None':
    """
    Atomically move a payout from PENDING → PROCESSING using a
    Compare-And-Swap (CAS) UPDATE.

    This is the key idempotency guard for the worker:
      - Two workers racing on the same payout_id will both run this.
      - Django's .update() translates to a single atomic SQL statement:
            UPDATE payouts
            SET    status = 'PROCESSING'
            WHERE  id     = %s
              AND  status = 'PENDING';
      - Only ONE of the two workers will see `updated_rows = 1`.
      - The other sees `updated_rows = 0` and exits safely (returns None).

    This prevents double-processing entirely at the DB level, with no
    application-level locking or distributed locks required.

    Returns:
        Payout — if this worker successfully claimed the payout.
        None   — if the payout was already claimed or beyond PENDING.
    """
    updated_rows = Payout.objects.filter(
        id=payout_id,
        status=PayoutStatus.PENDING,
    ).update(status=PayoutStatus.PROCESSING)

    if updated_rows == 0:
        return None  # Already claimed by another worker, or already resolved.

    # Fetch the full object now that we own it.
    return Payout.objects.select_related('merchant', 'bank_account').get(id=payout_id)


def complete_payout(payout: 'Payout', reference_id: str) -> bool:
    """
    Atomically mark a payout as COMPLETED.

    Uses a guarded UPDATE (WHERE status='PROCESSING') so if another
    process already resolved this payout (e.g., via admin or a race),
    this call is a safe no-op.

    Args:
        payout:       The Payout instance currently in PROCESSING state.
        reference_id: UTR / gateway transaction ID from the payment rail.

    Returns:
        bool: True if the update applied, False if payout was already resolved.

    SQL:
        UPDATE payouts
        SET    status       = 'COMPLETED',
               reference_id = %s,
               processed_at = NOW()
        WHERE  id     = %s
          AND  status = 'PROCESSING';
    """
    from django.utils import timezone

    updated_rows = Payout.objects.filter(
        id=payout.id,
        status=PayoutStatus.PROCESSING,
    ).update(
        status=PayoutStatus.COMPLETED,
        reference_id=reference_id,
        processed_at=timezone.now(),
    )
    return updated_rows == 1


def fail_payout(payout: 'Payout', reason: str) -> bool:
    """
    Atomically mark a payout as FAILED and insert a CREDIT reversal
    ledger entry to release the held funds back to the merchant's balance.

    Both the status update and the reversal ledger entry are wrapped in
    a single transaction.atomic() so they either both succeed or both
    roll back — the ledger stays consistent.

    Guarded with WHERE status='PROCESSING' to be safe under duplicate
    task execution (idempotent: second call is a no-op).

    Args:
        payout: The Payout instance currently in PROCESSING state.
        reason: Human-readable failure reason (stored for debugging).

    Returns:
        bool: True if this call performed the transition, False if already done.

    SQL (conceptual):
        BEGIN;
        UPDATE payouts
        SET    status         = 'FAILED',
               failure_reason = %s,
               processed_at   = NOW()
        WHERE  id = %s AND status = 'PROCESSING';

        -- Only if above updated 1 row:
        INSERT INTO ledger_entries
          (merchant_id, payout_id, entry_type, amount, balance_after, description)
        VALUES (%s, %s, 'CREDIT', %s, %s, 'PAYOUT_REVERSAL: ...');
        COMMIT;
    """
    from django.utils import timezone

    with transaction.atomic():
        # Lock merchant to safely read balance for the reversal snapshot.
        merchant = Merchant.objects.select_for_update().get(id=payout.merchant_id)

        updated_rows = Payout.objects.filter(
            id=payout.id,
            status=PayoutStatus.PROCESSING,
        ).update(
            status=PayoutStatus.FAILED,
            failure_reason=reason,
            processed_at=timezone.now(),
        )

        if updated_rows == 0:
            # Already resolved by another worker. Do NOT double-credit.
            return False

        # Compute post-reversal balance for the snapshot field.
        balance_before_reversal = get_balance(merchant.id)
        balance_after_reversal  = balance_before_reversal + payout.amount

        LedgerEntry.objects.create(
            merchant=merchant,
            payout=payout,
            entry_type=LedgerEntryType.CREDIT,
            amount=payout.amount,
            balance_after=balance_after_reversal,
            description=(
                f"PAYOUT_REVERSAL: Payout {payout.id} failed — {reason}"
            ),
        )
        return True


def reset_processing_to_pending(payout_id: str, older_than_seconds: int = 30) -> bool:
    """
    Safety-net function used by the retry_stuck_payouts beat task.

    Resets a payout that has been stuck in PROCESSING for longer than
    `older_than_seconds` back to PENDING so it can be re-enqueued.

    Why can a payout get stuck in PROCESSING?
      - Worker picked it up, crashed after the CAS update but before
        completing/failing it.
      - CELERY_TASK_REJECT_ON_WORKER_LOST=True should handle most cases,
        but this is a belt-and-suspenders safety net.

    Args:
        payout_id:          UUID string of the payout.
        older_than_seconds: Only reset if stuck for at least this long.

    Returns:
        bool: True if reset was applied.
    """
    from django.utils import timezone
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(seconds=older_than_seconds)

    updated_rows = Payout.objects.filter(
        id=payout_id,
        status=PayoutStatus.PROCESSING,
        initiated_at__lte=cutoff,   # Only touch genuinely old ones.
    ).update(status=PayoutStatus.PENDING)

    return updated_rows == 1
