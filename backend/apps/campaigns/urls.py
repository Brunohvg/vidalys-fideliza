from django.urls import path
from .views import CampaignDraftDetailView, CampaignDraftListView
from .benefit_views import BenefitSimulationView

urlpatterns = [
    path(
        "tenants/<uuid:tenant_id>/campaign-drafts/<uuid:draft_id>/simulate/",
        BenefitSimulationView.as_view(), name="benefit-simulate",
    ),
    path(
        "tenants/<uuid:tenant_id>/campaign-drafts/",
        CampaignDraftListView.as_view(), name="campaign-draft-list",
    ),
    path(
        "tenants/<uuid:tenant_id>/campaign-drafts/<uuid:draft_id>/",
        CampaignDraftDetailView.as_view(), name="campaign-draft-detail",
    ),
]
