
import uuid
from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase, TransactionTestCase
import concurrent.futures
from django.db import connection

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
        
        self.assertEqual(get_balance(self.merchant.id), 0)

    def test_balance_with_only_credits(self):
        
        self._add_entry(LedgerEntryType.CREDIT, 10000)  
        self._add_entry(LedgerEntryType.CREDIT, 5000)   
        self.assertEqual(get_balance(self.merchant.id), 15000)

    def test_balance_with_credits_and_debits(self):
        
        self._add_entry(LedgerEntryType.CREDIT, 50000)  
        self._add_entry(LedgerEntryType.DEBIT,  20000)  
        self.assertEqual(get_balance(self.merchant.id), 30000)  

    def test_balance_does_not_go_below_zero_if_debits_exceed_credits(self):
        
        self._add_entry(LedgerEntryType.CREDIT, 10000)
        self._add_entry(LedgerEntryType.DEBIT,  15000)
        self.assertEqual(get_balance(self.merchant.id), -5000)

    def test_balance_isolation_between_merchants(self):
        
        other_merchant = Merchant.objects.create(
            name='Other Merchant',
            email='other@merchant.com',
        )
        self._add_entry(LedgerEntryType.CREDIT, 10000)
        
        self.assertEqual(get_balance(other_merchant.id), 0)

    def test_raises_for_invalid_merchant(self):
        
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

    
    
    

    def test_hash_is_deterministic(self):
        
        h1 = compute_request_hash(self.payload)
        h2 = compute_request_hash(self.payload)
        self.assertEqual(h1, h2)

    def test_hash_is_key_order_independent(self):
        
        payload_a = {'amount': 10000, 'bank_account_id': 'x'}
        payload_b = {'bank_account_id': 'x', 'amount': 10000}
        self.assertEqual(compute_request_hash(payload_a), compute_request_hash(payload_b))

    def test_hash_differs_for_different_payloads(self):
        
        h1 = compute_request_hash({'amount': 10000})
        h2 = compute_request_hash({'amount': 20000})
        self.assertNotEqual(h1, h2)

    def test_hash_is_64_chars(self):
        
        h = compute_request_hash(self.payload)
        self.assertEqual(len(h), 64)

    
    
    

    def test_fresh_key_returns_created_true(self):
        
        result = resolve_idempotency(self.merchant.id, self.key, self.payload)
        self.assertIsInstance(result, IdempotencyResult)
        self.assertTrue(result.created)
        self.assertIsNone(result.cached_response)
        self.assertIsNone(result.cached_status)
        
        self.assertTrue(
            IdempotencyKey.objects.filter(
                merchant_id=self.merchant.id, key=self.key
            ).exists()
        )

    
    
    

    def test_duplicate_key_same_payload_returns_created_false(self):
        
        
        result1 = resolve_idempotency(self.merchant.id, self.key, self.payload)
        store_idempotency_response(result1.idempotency_key, 201, {'id': 'payout-1'})

        
        result2 = resolve_idempotency(self.merchant.id, self.key, self.payload)
        self.assertFalse(result2.created)
        self.assertEqual(result2.cached_status, 201)
        self.assertEqual(result2.cached_response, {'id': 'payout-1'})

    def test_duplicate_key_before_response_stored_returns_none_cached(self):
        
        resolve_idempotency(self.merchant.id, self.key, self.payload)
        

        result2 = resolve_idempotency(self.merchant.id, self.key, self.payload)
        self.assertFalse(result2.created)
        self.assertIsNone(result2.cached_response)
        self.assertIsNone(result2.cached_status)

    
    
    

    def test_duplicate_key_different_payload_raises_conflict(self):
        
        resolve_idempotency(self.merchant.id, self.key, self.payload)

        different_payload = {'amount': 99999, 'bank_account_id': 'different'}
        with self.assertRaises(IdempotencyConflictError):
            resolve_idempotency(self.merchant.id, self.key, different_payload)

    
    
    

    def test_same_key_string_different_merchants_are_independent(self):
        
        other_merchant = Merchant.objects.create(
            name='Other', email='other2@merchant.com'
        )
        r1 = resolve_idempotency(self.merchant.id, self.key, self.payload)
        r2 = resolve_idempotency(other_merchant.id, self.key, self.payload)
        
        self.assertTrue(r1.created)
        self.assertTrue(r2.created)
        self.assertNotEqual(r1.idempotency_key.pk, r2.idempotency_key.pk)

    
    
    

    def test_invalid_merchant_raises_does_not_exist(self):
        
        with self.assertRaises(Merchant.DoesNotExist):
            resolve_idempotency(uuid.uuid4(), self.key, self.payload)

    
    
    

    def test_race_condition_two_concurrent_inserts(self):
        
        
        existing_key = IdempotencyKey.objects.create(
            merchant_id=self.merchant.id,
            key=self.key,
            request_hash=compute_request_hash(self.payload),
        )
        store_idempotency_response(existing_key, 201, {'id': 'payout-race'})

        
        with patch.object(
            IdempotencyKey.objects, 'create', side_effect=IntegrityError
        ):
            result = resolve_idempotency(self.merchant.id, self.key, self.payload)

        self.assertFalse(result.created)
        self.assertEqual(result.cached_response, {'id': 'payout-race'})
        self.assertEqual(result.cached_status, 201)

    
    
    

    def test_store_response_persists_to_db(self):
        
        result = resolve_idempotency(self.merchant.id, self.key, self.payload)
        store_idempotency_response(result.idempotency_key, 201, {'payout_id': 'xyz'})

        refreshed = IdempotencyKey.objects.get(pk=result.idempotency_key.pk)
        self.assertEqual(refreshed.response_status, 201)
        self.assertEqual(refreshed.response_body, {'payout_id': 'xyz'})


