from django.urls import path
from .api import CreatePayoutView, BalanceView, PayoutListView, LedgerListView

urlpatterns = [
    path('payouts', CreatePayoutView.as_view(), name='create-payout'),
    path('merchants/<uuid:merchant_id>/balance', BalanceView.as_view(), name='get-balance'),
    path('merchants/<uuid:merchant_id>/payouts', PayoutListView.as_view(), name='list-payouts'),
    path('merchants/<uuid:merchant_id>/ledger', LedgerListView.as_view(), name='list-ledger'),
]
