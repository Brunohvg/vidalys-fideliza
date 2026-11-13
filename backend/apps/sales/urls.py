from django.urls import path
from .views import ManualSalesView, ManualSaleReviewView, PointRuleDraftView

urlpatterns = [
    path("tenants/<uuid:tenant_id>/sales/manual/", ManualSalesView.as_view(),
         name="manual-sales"),
    path("tenants/<uuid:tenant_id>/sales/manual/<uuid:sale_id>/review/",
         ManualSaleReviewView.as_view(), name="manual-sale-review"),
    path("tenants/<uuid:tenant_id>/loyalty/point-rule-draft/",
         PointRuleDraftView.as_view(), name="point-rule-draft"),
]
