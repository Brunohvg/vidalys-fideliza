from django.urls import path
from .views import CostItemsView, CostItemDetailView, CostHistoryView

urlpatterns = [
    path("tenants/<uuid:tenant_id>/cost-items/", CostItemsView.as_view(), name="cost-items"),
    path("tenants/<uuid:tenant_id>/cost-items/<uuid:item_id>/", CostItemDetailView.as_view(), name="cost-item-detail"),
    path("tenants/<uuid:tenant_id>/cost-items/<uuid:item_id>/history/", CostHistoryView.as_view(), name="cost-item-history"),
]
