import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import BigIntegerField, Case, Sum, Value, When
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
    pass


class InsufficientFundsError(Exception):
    pass


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
    if not Merchant.objects.filter(id=merchant_id).exists():
        raise Merchant.DoesNotExist(f"Merchant {merchant_id} does not exist.")

    # BigIntegerField needed — IntegerField overflows above ~₹2.14 Cr in paise
    result = LedgerEntry.objects.filter(merchant_id=merchant_id).aggregate(
        total_credits=Coalesce(
            Sum(Case(
                When(entry_type=LedgerEntryType.CREDIT, then='amount'),
                default=Value(0), output_field=BigIntegerField(),
            )),
            Value(0), output_field=BigIntegerField(),
        ),
        total_debits=Coalesce(
            Sum(Case(
                When(entry_type=LedgerEntryType.DEBIT, then='amount'),
                default=Value(0), output_field=BigIntegerField(),
            )),
            Value(0), output_field=BigIntegerField(),
        ),
    )
    return result['total_credits'] - result['total_debits']


def get_held_balance(merchant_id: str) -> int:
    held = Payout.objects.filter(
        merchant_id=merchant_id,
        status__in=[PayoutStatus.PENDING, PayoutStatus.PROCESSING],
    ).aggregate(
        total=Coalesce(Sum('amount'), Value(0), output_field=BigIntegerField())
    )['total']
    return held


def compute_request_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def resolve_idempotency(merchant_id: str, key: str, payload: dict) -> IdempotencyResult:
    """INSERT-first idempotency. The unique constraint on (merchant, key) is the guard."""
    if not Merchant.objects.filter(id=merchant_id).exists():
        raise Merchant.DoesNotExist(f"Merchant {merchant_id} does not exist.")

    incoming_hash = compute_request_hash(payload)
    expires_at = timezone.now() + timedelta(hours=24)

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

        # Don't delete expired keys inline — periodic task handles that
        if key_obj.expires_at and key_obj.expires_at < timezone.now():
            raise IdempotencyConflictError(
                f"Idempotency key '{key}' has expired. Use a new key."
            )

        if key_obj.request_hash != incoming_hash:
            raise IdempotencyConflictError(
                f"Idempotency key '{key}' already used with a different request body."
            )

        return IdempotencyResult(
            created=False,
            idempotency_key=key_obj,
            cached_response=key_obj.response_body,
            cached_status=key_obj.response_status,
        )


def store_idempotency_response(idempotency_key: IdempotencyKey, status_code: int, response_body: dict) -> None:
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
    with transaction.atomic():
        # Row-level lock — serializes payouts per merchant
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
                id=bank_account_id, merchant=merchant, is_verified=True,
            )
        except BankAccount.DoesNotExist:
            raise BankAccount.DoesNotExist(
                f"Bank account {bank_account_id} not found or doesn't belong to this merchant."
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
            description=f"PAYOUT_HOLD: {payout.id} to ...{bank_account.account_number[-4:]} via {mode}",
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

        from .tasks import process_payout
        transaction.on_commit(lambda: process_payout.apply_async(args=[str(payout.id)]))

        return PayoutResult(is_replay=False, status_code=201, data=response_data)


def transition_payout_to_processing(payout_id: str) -> 'Payout | None':
    rows = Payout.objects.filter(
        id=payout_id, status=PayoutStatus.PENDING,
    ).update(status=PayoutStatus.PROCESSING)
    if rows == 0:
        return None
    return Payout.objects.select_related('merchant', 'bank_account').get(id=payout_id)


def complete_payout(payout: 'Payout', reference_id: str) -> bool:
    rows = Payout.objects.filter(
        id=payout.id, status=PayoutStatus.PROCESSING,
    ).update(
        status=PayoutStatus.COMPLETED,
        reference_id=reference_id,
        processed_at=timezone.now(),
    )
    return rows == 1


def fail_payout(payout: 'Payout', reason: str) -> bool:
    """Atomically mark payout as failed and reverse the held funds."""
    with transaction.atomic():
        merchant = Merchant.objects.select_for_update().get(id=payout.merchant_id)

        rows = Payout.objects.filter(
            id=payout.id, status=PayoutStatus.PROCESSING,
        ).update(
            status=PayoutStatus.FAILED,
            failure_reason=reason,
            processed_at=timezone.now(),
        )
        if rows == 0:
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
    cutoff = timezone.now() - timedelta(seconds=older_than_seconds)
    rows = Payout.objects.filter(
        id=payout_id, status=PayoutStatus.PROCESSING, initiated_at__lte=cutoff,
    ).update(status=PayoutStatus.PENDING)
    return rows == 1


def cleanup_expired_idempotency_keys() -> int:
    deleted_count, _ = IdempotencyKey.objects.filter(
        expires_at__lt=timezone.now(),
    ).delete()
    logger.info("Cleaned up %d expired idempotency keys", deleted_count)
    return deleted_count
