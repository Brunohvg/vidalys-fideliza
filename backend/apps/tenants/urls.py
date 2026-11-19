from django.urls import path
from .views import MyTenantsView
from .settings_views import TenantAddressView, TenantSettingsView

urlpatterns = [
    path("me/tenants/", MyTenantsView.as_view(), name="my-tenants"),
    path("tenants/<uuid:tenant_id>/settings/", TenantSettingsView.as_view(),
         name="tenant-settings"),
    path("tenants/<uuid:tenant_id>/settings/address/", TenantAddressView.as_view(),
         name="tenant-club-address"),
]
