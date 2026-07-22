from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import DepositView, TransactionViewSet, TransferView, WithdrawView

router = DefaultRouter()
router.register("transactions", TransactionViewSet, basename="transaction")

urlpatterns = router.urls + [
    path("transactions/transfer/", TransferView.as_view(), name="transfer"),
    path("transactions/deposit/", DepositView.as_view(), name="deposit"),
    path("transactions/withdraw/", WithdrawView.as_view(), name="withdraw"),
]
