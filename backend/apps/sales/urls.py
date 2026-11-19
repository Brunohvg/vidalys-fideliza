from django.urls import path
from .views import (ManualSalesView, ManualSaleReviewView, ManualSaleLinkView, PointRuleDraftView,
                    ManualSaleBatchConfirmView, ManualSaleUndoView, CounterWalletView, CounterPilotView)
from .benefit_draft_views import DiscountRewardDraftsView, DiscountRewardDraftDetailView, DiscountRewardPublicationView, PointCampaignDraftsView, PointCampaignDraftDetailView, PointCampaignAudienceView, PointCampaignPublishView

urlpatterns = [
    path("tenants/<uuid:tenant_id>/loyalty/reward-drafts/", DiscountRewardDraftsView.as_view(), name="discount-reward-drafts"),
    path("tenants/<uuid:tenant_id>/loyalty/reward-drafts/<uuid:reward_id>/", DiscountRewardDraftDetailView.as_view(), name="discount-reward-draft-detail"),
    path("tenants/<uuid:tenant_id>/loyalty/reward-drafts/<uuid:reward_id>/publication/", DiscountRewardPublicationView.as_view(), name="discount-reward-publication"),
    path("tenants/<uuid:tenant_id>/loyalty/point-campaign-drafts/", PointCampaignDraftsView.as_view(), name="point-campaign-drafts"),
    path("tenants/<uuid:tenant_id>/loyalty/point-campaign-drafts/<uuid:campaign_id>/", PointCampaignDraftDetailView.as_view(), name="point-campaign-draft-detail"),
    path("tenants/<uuid:tenant_id>/loyalty/point-campaign-drafts/audience/", PointCampaignAudienceView.as_view(), name="point-campaign-audience"),
    path("tenants/<uuid:tenant_id>/loyalty/point-campaign-drafts/<uuid:campaign_id>/publish/", PointCampaignPublishView.as_view(), name="point-campaign-publish"),
    path("tenants/<uuid:tenant_id>/sales/manual/", ManualSalesView.as_view(),
         name="manual-sales"),
    path("tenants/<uuid:tenant_id>/sales/manual/<uuid:sale_id>/link/",
         ManualSaleLinkView.as_view(), name="manual-sale-link"),
    path("tenants/<uuid:tenant_id>/sales/manual/<uuid:sale_id>/review/",
         ManualSaleReviewView.as_view(), name="manual-sale-review"),
    path("tenants/<uuid:tenant_id>/sales/manual/confirm-batch/",
         ManualSaleBatchConfirmView.as_view(), name="manual-sale-confirm-batch"),
    path("tenants/<uuid:tenant_id>/sales/manual/<uuid:sale_id>/undo/",
         ManualSaleUndoView.as_view(), name="manual-sale-undo"),
    path("tenants/<uuid:tenant_id>/sales/counter/participants/<uuid:participant_id>/wallet/",
         CounterWalletView.as_view(), name="counter-wallet"),
    path("tenants/<uuid:tenant_id>/sales/pilot/",
         CounterPilotView.as_view(), name="counter-pilot"),
    path("tenants/<uuid:tenant_id>/loyalty/point-rule-draft/",
         PointRuleDraftView.as_view(), name="point-rule-draft"),
]
