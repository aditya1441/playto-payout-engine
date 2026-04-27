import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import BigIntegerField, Case, IntegerField, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

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

logger = logging.getLogger(__name__)


class IdempotencyConflictError(Exception):
    """Same Idempotency-Key reused with a different request body."""


class InsufficientFundsError(Exception):
    """Merchant balance is below the requested payout amount."""


@dataclass
class IdempotencyResult:
    created: bool
    idempotency_key: IdempotencyKey
    cached_response: dict | None = None
    cached_status: int | None = None


@dataclass
class PayoutResult:
    is_replay: bool
    status_code: int
    data: dict


def get_balance(merchant_id: str) -> int:
    """
    Compute a merchant's balance via conditional aggregation.

    A single SQL query sums CREDITs and DEBITs independently so we never
    fetch raw rows into Python for arithmetic. The merchant row does not
    store a balance field — this aggregate is the authoritative source.

    Raises:
        Merchant.DoesNotExist: if merchant_id is invalid.
    """
    if not Merchant.objects.filter(id=merchant_id).exists():
        raise Merchant.DoesNotExist(f"Merchant {merchant_id} does not exist.")

    result = LedgerEntry.objects.filter(merchant_id=merchant_id).aggregate(
        total_credits=Coalesce(
            Sum(Case(When(entry_type=LedgerEntryType.CREDIT, then='amount'), default=Value(0), output_field=IntegerField())),
            Value(0),
        ),
        total_debits=Coalesce(
            Sum(Case(When(entry_type=LedgerEntryType.DEBIT, then='amount'), default=Value(0), output_field=IntegerField())),
            Value(0),
        ),
    )
    return result['total_credits'] - result['total_debits']


def get_held_balance(merchant_id: str) -> int:
    """Sum of amounts currently locked in PENDING or PROCESSING payouts."""
    held = Payout.objects.filter(
        merchant_id=merchant_id,
        status__in=[PayoutStatus.PENDING, PayoutStatus.PROCESSING],
    ).aggregate(total=Sum('amount'))['total']
    return held or 0


def compute_request_hash(payload: dict) -> str:
    """
    Stable SHA-256 fingerprint of a request body.
    Keys are sorted before serialisation so field order does not matter.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def resolve_idempotency(merchant_id: str, key: str, payload: dict) -> IdempotencyResult:
    """
    Idempotency gate. Returns an IdempotencyResult indicating whether this
    is a fresh request or a replay.

    Uses a blind INSERT rather than get_or_create to avoid the TOCTOU window
    where two concurrent requests both observe the key as absent and then race
    to insert it. The database unique constraint on (merchant_id, key) resolves
    the race; we rely on IntegrityError as the signal.

    Keys older than 24 hours are treated as expired and deleted, allowing the
    same key string to be reused for a new operation.

    Raises:
        IdempotencyConflictError: same key, different request body.
        Merchant.DoesNotExist: unknown merchant_id.
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
        return IdempotencyResult(created=True, idempotency_key=key_obj)

    except IntegrityError:
        key_obj = IdempotencyKey.objects.get(merchant_id=merchant_id, key=key)

        if key_obj.created_at < timezone.now() - timedelta(hours=24):
            key_obj.delete()
            return resolve_idempotency(merchant_id, key, payload)

        if key_obj.request_hash != incoming_hash:
            raise IdempotencyConflictError(
                f"Idempotency key '{key}' was already used with a different request body."
            )

        return IdempotencyResult(
            created=False,
            idempotency_key=key_obj,
            cached_response=key_obj.response_body,
            cached_status=key_obj.response_status,
        )


def store_idempotency_response(idempotency_key: IdempotencyKey, status_code: int, response_body: dict) -> None:
    """Persist the API response against the key so duplicates get the same reply."""
    IdempotencyKey.objects.filter(pk=idempotency_key.pk).update(
        response_status=status_code,
        response_body=response_body,
    )


