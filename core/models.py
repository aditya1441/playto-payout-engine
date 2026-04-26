import uuid
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Enums (TextChoices)
# ---------------------------------------------------------------------------

class PayoutStatus(models.TextChoices):
    """
    State machine for a Payout:
      PENDING → PROCESSING → COMPLETED
                           → FAILED
      PENDING → CANCELLED
    """
    PENDING    = 'PENDING',    'Pending'
    PROCESSING = 'PROCESSING', 'Processing'
    COMPLETED  = 'COMPLETED',  'Completed'
    FAILED     = 'FAILED',     'Failed'
    CANCELLED  = 'CANCELLED',  'Cancelled'


class LedgerEntryType(models.TextChoices):
    """
    Direction of money movement in the ledger.
    CREDIT increases available balance; DEBIT decreases it.
    """
    CREDIT = 'CREDIT', 'Credit'
    DEBIT  = 'DEBIT',  'Debit'


class PayoutMode(models.TextChoices):
    """
    Rail used to transfer funds.
    Stored here so we can route to the correct payment gateway.
    """
    IMPS = 'IMPS', 'IMPS'
    NEFT = 'NEFT', 'NEFT'
    RTGS = 'RTGS', 'RTGS'
    UPI  = 'UPI',  'UPI'


# ---------------------------------------------------------------------------
# Merchant
# ---------------------------------------------------------------------------

