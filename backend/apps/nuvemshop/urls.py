from django.urls import path
from .order_preview_views import OrderPreviewView
from .order_event_inspection import OrderEventInspectionView
from .order_webhooks import OrderEventsView, order_webhook
from .privacy_webhooks import privacy_webhook
from .privacy_views import PrivacyRequestsView
from .privacy_report_views import PrivacyReportDownloadView, PrivacyReportConfirmView
from .views import (
    NuvemshopStatusView, OAuthStartView, LiveCatalogPreviewView, oauth_callback
)

urlpatterns = [
    path("tenants/<uuid:tenant_id>/nuvemshop/status/",
         NuvemshopStatusView.as_view(), name="nuvemshop-status"),
    path("tenants/<uuid:tenant_id>/nuvemshop/connect/",
         OAuthStartView.as_view(), name="nuvemshop-connect"),
    path("tenants/<uuid:tenant_id>/nuvemshop/catalog/preview/",
         LiveCatalogPreviewView.as_view(), name="nuvemshop-catalog-preview"),
    path("tenants/<uuid:tenant_id>/nuvemshop/orders/<int:order_id>/preview/",
         OrderPreviewView.as_view(), name="nuvemshop-order-preview"),
    path("oauth/nuvemshop/callback/", oauth_callback, name="nuvemshop-oauth-callback"),
    path("tenants/<uuid:tenant_id>/nuvemshop/orders/events/<uuid:event_id>/inspect/",
         OrderEventInspectionView.as_view(), name="nuvemshop-order-event-inspect"),
    path("webhooks/orders/<slug:kind>/", order_webhook,
         name="nuvemshop-order-webhook"),
    path("tenants/<uuid:tenant_id>/nuvemshop/orders/events/",
         OrderEventsView.as_view(), name="nuvemshop-order-events"),
    path("webhooks/privacy/<slug:kind>/", privacy_webhook,
         name="nuvemshop-privacy-webhook"),
    path("tenants/<uuid:tenant_id>/privacy/requests/",
         PrivacyRequestsView.as_view(), name="tenant-privacy-requests"),
    path("tenants/<uuid:tenant_id>/privacy/requests/<uuid:request_id>/report/",
         PrivacyReportDownloadView.as_view(), name="tenant-privacy-report"),
    path("tenants/<uuid:tenant_id>/privacy/requests/<uuid:request_id>/confirm/",
         PrivacyReportConfirmView.as_view(), name="tenant-privacy-report-confirm"),
]