def create_payout(
    merchant_id: str,
    bank_account_id: str,
    amount: int,
    mode: str,
    idempotency_key_header: str,
    payload: dict,
) -> PayoutResult:
    """
    Atomically create a payout with full safety guarantees.

    The entire operation runs inside a single database transaction:
    1. SELECT merchant FOR UPDATE — serialises concurrent payout requests
       for the same merchant at the DB row level.
    2. Idempotency resolution — duplicate key returns the cached response
       without creating a new payout.
    3. Balance check — computed via DB aggregate while the merchant lock is held,
       so no concurrent write can change the balance between the check and the debit.
    4. INSERT Payout (PENDING) + LedgerEntry (DEBIT).

    Raises:
        Merchant.DoesNotExist: merchant not found or inactive.
        BankAccount.DoesNotExist: account not found, not verified, or wrong merchant.
        InsufficientFundsError: balance < requested amount.
        IdempotencyConflictError: same key, different payload.
    """
    with transaction.atomic():
        merchant = Merchant.objects.select_for_update().get(id=merchant_id, is_active=True)

        idempotency_result = resolve_idempotency(
            merchant_id=merchant_id,
            key=idempotency_key_header,
            payload=payload,
        )

        if not idempotency_result.created:
            if idempotency_result.cached_response:
                return PayoutResult(
                    is_replay=True,
                    status_code=idempotency_result.cached_status,
                    data=idempotency_result.cached_response,
                )
            return PayoutResult(
                is_replay=True,
                status_code=202,
                data={'detail': 'Request is being processed. Retry with the same Idempotency-Key.'},
            )

        try:
            bank_account = BankAccount.objects.get(
                id=bank_account_id,
                merchant=merchant,
                is_verified=True,
            )
        except BankAccount.DoesNotExist:
            raise BankAccount.DoesNotExist(
                f"Bank account {bank_account_id} not found, unverified, or does not belong to merchant {merchant_id}."
            )

        balance = get_balance(merchant_id)
        if balance < amount:
            raise InsufficientFundsError(
                f"Insufficient balance. Available: {balance} paise, requested: {amount} paise."
            )

        payout = Payout.objects.create(
            merchant=merchant,
            bank_account=bank_account,
            amount=amount,
            mode=mode,
            status=PayoutStatus.PENDING,
            idempotency_key=idempotency_result.idempotency_key,
        )

        new_balance = balance - amount
        LedgerEntry.objects.create(
            merchant=merchant,
            payout=payout,
            entry_type=LedgerEntryType.DEBIT,
            amount=amount,
            balance_after=new_balance,
            description=f"PAYOUT_HOLD: {payout.id} to account ...{bank_account.account_number[-4:]} via {mode}",
        )

        response_data = {
            'id':              str(payout.id),
            'merchant_id':     str(merchant.id),
            'bank_account_id': str(bank_account.id),
            'amount':          payout.amount,
            'mode':            payout.mode,
            'status':          payout.status,
            'initiated_at':    payout.initiated_at.isoformat(),
        }
        store_idempotency_response(idempotency_result.idempotency_key, 201, response_data)

        return PayoutResult(is_replay=False, status_code=201, data=response_data)


def transition_payout_to_processing(payout_id: str) -> 'Payout | None':
    """
    CAS transition: PENDING → PROCESSING.

    Issues a single atomic UPDATE ... WHERE status='PENDING'.
    Exactly one worker wins — all others get updated_rows=0 and skip safely.
    """
    updated_rows = Payout.objects.filter(
        id=payout_id,
        status=PayoutStatus.PENDING,
    ).update(status=PayoutStatus.PROCESSING)

    if updated_rows == 0:
        return None

    return Payout.objects.select_related('merchant', 'bank_account').get(id=payout_id)


def complete_payout(payout: 'Payout', reference_id: str) -> bool:
    """
    Mark a payout COMPLETED. Guarded with WHERE status='PROCESSING' so
    concurrent or duplicate calls are safe no-ops.
    """
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
    Atomically mark a payout FAILED and credit the held funds back to the merchant.

    The status update and the reversal LedgerEntry are wrapped in one transaction
    so the ledger is never left inconsistent. The WHERE status='PROCESSING' guard
    prevents double-reversal if called twice.
    """
    with transaction.atomic():
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
            return False

        balance_after = get_balance(merchant.id) + payout.amount
        LedgerEntry.objects.create(
            merchant=merchant,
            payout=payout,
            entry_type=LedgerEntryType.CREDIT,
            amount=payout.amount,
            balance_after=balance_after,
            description=f"PAYOUT_REVERSAL: {payout.id} failed — {reason}",
        )
        return True


def reset_processing_to_pending(payout_id: str, older_than_seconds: int = 30) -> bool:
    """
    Safety-net for worker crashes.

    If a payout has been stuck in PROCESSING for longer than older_than_seconds,
    reset it to PENDING so it can be re-enqueued by the periodic beat task.
    """
    cutoff = timezone.now() - timedelta(seconds=older_than_seconds)
    updated_rows = Payout.objects.filter(
        id=payout_id,
        status=PayoutStatus.PROCESSING,
        initiated_at__lte=cutoff,
    ).update(status=PayoutStatus.PENDING)
    return updated_rows == 1
