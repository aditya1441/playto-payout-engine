"""
services.py — Business logic layer.

All DB-level computations live here. Views and tasks must never
directly aggregate the ledger; they must call these service functions.
"""
from django.db.models import Sum, Case, When, IntegerField, Value
from django.db.models.functions import Coalesce

from .models import LedgerEntry, LedgerEntryType, Merchant


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
