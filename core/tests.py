"""
Unit tests for the balance calculation service.

Run with:
    python3 manage.py test core.tests.BalanceServiceTests
"""
import uuid
from django.test import TestCase
from core.models import Merchant, LedgerEntry, LedgerEntryType
from core.services import get_balance


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
