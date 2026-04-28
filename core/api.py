from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import PayoutCreateSerializer, PayoutResponseSerializer
from .services import (
    IdempotencyConflictError,
    InsufficientFundsError,
    create_payout,
    get_balance,
    get_held_balance,
)
from .models import BankAccount, LedgerEntry, Merchant, Payout


class CreatePayoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        idempotency_key = request.headers.get('Idempotency-Key', '').strip()
        if not idempotency_key:
            return Response({'error': 'Idempotency-Key header is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(idempotency_key) > 255:
            return Response({'error': 'Idempotency-Key must be 255 characters or fewer.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = PayoutCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': 'Validation failed.', 'details': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        try:
            result = create_payout(
                merchant_id=data['merchant_id'],
                bank_account_id=data['bank_account_id'],
                amount=data['amount'],
                mode=data['mode'],
                idempotency_key_header=idempotency_key,
                payload=request.data,
            )
        except IdempotencyConflictError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_409_CONFLICT)
        except InsufficientFundsError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except BankAccount.DoesNotExist as exc:
            return Response({'error': str(exc)}, status=status.HTTP_404_NOT_FOUND)

        return Response(result.data, status=result.status_code)


class BalanceView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, merchant_id):
        try:
            balance = get_balance(merchant_id)
            held = get_held_balance(merchant_id)
            return Response({'balance': balance, 'held_balance': held})
        except Merchant.DoesNotExist:
            return Response({'error': 'Merchant not found.'}, status=status.HTTP_404_NOT_FOUND)


class PayoutListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, merchant_id):
        if not Merchant.objects.filter(id=merchant_id).exists():
            return Response({'error': 'Merchant not found.'}, status=status.HTTP_404_NOT_FOUND)
        payouts = Payout.objects.filter(merchant_id=merchant_id).order_by('-initiated_at')[:50]
        serializer = PayoutResponseSerializer(payouts, many=True)
        return Response(serializer.data)


class LedgerListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, merchant_id):
        if not Merchant.objects.filter(id=merchant_id).exists():
            return Response({'error': 'Merchant not found.'}, status=status.HTTP_404_NOT_FOUND)
        entries = LedgerEntry.objects.filter(merchant_id=merchant_id).order_by('-created_at')[:50]
        data = [
            {
                'id': str(e.id),
                'type': e.entry_type,
                'amount': e.amount,
                'balance_after': e.balance_after,
                'description': e.description,
                'created_at': e.created_at.isoformat(),
            }
            for e in entries
        ]
        return Response(data)
