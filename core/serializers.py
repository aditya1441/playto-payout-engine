"""
serializers.py — DRF serializers for the payout API.

Input:  PayoutCreateSerializer  — validates and cleans the POST body.
Output: PayoutResponseSerializer — shapes the JSON response.
"""
from rest_framework import serializers

from .models import BankAccount, Merchant, Payout, PayoutMode


class PayoutCreateSerializer(serializers.Serializer):
    """
    Validates the POST /api/v1/payouts request body.

    In production, merchant_id would come from the authenticated token
    (e.g., JWT sub), not from the request body. It is accepted here as
    a body field because auth middleware is not yet implemented.
    """
    merchant_id = serializers.UUIDField(
        help_text="UUID of the merchant initiating the payout.",
    )
    bank_account_id = serializers.UUIDField(
        help_text="UUID of the destination BankAccount (must belong to merchant).",
    )
    amount = serializers.IntegerField(
        min_value=100,  # Minimum ₹1 (100 paise)
        help_text="Amount in paise (integer). Minimum 100 (₹1).",
    )
    mode = serializers.ChoiceField(
        choices=PayoutMode.choices,
        default=PayoutMode.IMPS,
        help_text="Transfer rail: IMPS, NEFT, RTGS, or UPI.",
    )

    def validate_bank_account_id(self, value):
        """
        Check the BankAccount exists at the serializer level.
        We deliberately do NOT check merchant ownership here — that
        is done inside the atomic service function where the merchant
        row is already locked, preventing TOCTOU attacks.
        """
        if not BankAccount.objects.filter(id=value, is_verified=True).exists():
            raise serializers.ValidationError(
                "Bank account not found or is not yet verified."
            )
        return value

    def validate_merchant_id(self, value):
        """Ensure the merchant exists and is active before entering the transaction."""
        if not Merchant.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError(
                "Merchant not found or is inactive."
            )
        return value


class PayoutResponseSerializer(serializers.ModelSerializer):
    """
    Serializes a Payout instance into the API response.
    All monetary amounts are returned in paise (integer).
    """
    merchant_id    = serializers.UUIDField(source='merchant.id', read_only=True)
    bank_account_id = serializers.UUIDField(source='bank_account.id', read_only=True)

    class Meta:
        model  = Payout
        fields = [
            'id',
            'merchant_id',
            'bank_account_id',
            'amount',
            'mode',
            'status',
            'initiated_at',
        ]
        read_only_fields = fields
