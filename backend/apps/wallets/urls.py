from django.urls import path
from .views import ParticipantWalletView

urlpatterns = [
    path(
        "tenants/<uuid:tenant_id>/participants/<uuid:participant_id>/wallet/",
        ParticipantWalletView.as_view(), name="participant-wallet",
    ),
]
