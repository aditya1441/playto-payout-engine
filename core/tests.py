"""
Unit tests for the balance calculation and idempotency services.

Run with:
    python3 manage.py test core
"""
import uuid
from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase

from core.models import (
    BankAccount, IdempotencyKey, LedgerEntry, LedgerEntryType,
    Merchant, Payout, PayoutStatus,
)
from core.services import (
    IdempotencyConflictError,
    IdempotencyResult,
    InsufficientFundsError,
    compute_request_hash,
    create_payout,
    get_balance,
    resolve_idempotency,
    store_idempotency_response,
)


class BalanceServiceTests(TestCase):

    def setUp(self):
        self.merchant = Merchant.objects.create(
            name='Test Merchant',
            email='test@merchant.com',
        )

    def _add_entry(self, entry_type, amount, balance_after=0):
        LedgerEntry.objects.create(
            merchant=self.merchant,
            entry_type=entry_type,
            amount=amount,
            balance_after=balance_after,
        )

    def test_balance_zero_with_no_entries(self):
        """A new merchant with no ledger entries must have balance = 0."""
        self.assertEqual(get_balance(self.merchant.id), 0)

    def test_balance_with_only_credits(self):
        """SUM of credits with no debits = total credits."""
        self._add_entry(LedgerEntryType.CREDIT, 10000)  # ₹100
        self._add_entry(LedgerEntryType.CREDIT, 5000)   # ₹50
        self.assertEqual(get_balance(self.merchant.id), 15000)

    def test_balance_with_credits_and_debits(self):
        """Credits - Debits = correct balance."""
        self._add_entry(LedgerEntryType.CREDIT, 50000)  # ₹500
        self._add_entry(LedgerEntryType.DEBIT,  20000)  # ₹200
        self.assertEqual(get_balance(self.merchant.id), 30000)  # ₹300

    def test_balance_does_not_go_below_zero_if_debits_exceed_credits(self):
        """
        The DB calculation will return negative if debits > credits.
        This is intentional — the service layer is not responsible for
        enforcing the business rule; that's the Payout service's job.
        """
        self._add_entry(LedgerEntryType.CREDIT, 10000)
        self._add_entry(LedgerEntryType.DEBIT,  15000)
        self.assertEqual(get_balance(self.merchant.id), -5000)

    def test_balance_isolation_between_merchants(self):
        """Entries from one merchant must not affect another merchant's balance."""
        other_merchant = Merchant.objects.create(
            name='Other Merchant',
            email='other@merchant.com',
        )
        self._add_entry(LedgerEntryType.CREDIT, 10000)
        # other_merchant has no entries
        self.assertEqual(get_balance(other_merchant.id), 0)

    def test_raises_for_invalid_merchant(self):
        """get_balance must raise Merchant.DoesNotExist for an unknown ID."""
        with self.assertRaises(Merchant.DoesNotExist):
            get_balance(uuid.uuid4())


