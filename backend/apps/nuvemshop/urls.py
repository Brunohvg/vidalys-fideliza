from django.urls import path
from .privacy_webhooks import privacy_webhook
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
    path("oauth/nuvemshop/callback/", oauth_callback, name="nuvemshop-oauth-callback"),
    path("webhooks/privacy/<slug:kind>/", privacy_webhook,
         name="nuvemshop-privacy-webhook"),
]
