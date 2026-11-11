from django.urls import path
from .views import MyTenantsView

urlpatterns = [path("me/tenants/", MyTenantsView.as_view(), name="my-tenants")]
