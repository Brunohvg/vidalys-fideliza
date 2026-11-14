from django.urls import path

from .views import ClubVoucherIssueView, VoucherCheckView, VoucherRedeemView

urlpatterns = [
    path("public/clubs/<slug:slug>/vouchers/issue/",
         ClubVoucherIssueView.as_view(), name="loyalty-member-voucher-issue"),
    path("tenants/<uuid:tenant_id>/loyalty/vouchers/validate/",
         VoucherCheckView.as_view(), name="loyalty-voucher-check"),
    path("tenants/<uuid:tenant_id>/loyalty/vouchers/redeem/",
         VoucherRedeemView.as_view(), name="loyalty-voucher-redeem"),
]
