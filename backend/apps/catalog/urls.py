from django.urls import path
from .views import CatalogReconcilePreviewView

urlpatterns = [
    path(
        "tenants/<uuid:tenant_id>/catalog/reconcile-preview/",
        CatalogReconcilePreviewView.as_view(),
        name="catalog-reconcile-preview",
    ),
]
