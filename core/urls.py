from django.urls import path
from .api import CreatePayoutView

urlpatterns = [
    path('payouts', CreatePayoutView.as_view(), name='create-payout'),
]
