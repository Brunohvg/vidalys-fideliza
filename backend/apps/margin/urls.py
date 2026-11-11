from django.urls import path

from .views import TenantMarginSimulationView

urlpatterns = [
    path(
        "tenants/<uuid:tenant_id>/margin-simulations/",
        TenantMarginSimulationView.as_view(),
        name="tenant-margin-simulation",
    ),
]
