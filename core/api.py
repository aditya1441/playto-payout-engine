"""
api.py — DRF API Views.

Each view is thin: validate input, call the service, return the response.
No business logic lives here.
"""
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
from .models import BankAccount, Merchant, Payout


class CreatePayoutView(APIView):
    """
    POST /api/v1/payouts

    Creates a new payout for a merchant. This endpoint is idempotent:
    repeat requests with the same Idempotency-Key and body return the
    original response without creating a duplicate payout.

    Required Headers:
        Idempotency-Key: <unique string per intended payout>
            - Generate this client-side (e.g., UUID or order ID).
            - Reuse the exact same key on retry after a network failure.
            - Using the same key with a different body returns HTTP 409.

    Request Body (JSON):
        merchant_id     (UUID)    - The initiating merchant.
        bank_account_id (UUID)    - Destination bank account (must be verified).
        amount          (integer) - Amount in paise. Minimum 100 (₹1).
        mode            (string)  - IMPS | NEFT | RTGS | UPI. Default: IMPS.

    Response:
        201 Created      - Payout accepted; status is PENDING.
        200 OK           - Idempotent replay of a previously accepted payout.
        202 Accepted     - Duplicate key; original request still in-flight.
        400 Bad Request  - Validation failure (missing/invalid fields).
        404 Not Found    - Merchant not found.
        409 Conflict     - Same Idempotency-Key reused with different body.
        422 Unprocessable- Insufficient balance.
        500 Server Error - Unexpected error (check logs).
    """
    # AllowAny until auth middleware is added in a later step.
    permission_classes = [AllowAny]

    def post(self, request):
        # ── 1. Validate Idempotency-Key header ────────────────────────────
        idempotency_key = request.headers.get('Idempotency-Key', '').strip()
        if not idempotency_key:
            return Response(
                {'error': 'Idempotency-Key header is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(idempotency_key) > 255:
            return Response(
                {'error': 'Idempotency-Key must be 255 characters or fewer.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── 2. Validate request body ───────────────────────────────────────
        serializer = PayoutCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'error': 'Validation failed.', 'details': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = serializer.validated_data

        # ── 3. Delegate to service (all business logic lives there) ────────
        try:
            result = create_payout(
                merchant_id=data['merchant_id'],
                bank_account_id=data['bank_account_id'],
                amount=data['amount'],
                mode=data['mode'],
                idempotency_key_header=idempotency_key,
                payload=request.data,   # raw dict for hash computation
            )
        except IdempotencyConflictError as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        except InsufficientFundsError as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except BankAccount.DoesNotExist as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_404_NOT_FOUND,
            )

        # result.status_code is 201 (new), 200 (replay), or 202 (in-flight).
        return Response(result.data, status=result.status_code)


class BalanceView(APIView):
    """GET /api/v1/merchants/<merchant_id>/balance"""
    permission_classes = [AllowAny]

    def get(self, request, merchant_id):
        try:
            balance = get_balance(merchant_id)
            held = get_held_balance(merchant_id)
            return Response({
                'balance': balance,
                'held_balance': held
            }, status=status.HTTP_200_OK)
        except Merchant.DoesNotExist:
            return Response({'error': 'Merchant not found.'}, status=status.HTTP_404_NOT_FOUND)


class PayoutListView(APIView):
    """GET /api/v1/merchants/<merchant_id>/payouts"""
    permission_classes = [AllowAny]

    def get(self, request, merchant_id):
        # Verify merchant exists
        if not Merchant.objects.filter(id=merchant_id).exists():
            return Response({'error': 'Merchant not found.'}, status=status.HTTP_404_NOT_FOUND)
            
        payouts = Payout.objects.filter(merchant_id=merchant_id).order_by('-initiated_at')[:50]
        serializer = PayoutResponseSerializer(payouts, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class LedgerListView(APIView):
    """GET /api/v1/merchants/<merchant_id>/ledger"""
    permission_classes = [AllowAny]

    def get(self, request, merchant_id):
        from .models import LedgerEntry
        if not Merchant.objects.filter(id=merchant_id).exists():
            return Response({'error': 'Merchant not found.'}, status=status.HTTP_404_NOT_FOUND)
            
        entries = LedgerEntry.objects.filter(merchant_id=merchant_id).order_by('-created_at')[:50]
        data = [{
            'id': str(e.id),
            'type': e.entry_type,
            'amount': e.amount,
            'balance_after': e.balance_after,
            'description': e.description,
            'created_at': e.created_at.isoformat()
        } for e in entries]
        return Response(data, status=status.HTTP_200_OK)

