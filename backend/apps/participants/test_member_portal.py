"""Acesso do consumidor isolado por loja e prova de e-mail; sem pagamentos."""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import EmailDispatch
from apps.tenants.models import Tenant, TenantMembership
from .email_proof import digest, make_token
from .enrollment_models import (
    EnrollmentInvite, EnrollmentSubmission, MemberAccessChallenge, ProgramTerms,
)
from .member_portal_views import SESSION_EXPIRES
from .models import ProgramParticipant


@override_settings(
    FIDELIZA_EMAIL_DELIVERY_ENABLED=True,
    FIDELIZA_PUBLIC_BASE_URL="https://staging.invalid",
    FIDELIZA_LEDGER_WRITES_ENABLED=False,
)
class MemberClubAccessTests(TestCase):
    def setUp(self):
        cache.clear()
        self.tenant = Tenant.objects.create(
            name="Loja QA", slug="clube-qa", status=Tenant.Status.ACTIVE,
            platform="independent",
        )
        self.other = Tenant.objects.create(
            name="Outra loja", slug="outro-clube", status=Tenant.Status.ACTIVE,
            platform="independent",
        )
        now=timezone.now()
        self.terms=ProgramTerms.objects.create(
            tenant=self.tenant, version="v1", title="Regulamento QA",
            body="Regras somente para verificação. " * 5,
            privacy_notice="Dados usados para adesão. " * 10,
            approved_at=now,
        )
        invite=EnrollmentInvite.objects.create(
            tenant=self.tenant, terms=self.terms,
            token_digest="a"*64,
            expires_at=now+timedelta(hours=1), consumed_at=now,
        )
        self.submission=EnrollmentSubmission.objects.create(
            tenant=self.tenant, terms=self.terms, invitation=invite,
            name="Pessoa Teste", email="membro@example.invalid",
            terms_digest="b"*64, accepted_at=now,
            email_verified_at=now, status=EnrollmentSubmission.Status.EMAIL_VERIFIED,
        )
        self.api=APIClient(enforce_csrf_checks=True)
        self.api.get(reverse("auth-session"))
        self.csrf=self.api.cookies["csrftoken"].value

    def call(self,name,payload=None,slug=None):
        return self.api.post(
            reverse(name,kwargs={"slug":slug or self.tenant.slug}),
            payload if payload is not None else {}, format="json",
            HTTP_X_CSRFTOKEN=self.csrf,
        )

    def request_link(self,email="membro@example.invalid",slug=None):
        with patch("apps.participants.tasks.send_member_access_email.delay") as mail:
            with self.captureOnCommitCallbacks(execute=True):
                result=self.call("member-club-access-request",{"email":email},slug)
        return result,mail

    def test_visitor_can_read_public_club_but_no_private_data(self):
        public=self.api.get(reverse("member-club-public",kwargs={"slug":self.tenant.slug}))
        self.assertEqual(public.status_code,200,public.data)
        self.assertEqual(public.data["store_name"],"Loja QA")
        self.assertNotIn("membro@example.invalid",str(public.data))
        self.assertFalse(public.data["points_enabled"])
        me=self.api.get(reverse("member-club-me",kwargs={"slug":self.tenant.slug}))
        self.assertEqual(me.status_code,401)
        self.assertNotIn("Pessoa Teste",str(me.data))

    def test_generic_email_and_private_token_from_verified_submission(self):
        missing,mail=self.request_link(email="inexistente@example.invalid")
        self.assertEqual(missing.status_code,202)
        self.assertFalse(MemberAccessChallenge.objects.exists())
        mail.assert_not_called()
        valid,mail=self.request_link()
        self.assertEqual(valid.status_code,202)
        self.assertEqual(valid.data,missing.data)
        self.assertEqual(MemberAccessChallenge.objects.count(),1)
        challenge=MemberAccessChallenge.objects.get()
        token=make_token(challenge.id,"member")
        self.assertEqual(challenge.token_digest,digest(token))
        self.assertNotIn(token,str(challenge.__dict__))
        self.assertEqual(EmailDispatch.objects.count(),1)
        self.assertEqual(EmailDispatch.objects.get().kind,EmailDispatch.Kind.MEMBER)
        mail.assert_called_once()

    def test_token_one_time_and_session_isolated_from_other_shop(self):
        self.request_link()
        challenge=MemberAccessChallenge.objects.get()
        token=make_token(challenge.id,"member")
        stranger=self.call("member-club-access-confirm",{"token":token},slug=self.other.slug)
        self.assertEqual(stranger.status_code,410)
        self.assertIsNone(MemberAccessChallenge.objects.get().consumed_at)
        result=self.call("member-club-access-confirm",{"token":token})
        self.assertEqual(result.status_code,200,result.data)
        self.assertEqual(self.call("member-club-access-confirm",{"token":token}).status_code,410)
        me=self.api.get(reverse("member-club-me",kwargs={"slug":self.tenant.slug}))
        self.assertEqual(me.status_code,200,me.data)
        self.assertEqual(me.data["display_name"],"Pessoa Teste")
        self.assertEqual(me.data["status"],"awaiting_link")
        self.assertIsNone(me.data["points_balance"])
        self.assertFalse(me.data["redemption_enabled"])
        self.assertEqual(self.api.get(reverse("member-club-me",kwargs={"slug":self.other.slug})).status_code,401)
        self.assertEqual(self.call("member-club-logout").status_code,200)
        self.assertEqual(self.api.get(reverse("member-club-me",kwargs={"slug":self.tenant.slug})).status_code,401)

    def test_unverified_submission_cannot_request_link_and_withdrawal_revokes(self):
        self.submission.email_verified_at=None
        self.submission.status=EnrollmentSubmission.Status.PENDING_VERIFICATION
        self.submission.save(update_fields=["email_verified_at","status"])
        response,_=self.request_link()
        self.assertEqual(response.status_code,202)
        self.assertFalse(MemberAccessChallenge.objects.exists())
        self.submission.email_verified_at=timezone.now()
        self.submission.status=EnrollmentSubmission.Status.EMAIL_VERIFIED
        self.submission.save(update_fields=["email_verified_at","status"])
        cache.clear()
        self.request_link()
        token=make_token(MemberAccessChallenge.objects.get().id,"member")
        self.assertEqual(self.call("member-club-access-confirm",{"token":token}).status_code,200)
        self.submission.status=EnrollmentSubmission.Status.WITHDRAWN
        self.submission.withdrawn_at=timezone.now()
        self.submission.save(update_fields=["status","withdrawn_at"])
        self.assertEqual(self.api.get(reverse("member-club-me",kwargs={"slug":self.tenant.slug})).status_code,401)

    def test_session_expires_and_merchant_auth_does_not_inherit_member(self):
        User=get_user_model()
        merchant=User.objects.create_user(username="merchant-check")
        TenantMembership.objects.create(
            tenant=self.tenant,user=merchant,role=TenantMembership.Role.OWNER,
        )
        self.api.force_login(merchant)
        self.assertEqual(self.api.get(reverse("member-club-me",kwargs={"slug":self.tenant.slug})).status_code,401)
        self.request_link()
        token=make_token(MemberAccessChallenge.objects.get().id,"member")
        self.assertEqual(self.call("member-club-access-confirm",{"token":token}).status_code,200)
        session=self.api.session
        session[SESSION_EXPIRES]=1
        session.save()
        self.assertEqual(self.api.get(reverse("member-club-me",kwargs={"slug":self.tenant.slug})).status_code,401)

    def test_expired_link_cannot_login(self):
        self.request_link()
        challenge=MemberAccessChallenge.objects.get()
        token=make_token(challenge.id,"member")
        challenge.expires_at=timezone.now()-timedelta(seconds=1)
        challenge.save(update_fields=["expires_at"])
        self.assertEqual(self.call("member-club-access-confirm",{"token":token}).status_code,410)
        self.assertFalse(ProgramParticipant.objects.exists())
