from django.urls import path
from .views import ParticipantListView
from .email_views import PublicEmailActionView, PublicWithdrawalRequestView
from .public_registration_views import PublicStoreJoinView, PublicStoreProgramView
from .enrollment_views import (
    InvitationView, PendingEnrollmentsView, ProgramTermsView,
    PublicAcceptView, PublicInvitationView,
)

urlpatterns = [
    path("tenants/<uuid:tenant_id>/participants/", ParticipantListView.as_view(),
         name="tenant-participants"),
    path("tenants/<uuid:tenant_id>/program-terms/", ProgramTermsView.as_view(),
         name="tenant-program-terms"),
    path("tenants/<uuid:tenant_id>/enrollment-invitations/", InvitationView.as_view(),
         name="tenant-enrollment-invitations"),
    path("tenants/<uuid:tenant_id>/enrollment-submissions/", PendingEnrollmentsView.as_view(),
         name="tenant-enrollment-submissions"),
    path("public/programs/<slug:slug>/", PublicStoreProgramView.as_view(),
         name="public-store-program"),
    path("public/programs/<slug:slug>/join/", PublicStoreJoinView.as_view(),
         name="public-store-join"),
    path("public/programs/<slug:slug>/withdraw-request/", PublicWithdrawalRequestView.as_view(),
         name="public-store-withdraw-request"),
    path("public/enrollment/email-action/", PublicEmailActionView.as_view(),
         name="public-enrollment-email-action"),
    path("public/enrollment/preview/", PublicInvitationView.as_view(),
         name="public-enrollment-preview"),
    path("public/enrollment/accept/", PublicAcceptView.as_view(),
         name="public-enrollment-accept"),
]
