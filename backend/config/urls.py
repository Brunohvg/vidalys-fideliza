from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.core.urls")),
    path("api/v1/", include("apps.tenants.urls")),
    path("api/v1/auth/", include("apps.core.auth_urls")),
    path("api/v1/", include("apps.margin.urls")),
    path("api/v1/", include("apps.costs.urls")),
    path("api/v1/", include("apps.catalog.urls")),
    path("api/v1/", include("apps.nuvemshop.urls")),
    path("api/v1/", include("apps.participants.urls")),
    path("api/v1/", include("apps.campaigns.urls")),
    path("api/v1/", include("apps.wallets.urls")),
]
