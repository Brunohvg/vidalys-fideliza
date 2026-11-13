from django.urls import path
from .views import ManualSalesView, ManualSaleReviewView, PointRuleDraftView
from .benefit_draft_views import DiscountRewardDraftsView, DiscountRewardDraftDetailView, PointCampaignDraftsView

urlpatterns = [
    path("tenants/<uuid:tenant_id>/loyalty/reward-drafts/", DiscountRewardDraftsView.as_view(), name="discount-reward-drafts"),
    path("tenants/<uuid:tenant_id>/loyalty/reward-drafts/<uuid:reward_id>/", DiscountRewardDraftDetailView.as_view(), name="discount-reward-draft-detail"),
    path("tenants/<uuid:tenant_id>/loyalty/point-campaign-drafts/", PointCampaignDraftsView.as_view(), name="point-campaign-drafts"),
    path("tenants/<uuid:tenant_id>/sales/manual/", ManualSalesView.as_view(),
         name="manual-sales"),
    path("tenants/<uuid:tenant_id>/sales/manual/<uuid:sale_id>/review/",
         ManualSaleReviewView.as_view(), name="manual-sale-review"),
    path("tenants/<uuid:tenant_id>/loyalty/point-rule-draft/",
         PointRuleDraftView.as_view(), name="point-rule-draft"),
]
