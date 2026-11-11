from django.urls import path
from .views import ParticipantListView

urlpatterns = [
    path("tenants/<uuid:tenant_id>/participants/", ParticipantListView.as_view(),
         name="tenant-participants"),
]