class IdempotencyServiceTests(TestCase):

    def setUp(self):
        self.merchant = Merchant.objects.create(
            name='Idempotency Test Merchant',
            email='idempotency@merchant.com',
        )
        self.payload = {'amount': 10000, 'bank_account_id': str(uuid.uuid4())}
        self.key = 'order-abc-123'

    # ------------------------------------------------------------------
    # compute_request_hash
    # ------------------------------------------------------------------

    def test_hash_is_deterministic(self):
        """Same payload must always produce the same hash."""
        h1 = compute_request_hash(self.payload)
        h2 = compute_request_hash(self.payload)
        self.assertEqual(h1, h2)

    def test_hash_is_key_order_independent(self):
        """JSON key order must not affect the hash."""
        payload_a = {'amount': 10000, 'bank_account_id': 'x'}
        payload_b = {'bank_account_id': 'x', 'amount': 10000}
        self.assertEqual(compute_request_hash(payload_a), compute_request_hash(payload_b))

    def test_hash_differs_for_different_payloads(self):
        """Different payloads must produce different hashes."""
        h1 = compute_request_hash({'amount': 10000})
        h2 = compute_request_hash({'amount': 20000})
        self.assertNotEqual(h1, h2)

    def test_hash_is_64_chars(self):
        """SHA-256 hex digest must be exactly 64 characters."""
        h = compute_request_hash(self.payload)
        self.assertEqual(len(h), 64)

    # ------------------------------------------------------------------
    # resolve_idempotency — fresh request
    # ------------------------------------------------------------------

    def test_fresh_key_returns_created_true(self):
        """A new key must be created and result.created must be True."""
        result = resolve_idempotency(self.merchant.id, self.key, self.payload)
        self.assertIsInstance(result, IdempotencyResult)
        self.assertTrue(result.created)
        self.assertIsNone(result.cached_response)
        self.assertIsNone(result.cached_status)
        # DB row must exist
        self.assertTrue(
            IdempotencyKey.objects.filter(
                merchant_id=self.merchant.id, key=self.key
            ).exists()
        )

    # ------------------------------------------------------------------
    # resolve_idempotency — exact replay (same key, same body)
    # ------------------------------------------------------------------

    def test_duplicate_key_same_payload_returns_created_false(self):
        """Exact retry must return created=False and replay the cached response."""
        # First request
        result1 = resolve_idempotency(self.merchant.id, self.key, self.payload)
        store_idempotency_response(result1.idempotency_key, 201, {'id': 'payout-1'})

        # Duplicate request with same payload
        result2 = resolve_idempotency(self.merchant.id, self.key, self.payload)
        self.assertFalse(result2.created)
        self.assertEqual(result2.cached_status, 201)
        self.assertEqual(result2.cached_response, {'id': 'payout-1'})

    def test_duplicate_key_before_response_stored_returns_none_cached(self):
        """
        If the first request is still in-flight when the retry arrives,
        response_body will be None. The caller should handle this (e.g. 202).
        """
        resolve_idempotency(self.merchant.id, self.key, self.payload)
        # Do NOT call store_idempotency_response — simulates in-flight state

        result2 = resolve_idempotency(self.merchant.id, self.key, self.payload)
        self.assertFalse(result2.created)
        self.assertIsNone(result2.cached_response)
        self.assertIsNone(result2.cached_status)

    # ------------------------------------------------------------------
    # resolve_idempotency — conflict (same key, different body)
    # ------------------------------------------------------------------

    def test_duplicate_key_different_payload_raises_conflict(self):
        """Reusing a key with a different payload must raise IdempotencyConflictError."""
        resolve_idempotency(self.merchant.id, self.key, self.payload)

        different_payload = {'amount': 99999, 'bank_account_id': 'different'}
        with self.assertRaises(IdempotencyConflictError):
            resolve_idempotency(self.merchant.id, self.key, different_payload)

    # ------------------------------------------------------------------
    # resolve_idempotency — key isolation between merchants
    # ------------------------------------------------------------------

    def test_same_key_string_different_merchants_are_independent(self):
        """Two merchants may use the same key string without collision."""
        other_merchant = Merchant.objects.create(
            name='Other', email='other2@merchant.com'
        )
        r1 = resolve_idempotency(self.merchant.id, self.key, self.payload)
        r2 = resolve_idempotency(other_merchant.id, self.key, self.payload)
        # Both must be created independently
        self.assertTrue(r1.created)
        self.assertTrue(r2.created)
        self.assertNotEqual(r1.idempotency_key.pk, r2.idempotency_key.pk)

    # ------------------------------------------------------------------
    # resolve_idempotency — invalid merchant
    # ------------------------------------------------------------------

    def test_invalid_merchant_raises_does_not_exist(self):
        """Must raise Merchant.DoesNotExist for an unknown merchant ID."""
        with self.assertRaises(Merchant.DoesNotExist):
            resolve_idempotency(uuid.uuid4(), self.key, self.payload)

    # ------------------------------------------------------------------
    # Race condition — simulated via mocking
    # ------------------------------------------------------------------

    def test_race_condition_two_concurrent_inserts(self):
        """
        Simulate two workers racing to INSERT the same idempotency key.
        Worker 1 succeeds; Worker 2 gets IntegrityError and must fall
        through to the GET path, returning created=False.

        We mock IdempotencyKey.objects.create to raise IntegrityError on
        the second call, then pre-create the key to make the .get() succeed.
        """
        # Pre-create the key in DB (simulates Worker 1 having won the race)
        existing_key = IdempotencyKey.objects.create(
            merchant_id=self.merchant.id,
            key=self.key,
            request_hash=compute_request_hash(self.payload),
        )
        store_idempotency_response(existing_key, 201, {'id': 'payout-race'})

        # Now simulate Worker 2: its create() raises IntegrityError
        with patch.object(
            IdempotencyKey.objects, 'create', side_effect=IntegrityError
        ):
            result = resolve_idempotency(self.merchant.id, self.key, self.payload)

        self.assertFalse(result.created)
        self.assertEqual(result.cached_response, {'id': 'payout-race'})
        self.assertEqual(result.cached_status, 201)

    # ------------------------------------------------------------------
    # store_idempotency_response
    # ------------------------------------------------------------------

    def test_store_response_persists_to_db(self):
        """store_idempotency_response must persist status and body to DB."""
        result = resolve_idempotency(self.merchant.id, self.key, self.payload)
        store_idempotency_response(result.idempotency_key, 201, {'payout_id': 'xyz'})

        refreshed = IdempotencyKey.objects.get(pk=result.idempotency_key.pk)
        self.assertEqual(refreshed.response_status, 201)
        self.assertEqual(refreshed.response_body, {'payout_id': 'xyz'})


