from django.urls import path
from .views import MyTenantsView
from .settings_views import TenantSettingsView

urlpatterns = [
    path("me/tenants/", MyTenantsView.as_view(), name="my-tenants"),
    path("tenants/<uuid:tenant_id>/settings/", TenantSettingsView.as_view(),
         name="tenant-settings"),
]