class CreatePayoutTests(TestCase):
    

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

        
        LedgerEntry.objects.create(
            merchant=self.merchant,
            entry_type=LedgerEntryType.CREDIT,
            amount=20000,
            balance_after=20000,
            description='Initial top-up',
        )

    def _create(self, key=None, payload=None):
        
        p = payload or self.payload
        return create_payout(
            merchant_id=p['merchant_id'],
            bank_account_id=p['bank_account_id'],
            amount=p['amount'],
            mode=p['mode'],
            idempotency_key_header=key or self.key,
            payload=p,
        )

    
    
    

    def test_successful_payout_creates_payout_and_ledger_entry(self):
        
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
        self.assertEqual(debits.first().balance_after, 15000)  

    def test_balance_reduced_after_payout(self):
        
        self._create()
        self.assertEqual(get_balance(self.merchant.id), 15000)

    def test_payout_linked_to_idempotency_key(self):
        
        self._create()
        payout = Payout.objects.first()
        self.assertIsNotNone(payout.idempotency_key)
        self.assertEqual(payout.idempotency_key.key, self.key)

    
    
    

    def test_insufficient_funds_raises_error(self):
        
        high_amount_payload = {**self.payload, 'amount': 999999}
        with self.assertRaises(InsufficientFundsError):
            self._create(payload=high_amount_payload)

    def test_insufficient_funds_creates_no_records(self):
        
        high_amount_payload = {**self.payload, 'amount': 999999}
        try:
            self._create(payload=high_amount_payload)
        except InsufficientFundsError:
            pass
        self.assertEqual(Payout.objects.count(), 0)
        
        self.assertEqual(LedgerEntry.objects.count(), 1)

    
    
    

    def test_duplicate_request_returns_cached_response(self):
        
        result1 = self._create()
        result2 = self._create()  

        self.assertFalse(result1.is_replay)
        self.assertTrue(result2.is_replay)
        self.assertEqual(result2.data['id'], result1.data['id'])  
        self.assertEqual(Payout.objects.count(), 1)  

    def test_duplicate_request_does_not_debit_twice(self):
        
        self._create()
        self._create()  
        self.assertEqual(get_balance(self.merchant.id), 15000)  

    def test_different_keys_create_independent_payouts(self):
        
        self._create(key='key-001')
        self._create(key='key-002')
        self.assertEqual(Payout.objects.count(), 2)
        self.assertEqual(get_balance(self.merchant.id), 10000)  

    
    
    

    def test_wrong_bank_account_raises_error(self):
        
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


