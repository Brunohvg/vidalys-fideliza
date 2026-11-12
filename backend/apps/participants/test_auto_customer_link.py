"""Adesão automática é condicional, idempotente e isolada.

Nenhuma rede real; somente a API Nuvemshop com cliente sintético injetado.
"""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.nuvemshop.models import NuvemshopInstallation
from apps.nuvemshop.privacy_models import PrivacyWebhookRequest
from apps.nuvemshop.security import OAuthConfig
from apps.tenants.models import Tenant, TenantMembership
from apps.wallets.models import CashbackEvent, CashbackWallet
from .email_proof import digest, make_token
from .enrollment_models import EnrollmentEmailChallenge, EnrollmentSubmission, ProgramTerms, EnrollmentInvite, EnrollmentCustomerLink
from .models import ProgramParticipant


@override_settings(
    FIDELIZA_AUTO_CUSTOMER_LINK_ENABLED=True,
    FIDELIZA_EMAIL_DELIVERY_ENABLED=True,
    FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED=True,
    FIDELIZA_PARTICIPANT_APPROVAL_ENABLED=True,
    FIDELIZA_LEDGER_WRITES_ENABLED=False,
)
class AutoCustomerLinkTests(TestCase):
    def setUp(self):
        cache.clear()
        User=get_user_model()
        self.owner=User.objects.create_user(username="auto-owner")
        self.tenant=Tenant.objects.create(
            name="Loja piloto auto",slug="auto-loja",
            status=Tenant.Status.ACTIVE,
            platform="nuvemshop",external_store_id="8731",
        )
        self.other=Tenant.objects.create(
            name="Outra loja",slug="auto-other",
            status=Tenant.Status.ACTIVE,platform="nuvemshop",
            external_store_id="9919",
        )
        TenantMembership.objects.create(
            user=self.owner,tenant=self.tenant,role=TenantMembership.Role.OWNER,
        )
        self.install=NuvemshopInstallation.objects.create(
            tenant=self.tenant,client_id="12345",store_id="8731",
            scope="read_customers",token_ciphertext="opaque-test-ciphertext",
        )
        now=timezone.now()
        self.terms=ProgramTerms.objects.create(
            tenant=self.tenant,version="v1",title="Regulamento",
            body="Aceite consciente e sem recompensas liberadas. "*4,
            privacy_notice="A loja responde às solicitações dos titulares. "*4,
            approved_at=now,active=True,
        )
        invite=EnrollmentInvite.objects.create(
            tenant=self.tenant,terms=self.terms,
            token_digest="a"*64,consumed_at=now,
            expires_at=now+timedelta(hours=1),
        )
        self.submission=EnrollmentSubmission.objects.create(
            tenant=self.tenant,terms=self.terms,invitation=invite,
            name="Pessoa fictícia",email="test@example.invalid",
            accepted_at=now,terms_digest="b"*64,
            marketing_opt_in=False,
        )
        self.challenge=EnrollmentEmailChallenge.objects.create(
            submission=self.submission,purpose="verify",
            token_digest="c"*64,expires_at=now+timedelta(minutes=20),
        )
        self.token=make_token(self.challenge.pk,"verify")
        self.challenge.token_digest=digest(self.token)
        self.challenge.save(update_fields=["token_digest"])
        self.cfg=OAuthConfig(
            client_id="12345",client_secret="synthetic",
            callback_url="https://staging.invalid/api/v1/oauth/nuvemshop/callback/",
            user_agent="Fideliza CI (qa@example.invalid)",
            token_keys="synthetic-keys",
        )
        self.public=APIClient(enforce_csrf_checks=True)
        self.public.get(reverse("auth-session"))
        self.csrf=self.public.cookies["csrftoken"].value

    def action(self,token=None):
        return self.public.post(
            reverse("public-enrollment-email-action"),{
                "token":token or self.token,"action":"verify",
            },format="json",HTTP_X_CSRFTOKEN=self.csrf,
        )

    def mocked(self,customers=None):
        if customers is None:
            customers=[{"id":"351","email":"test@example.invalid"}]
        return (
            patch("apps.participants.customer_link_auto.config",return_value=self.cfg),
            patch("apps.participants.customer_link_auto.decrypt_token",
                  return_value="synthetic-access-token"),
            patch("apps.participants.customer_link_auto.read_customer_candidates",
                  return_value=customers),
        )

    def test_unique_match_links_automatically_once_no_financial_side_effect(self):
        a,b,c=self.mocked()
        with a,b,c as read:
            result=self.action()
        self.assertEqual(result.status_code,200,result.data)
        self.assertTrue(result.data["identity_verified_in_nuvemshop"])
        self.assertTrue(result.data["participant_created"])
        self.assertFalse(result.data["cashback_enabled"])
        self.assertNotIn("351",str(result.data))
        self.assertNotIn("test@example.invalid",str(result.data))
        self.assertEqual(read.call_args.kwargs["store_id"],8731)
        self.assertEqual(read.call_args.kwargs["email"],"test@example.invalid")
        self.assertEqual(ProgramParticipant.objects.count(),1)
        participant=ProgramParticipant.objects.get(tenant=self.tenant)
        self.assertEqual(participant.external_customer_id,"351")
        self.assertEqual(participant.terms_version,"v1")
        self.assertFalse(EnrollmentCustomerLink.objects.get(
            participant=participant).confirmed_by_id)
        self.assertEqual(
            EnrollmentCustomerLink.objects.get(participant=participant).source,
            "nuvemshop_customer_auto_verified_email",
        )
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status,EnrollmentSubmission.Status.LINKED)
        self.assertEqual(self.action().status_code,410)
        self.assertEqual(ProgramParticipant.objects.count(),1)
        self.assertFalse(CashbackEvent.objects.exists())
        self.assertFalse(CashbackWallet.objects.exists())
        self.assertFalse(ProgramParticipant.objects.filter(tenant=self.other).exists())

    def test_missing_or_ambiguous_customer_is_not_auto_enrolled(self):
        for candidates in (
            [],[{"id":"351","email":"other@example.invalid"}],
            [{"id":"351","email":"test@example.invalid"},
             {"id":"352","email":"test@example.invalid"}],
        ):
            with self.subTest(candidates=candidates):
                # Cada subteste usa rollback de savepoint para reaproveitar token.
                from django.db import transaction
                with transaction.atomic():
                    sid=transaction.savepoint()
                    a,b,c=self.mocked(candidates)
                    with a,b,c:
                        result=self.action()
                    self.assertEqual(result.status_code,200)
                    self.assertFalse(result.data["participant_created"])
                    self.assertFalse(result.data["identity_verified_in_nuvemshop"])
                    self.assertFalse(ProgramParticipant.objects.exists())
                    self.assertEqual(
                        EnrollmentSubmission.objects.get(pk=self.submission.pk).status,
                        EnrollmentSubmission.Status.EMAIL_VERIFIED,
                    )
                    transaction.savepoint_rollback(sid)

    def test_scope_feature_and_suspended_store_fail_closed(self):
        scenarios=[
            {"scope":"read_products"},
            {"status":Tenant.Status.SUSPENDED},
            {"store":"9999"},
        ]
        for case in scenarios:
            with self.subTest(case=case):
                original_scope=self.install.scope
                original_store=self.install.store_id
                original_status=self.tenant.status
                if case.get("scope"):
                    self.install.scope=case["scope"]
                    self.install.save(update_fields=["scope"])
                if case.get("store"):
                    self.install.store_id=case["store"]
                    self.install.save(update_fields=["store_id"])
                if case.get("status"):
                    self.tenant.status=case["status"]
                    self.tenant.save(update_fields=["status"])
                with patch("apps.participants.customer_link_auto.read_customer_candidates") as read:
                    result=self.action()
                expected=410 if case.get("status") else 200
                self.assertEqual(result.status_code,expected,result.data)
                if expected==200:
                    self.assertFalse(result.data["participant_created"])
                read.assert_not_called()
                self.assertFalse(ProgramParticipant.objects.exists())
                self.install.scope=original_scope
                self.install.store_id=original_store
                self.install.save(update_fields=["scope","store_id"])
                self.tenant.status=original_status
                self.tenant.save(update_fields=["status"])
                EnrollmentSubmission.objects.filter(pk=self.submission.pk).update(
                    status=EnrollmentSubmission.Status.PENDING_VERIFICATION,
                    email_verified_at=None,
                )
                EnrollmentEmailChallenge.objects.filter(pk=self.challenge.pk).update(
                    consumed_at=None,
                )
                self.submission.refresh_from_db()
                self.challenge.refresh_from_db()

    def test_privacy_redact_blocks_automatic_link(self):
        PrivacyWebhookRequest.objects.create(
            tenant=self.tenant,store_id="8731",customer_id="351",
            topic=PrivacyWebhookRequest.Topic.CUSTOMER_REDACT,
            event_key="f"*64,state=PrivacyWebhookRequest.State.NEEDS_REVIEW,
            reason_code="pending_erasure",
        )
        a,b,c=self.mocked()
        with a,b,c:
            response=self.action()
        self.assertEqual(response.status_code,200,response.data)
        self.assertFalse(response.data["participant_created"])
        self.assertFalse(ProgramParticipant.objects.exists())
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status,"email_verified")

    def test_flag_off_does_not_query_nuvemshop(self):
        with override_settings(FIDELIZA_AUTO_CUSTOMER_LINK_ENABLED=False), \
                patch("apps.participants.customer_link_auto.read_customer_candidates") as read:
            result=self.action()
        self.assertEqual(result.status_code,200)
        self.assertFalse(result.data["participant_created"])
        read.assert_not_called()
        self.assertFalse(ProgramParticipant.objects.exists())

    def test_transient_provider_failure_keeps_verified_state_and_manual_review(self):
        from apps.nuvemshop.customer_lookup import CustomerReadError
        a,b,c=self.mocked()
        with a,b,c as read:
            read.side_effect=CustomerReadError("Temporary failure")
            result=self.action()
        self.assertEqual(result.status_code,200)
        self.assertFalse(result.data["participant_created"])
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status,"email_verified")
        self.assertFalse(CashbackWallet.objects.exists())
