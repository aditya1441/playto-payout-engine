
from rest_framework import serializers

from .models import BankAccount, Merchant, Payout, PayoutMode


class PayoutCreateSerializer(serializers.Serializer):
    merchant_id = serializers.UUIDField(
        help_text="UUID of the merchant initiating the payout.",
    )
    bank_account_id = serializers.UUIDField(
        help_text="UUID of the destination BankAccount (must belong to merchant).",
    )
    amount = serializers.IntegerField(
        min_value=100,
        help_text="Amount in paise (integer). Minimum 100 (₹1).",
    )
    mode = serializers.ChoiceField(
        choices=PayoutMode.choices,
        default=PayoutMode.IMPS,
        help_text="Transfer rail: IMPS, NEFT, RTGS, or UPI.",
    )

    def validate_bank_account_id(self, value):
        if not BankAccount.objects.filter(id=value, is_verified=True).exists():
            raise serializers.ValidationError(
                "Bank account not found or is not yet verified."
            )
        return value

    def validate_merchant_id(self, value):
        if not Merchant.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError(
                "Merchant not found or is inactive."
            )
        return value


class PayoutResponseSerializer(serializers.ModelSerializer):
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