class CriticalConcurrencyTests(TransactionTestCase):
    

    def setUp(self):
        self.merchant = Merchant.objects.create(
            name='Concurrency Merchant', email='race@merchant.com'
        )
        self.bank_account = BankAccount.objects.create(
            merchant=self.merchant,
            account_holder_name='Race Holder',
            account_number='123456789012',
            ifsc_code='HDFC0001234',
            is_verified=True,
        )
        
        LedgerEntry.objects.create(
            merchant=self.merchant,
            entry_type=LedgerEntryType.CREDIT,
            amount=10000,
            balance_after=10000,
            description='Initial top-up',
        )

    def test_concurrent_payouts_prevent_double_spend(self):
        
        from django.db.utils import OperationalError

        key1 = "race-key-1"
        key2 = "race-key-2"
        payload1 = {'merchant_id': str(self.merchant.id), 'bank_account_id': str(self.bank_account.id), 'amount': 10000, 'mode': 'IMPS'}
        payload2 = {'merchant_id': str(self.merchant.id), 'bank_account_id': str(self.bank_account.id), 'amount': 10000, 'mode': 'UPI'}

        def run_payout(key, payload):
            connection.close()
            try:
                return create_payout(
                    merchant_id=payload['merchant_id'],
                    bank_account_id=payload['bank_account_id'],
                    amount=payload['amount'],
                    mode=payload['mode'],
                    idempotency_key_header=key,
                    payload=payload,
                )
            except Exception as e:
                return e

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future1 = executor.submit(run_payout, key1, payload1)
            future2 = executor.submit(run_payout, key2, payload2)
            results = [future1.result(), future2.result()]

        successes = [r for r in results if not isinstance(r, Exception)]
        
        expected_failures = [
            r for r in results 
            if isinstance(r, InsufficientFundsError) or 
               (isinstance(r, OperationalError) and 'locked' in str(r).lower())
        ]

        self.assertEqual(len(successes), 1, "Exactly one payout must succeed.")
        self.assertEqual(len(expected_failures), 1, "Exactly one payout must be blocked by the lock or fail balance check.")

        self.assertEqual(Payout.objects.count(), 1)
        self.assertEqual(get_balance(self.merchant.id), 0)

    def test_idempotent_duplicate_payouts(self):
        
        from django.db.utils import OperationalError

        key = "idemp-key-concurrent"
        payload = {'merchant_id': str(self.merchant.id), 'bank_account_id': str(self.bank_account.id), 'amount': 5000, 'mode': 'IMPS'}

        def run_payout():
            connection.close()
            try:
                return create_payout(
                    merchant_id=payload['merchant_id'],
                    bank_account_id=payload['bank_account_id'],
                    amount=payload['amount'],
                    mode=payload['mode'],
                    idempotency_key_header=key,
                    payload=payload,
                )
            except Exception as e:
                return e

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future1 = executor.submit(run_payout)
            future2 = executor.submit(run_payout)
            results = [future1.result(), future2.result()]

        successes = [r for r in results if not isinstance(r, Exception)]
        lock_errors = [r for r in results if isinstance(r, OperationalError) and 'locked' in str(r).lower()]

        
        self.assertEqual(len(successes), 1, "Exactly one request must succeed outright.")
        
        
        
        if not lock_errors:
            status_codes = [r.status_code for r in successes]
            self.assertIn(201, status_codes)

        self.assertEqual(Payout.objects.count(), 1)
        self.assertEqual(get_balance(self.merchant.id), 5000)
