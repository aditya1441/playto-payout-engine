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

from .models import IdempotencyKey, LedgerEntry, LedgerEntryType, Merchant


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------

class IdempotencyConflictError(Exception):
    """
    Raised when the same Idempotency-Key is reused with a DIFFERENT
    request body. This signals a client programming error.
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
    The core idempotency gate. Call this BEFORE creating a payout.

    Algorithm (race-safe):
    ┌─────────────────────────────────────────────────────────────┐
    │ 1. Hash the incoming payload.                               │
    │ 2. Attempt to INSERT a new IdempotencyKey row.              │
    │    ├─ INSERT succeeds → brand new request → created=True.   │
    │    └─ IntegrityError (duplicate) →                          │
    │       a. SELECT the existing row.                           │
    │       b. Compare request_hash.                              │
    │          ├─ Hash matches → safe replay → created=False.     │
    │          └─ Hash differs → CONFLICT → raise error.          │
    └─────────────────────────────────────────────────────────────┘

    Why not get_or_create()?
        get_or_create() has a TOCTOU window: it SELECTs first, then
        INSERTs. Two concurrent requests can both SELECT "not found"
        and then both attempt INSERT. The second INSERT raises
        IntegrityError anyway, but Django's get_or_create catches it
        internally and retries the SELECT — which works, but hides the
        race. Here we make the race explicit and intentional.

    Why transaction.atomic() on the INSERT?
        To ensure the INSERT and any subsequent work within the caller's
        transaction is rolled back cleanly if the caller raises an
        exception AFTER we've inserted the key but BEFORE we store the
        response. The key record is therefore provisional until
        store_idempotency_response() is called.

    Equivalent SQL (INSERT ... ON CONFLICT DO NOTHING style):
        BEGIN;
        INSERT INTO idempotency_keys (merchant_id, key, request_hash, ...)
        VALUES (%s, %s, %s, ...)
        ON CONFLICT (merchant_id, key) DO NOTHING;

        -- If 0 rows inserted, read the existing row:
        SELECT * FROM idempotency_keys
        WHERE merchant_id = %s AND key = %s;
        COMMIT;

    Args:
        merchant_id: UUID of the merchant making the request.
        key:         The raw Idempotency-Key header value.
        payload:     Parsed request body dict.

    Returns:
        IdempotencyResult

    Raises:
        IdempotencyConflictError: if key reused with different body.
        Merchant.DoesNotExist:    if merchant_id is invalid.
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