class CreatePayoutTests(TestCase):
    """
    Integration tests for create_payout().
    Uses an in-memory SQLite DB; tests all paths through the atomic transaction.
    """

    def setUp(self):
        self.merchant = Merchant.objects.create(
            name='Payout Merchant', email='payout@merchant.com'
        )
        self.bank_account = BankAccount.objects.create(
            merchant=self.merchant,
            account_holder_name='Test Holder',
            account_number='123456789012',
            ifsc_code='HDFC0001234',
            is_verified=True,
        )
        self.key = 'unique-idempotency-key-001'
        self.payload = {
            'merchant_id':     str(self.merchant.id),
            'bank_account_id': str(self.bank_account.id),
            'amount':          5000,
            'mode':            'IMPS',
        }

        # Give the merchant ₹200 (20000 paise) of balance.
        LedgerEntry.objects.create(
            merchant=self.merchant,
            entry_type=LedgerEntryType.CREDIT,
            amount=20000,
            balance_after=20000,
            description='Initial top-up',
        )

    def _create(self, key=None, payload=None):
        """Helper to call create_payout with default test values."""
        p = payload or self.payload
        return create_payout(
            merchant_id=p['merchant_id'],
            bank_account_id=p['bank_account_id'],
            amount=p['amount'],
            mode=p['mode'],
            idempotency_key_header=key or self.key,
            payload=p,
        )

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_successful_payout_creates_payout_and_ledger_entry(self):
        """A valid request must create one Payout and one DEBIT LedgerEntry."""
        result = self._create()

        self.assertFalse(result.is_replay)
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.data['status'], PayoutStatus.PENDING)
        self.assertEqual(result.data['amount'], 5000)

        self.assertEqual(Payout.objects.count(), 1)
        payout = Payout.objects.first()
        self.assertEqual(payout.status, PayoutStatus.PENDING)
        self.assertEqual(payout.amount, 5000)

        debits = LedgerEntry.objects.filter(entry_type=LedgerEntryType.DEBIT)
        self.assertEqual(debits.count(), 1)
        self.assertEqual(debits.first().amount, 5000)
        self.assertEqual(debits.first().balance_after, 15000)  # 20000 - 5000

    def test_balance_reduced_after_payout(self):
        """Post-payout balance must reflect the debit."""
        self._create()
        self.assertEqual(get_balance(self.merchant.id), 15000)

    def test_payout_linked_to_idempotency_key(self):
        """The created Payout must reference the IdempotencyKey."""
        self._create()
        payout = Payout.objects.first()
        self.assertIsNotNone(payout.idempotency_key)
        self.assertEqual(payout.idempotency_key.key, self.key)

    # ------------------------------------------------------------------
    # Insufficient funds
    # ------------------------------------------------------------------

    def test_insufficient_funds_raises_error(self):
        """Amount > balance must raise InsufficientFundsError."""
        high_amount_payload = {**self.payload, 'amount': 999999}
        with self.assertRaises(InsufficientFundsError):
            self._create(payload=high_amount_payload)

    def test_insufficient_funds_creates_no_records(self):
        """On InsufficientFundsError, NO Payout or extra LedgerEntry must be created."""
        high_amount_payload = {**self.payload, 'amount': 999999}
        try:
            self._create(payload=high_amount_payload)
        except InsufficientFundsError:
            pass
        self.assertEqual(Payout.objects.count(), 0)
        # Only the original credit entry should exist.
        self.assertEqual(LedgerEntry.objects.count(), 1)

    # ------------------------------------------------------------------
    # Idempotency replay
    # ------------------------------------------------------------------

    def test_duplicate_request_returns_cached_response(self):
        """Second request with same key returns is_replay=True and cached data."""
        result1 = self._create()
        result2 = self._create()  # Same key, same payload

        self.assertFalse(result1.is_replay)
        self.assertTrue(result2.is_replay)
        self.assertEqual(result2.data['id'], result1.data['id'])  # Same payout
        self.assertEqual(Payout.objects.count(), 1)  # NOT duplicated

    def test_duplicate_request_does_not_debit_twice(self):
        """Balance must only be debited once even if the same request is sent twice."""
        self._create()
        self._create()  # Duplicate
        self.assertEqual(get_balance(self.merchant.id), 15000)  # Debited once only

    def test_different_keys_create_independent_payouts(self):
        """Two distinct idempotency keys must each create their own payout."""
        self._create(key='key-001')
        self._create(key='key-002')
        self.assertEqual(Payout.objects.count(), 2)
        self.assertEqual(get_balance(self.merchant.id), 10000)  # 20000 - 5000 - 5000

    # ------------------------------------------------------------------
    # Bank account validation
    # ------------------------------------------------------------------

    def test_wrong_bank_account_raises_error(self):
        """A bank account belonging to a different merchant must be rejected."""
        other_merchant = Merchant.objects.create(
            name='Other', email='other3@merchant.com'
        )
        other_account = BankAccount.objects.create(
            merchant=other_merchant,
            account_holder_name='Other Holder',
            account_number='999999999999',
            ifsc_code='ICIC0001234',
            is_verified=True,
        )
        bad_payload = {**self.payload, 'bank_account_id': str(other_account.id)}
        with self.assertRaises(BankAccount.DoesNotExist):
            self._create(payload=bad_payload)

    def test_unverified_bank_account_raises_error(self):
        """An unverified bank account must be rejected."""
        unverified = BankAccount.objects.create(
            merchant=self.merchant,
            account_holder_name='Unverified',
            account_number='111111111111',
            ifsc_code='SBIN0001234',
            is_verified=False,
        )
        bad_payload = {**self.payload, 'bank_account_id': str(unverified.id)}
        with self.assertRaises(BankAccount.DoesNotExist):
            self._create(payload=bad_payload)
