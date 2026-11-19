from django.urls import path
from .member_portal_views import (
    MemberClubPublicView, MemberClubRequestAccessView,
    MemberClubConfirmAccessView, MemberClubMeView, MemberClubLogoutView, MemberClubCodeView,
)
from .member_profile_views import ClubIconView, ClubManifestView, MemberExportView, MemberCouponView, MemberProfileView
from .views import ParticipantListView
from .detail_views import ParticipantDetailView, ParticipantStatusView
from .phone_views import ParticipantPhoneLookupView, ParticipantPhoneView
from .customer_link_preview import CustomerLinkPreviewView
from .customer_link_approval import CustomerLinkApproveView
from .email_views import PublicEmailActionView, PublicWithdrawalRequestView
from .public_registration_views import PublicStoreJoinView, PublicStoreProgramView
from .enrollment_views import (
    InvitationView, PendingEnrollmentsView, ProgramTermsView,
    PublicAcceptView, PublicInvitationView,
)

urlpatterns = [
    path("public/clubs/<slug:slug>/",
         MemberClubPublicView.as_view(), name="member-club-public"),
    path("public/clubs/<slug:slug>/access/request/",
         MemberClubRequestAccessView.as_view(), name="member-club-access-request"),
    path("public/clubs/<slug:slug>/access/confirm/",
         MemberClubConfirmAccessView.as_view(), name="member-club-access-confirm"),
    path("public/clubs/<slug:slug>/me/",
         MemberClubMeView.as_view(), name="member-club-me"),
    path("public/clubs/<slug:slug>/logout/",
         MemberClubLogoutView.as_view(), name="member-club-logout"),
    path("public/clubs/<slug:slug>/access/code/",
         MemberClubCodeView.as_view(), name="member-club-access-code"),
    path("public/clubs/<slug:slug>/me/profile/",
         MemberProfileView.as_view(), name="member-club-profile"),
    path("public/clubs/<slug:slug>/me/export/",
         MemberExportView.as_view(), name="member-club-export"),
    path("public/clubs/<slug:slug>/coupons/",
         MemberCouponView.as_view(), name="member-club-coupon"),
    path("public/clubs/<slug:slug>/manifest.webmanifest",
         ClubManifestView.as_view(), name="member-club-manifest"),
    path("public/clubs/<slug:slug>/icon.svg",
         ClubIconView.as_view(), name="member-club-icon"),
    path("tenants/<uuid:tenant_id>/participants/", ParticipantListView.as_view(),
         name="tenant-participants"),
    path("tenants/<uuid:tenant_id>/participants/by-phone/", ParticipantPhoneLookupView.as_view(),
         name="tenant-participant-by-phone"),
    path("tenants/<uuid:tenant_id>/participants/<uuid:participant_id>/", ParticipantDetailView.as_view(),
         name="tenant-participant-detail"),
    path("tenants/<uuid:tenant_id>/participants/<uuid:participant_id>/status/", ParticipantStatusView.as_view(),
         name="tenant-participant-status"),
    path("tenants/<uuid:tenant_id>/participants/<uuid:participant_id>/phone/", ParticipantPhoneView.as_view(),
         name="tenant-participant-phone"),
    path("tenants/<uuid:tenant_id>/program-terms/", ProgramTermsView.as_view(),
         name="tenant-program-terms"),
    path("tenants/<uuid:tenant_id>/enrollment-invitations/", InvitationView.as_view(),
         name="tenant-enrollment-invitations"),
    path("tenants/<uuid:tenant_id>/enrollment-submissions/", PendingEnrollmentsView.as_view(),
         name="tenant-enrollment-submissions"),
    path("tenants/<uuid:tenant_id>/enrollment-submissions/<uuid:submission_id>/customer-match/preview/",
         CustomerLinkPreviewView.as_view(), name="tenant-customer-match-preview"),
    path("tenants/<uuid:tenant_id>/enrollment-submissions/<uuid:submission_id>/customer-match/approve/",
         CustomerLinkApproveView.as_view(), name="tenant-customer-match-approve"),
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