class Merchant(models.Model):
    """
    Represents a business entity that uses the payout engine.
    No balance field — balance is always derived from LedgerEntry
    to maintain a single source of truth and full auditability.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        # UUID avoids sequential ID enumeration attacks.
    )
    name = models.CharField(
        max_length=255,
        # Human-readable name for display in admin / reports.
    )
    email = models.EmailField(
        unique=True,
        # Unique contact point; used for notifications.
    )
    is_active = models.BooleanField(
        default=True,
        # Soft-disable a merchant without deleting their data.
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        # Immutable audit timestamp; NOT auto_now so migrations don't wipe it.
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        # Tracks last profile change.
    )

    class Meta:
        db_table = 'merchants'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email'], name='idx_merchant_email'),
            models.Index(fields=['is_active'], name='idx_merchant_active'),
        ]

    def __str__(self):
        return f"Merchant({self.name}, {self.email})"


# ---------------------------------------------------------------------------
# BankAccount
# ---------------------------------------------------------------------------

class BankAccount(models.Model):
    """
    A verified bank account belonging to a merchant.
    Multiple accounts per merchant are allowed, but only one can
    be the default destination for payouts at a time.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.PROTECT,
        related_name='bank_accounts',
        # PROTECT: never delete a merchant with existing bank accounts.
    )
    account_holder_name = models.CharField(
        max_length=255,
        # Must match the bank's registered name for compliance.
    )
    account_number = models.CharField(
        max_length=20,
        # Stored as string to preserve leading zeros.
    )
    ifsc_code = models.CharField(
        max_length=11,
        # Standard Indian IFSC: 4 alpha + 0 + 6 alphanumeric.
    )
    is_default = models.BooleanField(
        default=False,
        # Convenience flag for selecting the primary payout destination.
    )
    is_verified = models.BooleanField(
        default=False,
        # Only verified accounts should be eligible for payouts.
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'bank_accounts'
        # (merchant, account_number) must be unique — same merchant cannot
        # register the same account twice.
        unique_together = [('merchant', 'account_number')]
        indexes = [
            models.Index(fields=['merchant'], name='idx_bankaccount_merchant'),
            models.Index(fields=['is_default'], name='idx_bankaccount_default'),
        ]

    def __str__(self):
        return f"BankAccount({self.account_number}, {self.ifsc_code})"


# ---------------------------------------------------------------------------
# LedgerEntry (Immutable Append-Only)
# ---------------------------------------------------------------------------

class LedgerEntry(models.Model):
    """
    Immutable double-entry bookkeeping record.
    NEVER update or delete a row — only append.
    The merchant's current balance = SUM(CREDIT amounts) - SUM(DEBIT amounts).

    Immutability is enforced via overriding save() below.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.PROTECT,
        related_name='ledger_entries',
    )
    payout = models.ForeignKey(
        'Payout',
        on_delete=models.PROTECT,
        related_name='ledger_entries',
        null=True,
        blank=True,
        # Nullable: some entries (e.g., top-ups) are not tied to a payout.
    )
    entry_type = models.CharField(
        max_length=10,
        choices=LedgerEntryType.choices,
    )
    amount = models.BigIntegerField(
        # Always in paise (1 INR = 100 paise) to avoid floating-point errors.
        # BigIntegerField handles values up to 9,223,372,036,854,775,807 paise.
    )
    balance_after = models.BigIntegerField(
        # Snapshot of the merchant's running balance after this entry.
        # Useful for point-in-time audits without re-summing the entire ledger.
    )
    description = models.TextField(
        blank=True,
        # Human-readable reason for the entry (e.g., "Payout to HDFC XXXXX").
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        # Indexed for range queries when generating statements.
    )

    class Meta:
        db_table = 'ledger_entries'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['merchant', 'created_at'], name='idx_ledger_merchant_date'),
            models.Index(fields=['payout'], name='idx_ledger_payout'),
            models.Index(fields=['entry_type'], name='idx_ledger_type'),
        ]

    def save(self, *args, **kwargs):
        """
        Enforce immutability: a LedgerEntry can be created but never updated.
        """
        if self.pk and LedgerEntry.objects.filter(pk=self.pk).exists():
            raise ValueError("LedgerEntry is immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Prevent deletion of ledger entries."""
        raise ValueError("LedgerEntry is immutable and cannot be deleted.")

    def __str__(self):
        return f"LedgerEntry({self.entry_type}, {self.amount} paise, merchant={self.merchant_id})"


# ---------------------------------------------------------------------------
# Payout (State Machine)
# ---------------------------------------------------------------------------

class Payout(models.Model):
    """
    Represents a single payout instruction.
    Status transitions are enforced at the service layer, not the DB,
    to keep the model thin. Only valid transitions:
      PENDING → PROCESSING → COMPLETED | FAILED
      PENDING → CANCELLED
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.PROTECT,
        related_name='payouts',
    )
    bank_account = models.ForeignKey(
        BankAccount,
        on_delete=models.PROTECT,
        related_name='payouts',
        # PROTECT: retain historical records even if account is removed.
    )
    amount = models.BigIntegerField(
        # In paise. Must be positive — enforced via model clean().
    )
    mode = models.CharField(
        max_length=10,
        choices=PayoutMode.choices,
        default=PayoutMode.IMPS,
        # Transfer rail; determines routing and SLA.
    )
    status = models.CharField(
        max_length=20,
        choices=PayoutStatus.choices,
        default=PayoutStatus.PENDING,
        db_index=True,
        # Indexed — queries like "all PENDING payouts" are very frequent.
    )
    reference_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        # External UTR / transaction ID returned by the payment gateway.
    )
    failure_reason = models.TextField(
        blank=True,
        null=True,
        # Populated when status = FAILED; useful for debugging and merchant comms.
    )
    idempotency_key = models.OneToOneField(
        'IdempotencyKey',
        on_delete=models.PROTECT,
        related_name='payout',
        null=True,
        blank=True,
        # OneToOne: each idempotency key maps to exactly one payout.
    )
    initiated_at = models.DateTimeField(
        default=timezone.now,
        # When the payout request was accepted.
    )
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        # Set when status moves to COMPLETED or FAILED.
    )

    class Meta:
        db_table = 'payouts'
        ordering = ['-initiated_at']
        indexes = [
            models.Index(fields=['merchant', 'status'], name='idx_payout_merchant_status'),
            models.Index(fields=['merchant', 'initiated_at'], name='idx_payout_merchant_date'),
            models.Index(fields=['reference_id'], name='idx_payout_reference'),
            models.Index(fields=['status', 'initiated_at'], name='idx_payout_status_date'),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.amount is not None and self.amount <= 0:
            raise ValidationError("Payout amount must be positive.")

    def __str__(self):
        return f"Payout({self.id}, {self.amount} paise, {self.status})"


# ---------------------------------------------------------------------------
# IdempotencyKey
# ---------------------------------------------------------------------------

class IdempotencyKey(models.Model):
    """
    Ensures that duplicate API requests (retries, network failures) do not
    result in duplicate payouts. The client generates a unique key per
    intended operation and re-uses it on retry.

    Key is unique per merchant: two merchants may use the same key string
    without collision, but the same merchant cannot reuse a key.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.PROTECT,
        related_name='idempotency_keys',
    )
    key = models.CharField(
        max_length=255,
        # The client-supplied key (e.g., a UUID or order ID).
    )
    request_hash = models.CharField(
        max_length=64,
        # SHA-256 hash of the original request payload.
        # On retry, we verify the hash matches to detect conflicting requests.
    )
    response_status = models.IntegerField(
        null=True,
        blank=True,
        # HTTP status code of the response returned for the original request.
        # Replayed on duplicate requests.
    )
    response_body = models.JSONField(
        null=True,
        blank=True,
        # Full response body stored so duplicates get the exact same response.
    )
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        # Optional TTL; stale keys can be pruned by a Celery periodic task.
    )

    class Meta:
        db_table = 'idempotency_keys'
        # Core uniqueness constraint: (merchant, key) must be unique.
        unique_together = [('merchant', 'key')]
        indexes = [
            models.Index(fields=['merchant', 'key'], name='idx_idempotency_merchant_key'),
            models.Index(fields=['expires_at'], name='idx_idempotency_expiry'),
        ]

    def __str__(self):
        return f"IdempotencyKey({self.key}, merchant={self.merchant_id})"
