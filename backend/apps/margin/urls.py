from django.urls import path

from .views import TenantMarginSimulationView
from .planning_views import CampaignPlanPreviewView

urlpatterns = [
    path(
        "tenants/<uuid:tenant_id>/campaign-plans/preview/",
        CampaignPlanPreviewView.as_view(),
        name="campaign-plan-preview",
    ),
    path(
        "tenants/<uuid:tenant_id>/margin-simulations/",
        TenantMarginSimulationView.as_view(),
        name="tenant-margin-simulation",
    ),
]
