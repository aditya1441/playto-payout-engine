import uuid
from django.db import models
from django.utils import timezone


class PayoutStatus(models.TextChoices):
    PENDING    = 'PENDING',    'Pending'
    PROCESSING = 'PROCESSING', 'Processing'
    COMPLETED  = 'COMPLETED',  'Completed'
    FAILED     = 'FAILED',     'Failed'
    CANCELLED  = 'CANCELLED',  'Cancelled'


class LedgerEntryType(models.TextChoices):
    CREDIT = 'CREDIT', 'Credit'
    DEBIT  = 'DEBIT',  'Debit'


class PayoutMode(models.TextChoices):
    IMPS = 'IMPS', 'IMPS'
    NEFT = 'NEFT', 'NEFT'
    RTGS = 'RTGS', 'RTGS'
    UPI  = 'UPI',  'UPI'


class Merchant(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name       = models.CharField(max_length=255)
    email      = models.EmailField(unique=True)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'merchants'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email'], name='idx_merchant_email'),
            models.Index(fields=['is_active'], name='idx_merchant_active'),
        ]

    def __str__(self):
        return f"Merchant({self.name}, {self.email})"


class BankAccount(models.Model):
    id                  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant            = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name='bank_accounts')
    account_holder_name = models.CharField(max_length=255)
    account_number      = models.CharField(max_length=20)
    ifsc_code           = models.CharField(max_length=11)
    is_default          = models.BooleanField(default=False)
    is_verified         = models.BooleanField(default=False)
    created_at          = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'bank_accounts'
        unique_together = [('merchant', 'account_number')]
        indexes = [
            models.Index(fields=['merchant'], name='idx_bankaccount_merchant'),
            models.Index(fields=['is_default'], name='idx_bankaccount_default'),
        ]

    def __str__(self):
        return f"BankAccount({self.account_number}, {self.ifsc_code})"


class LedgerEntry(models.Model):
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant     = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name='ledger_entries')
    payout       = models.ForeignKey(
        'Payout',
        on_delete=models.PROTECT,
        related_name='ledger_entries',
        null=True,
        blank=True,
    )
    entry_type   = models.CharField(max_length=10, choices=LedgerEntryType.choices)
    amount       = models.BigIntegerField()
    balance_after = models.BigIntegerField()
    description  = models.TextField(blank=True)
    created_at   = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = 'ledger_entries'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['merchant', 'created_at'], name='idx_ledger_merchant_date'),
            models.Index(fields=['payout'], name='idx_ledger_payout'),
            models.Index(fields=['entry_type'], name='idx_ledger_type'),
        ]

    def save(self, *args, **kwargs):
        if self.pk and LedgerEntry.objects.filter(pk=self.pk).exists():
            raise ValueError("LedgerEntry is immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("LedgerEntry is immutable and cannot be deleted.")

    def __str__(self):
        return f"LedgerEntry({self.entry_type}, {self.amount} paise, merchant={self.merchant_id})"


class Payout(models.Model):
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant       = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name='payouts')
    bank_account   = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name='payouts')
    amount         = models.BigIntegerField()
    mode           = models.CharField(max_length=10, choices=PayoutMode.choices, default=PayoutMode.IMPS)
    status         = models.CharField(max_length=20, choices=PayoutStatus.choices, default=PayoutStatus.PENDING, db_index=True)
    reference_id   = models.CharField(max_length=255, blank=True, null=True)
    failure_reason = models.TextField(blank=True, null=True)
    idempotency_key = models.OneToOneField(
        'IdempotencyKey',
        on_delete=models.PROTECT,
        related_name='payout',
        null=True,
        blank=True,
    )
    initiated_at = models.DateTimeField(default=timezone.now)
    processed_at = models.DateTimeField(null=True, blank=True)

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


class IdempotencyKey(models.Model):
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant       = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name='idempotency_keys')
    key            = models.CharField(max_length=255)
    request_hash   = models.CharField(max_length=64)
    response_status = models.IntegerField(null=True, blank=True)
    response_body  = models.JSONField(null=True, blank=True)
    created_at     = models.DateTimeField(default=timezone.now)
    expires_at     = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'idempotency_keys'
        unique_together = [('merchant', 'key')]
        indexes = [
            models.Index(fields=['merchant', 'key'], name='idx_idempotency_merchant_key'),
            models.Index(fields=['expires_at'], name='idx_idempotency_expiry'),
        ]

    def __str__(self):
        return f"IdempotencyKey({self.key}, merchant={self.merchant_id})"
