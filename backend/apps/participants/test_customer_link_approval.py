"""Aprovação de participante: consentimento, OAuth, idempotência e retirada."""
from datetime import timedelta
from unittest.mock import patch
import uuid

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
from apps.wallets.models import CashbackEvent
from .email_proof import consume_challenge, digest, make_token
from .enrollment_models import (
    EnrollmentCustomerLink, EnrollmentEmailChallenge,
    EnrollmentInvite, EnrollmentSubmission, ProgramTerms,
)
from .models import ProgramParticipant


@override_settings(
    FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED=True,
    FIDELIZA_PARTICIPANT_APPROVAL_ENABLED=True,
    FIDELIZA_PUBLIC_SIGNUP_ENABLED=False,
    FIDELIZA_LEDGER_WRITES_ENABLED=False,
)
class ParticipantApprovalTests(TestCase):
    def setUp(self):
        cache.clear()
        User=get_user_model()
        self.owner=User.objects.create_user(username="approval-owner")
        self.analyst=User.objects.create_user(username="approval-analyst")
        self.other_user=User.objects.create_user(username="approval-other")
        self.tenant=Tenant.objects.create(
            name="Loja com fidelização",slug="approval-test",status="active",
            external_store_id="8731",
        )
        self.other=Tenant.objects.create(
            name="Outra loja",slug="approval-foreign",status="active",
            external_store_id="9786",
        )
        for user,tenant,role in (
            (self.owner,self.tenant,"owner"),
            (self.analyst,self.tenant,"analyst"),
            (self.other_user,self.other,"owner"),
        ):
            TenantMembership.objects.create(user=user,tenant=tenant,role=role)
        self.terms=ProgramTerms.objects.create(
            tenant=self.tenant,version="v1",title="Regulamento de teste",
            body="Termos de adesão válidos apenas neste teste automatizado. "*4,
            privacy_notice="Informações de teste sobre participação e privacidade. "*4,
            active=True,approved_at=timezone.now(),
        )
        self.invite=EnrollmentInvite.objects.create(
            tenant=self.tenant,terms=self.terms,token_digest="e"*64,
            expires_at=timezone.now()+timedelta(days=1),
            consumed_at=timezone.now(),
        )
        self.submission=EnrollmentSubmission.objects.create(
            tenant=self.tenant,terms=self.terms,invitation=self.invite,
            name="Pessoa fictícia",email="cliente@example.invalid",
            terms_digest="a"*64,accepted_at=timezone.now(),
            email_verified_at=timezone.now(),status="email_verified",
            marketing_opt_in=True,
        )
        self.install=NuvemshopInstallation.objects.create(
            tenant=self.tenant,client_id="12345",store_id="8731",
            scope="read_products,read_orders,read_customers,write_orders",
            token_ciphertext="opaque-synthetic-token",
        )
        self.cfg=OAuthConfig(
            client_id="12345",client_secret="synthetic-secret",
            callback_url="https://staging.invalid/api/v1/oauth/nuvemshop/callback/",
            user_agent="Vidalys Fideliza (contato@vidalys.com.br)",
            token_keys="fake-keys",
        )
        self.client=APIClient()
        self.client.force_authenticate(self.owner)

    def endpoint(self, submission=None, tenant=None):
        return reverse("tenant-customer-match-approve",kwargs={
            "tenant_id":tenant or self.tenant.pk,
            "submission_id":submission or self.submission.pk,
        })

    def approve(self,customer_id="351",**kwargs):
        return self.client.post(self.endpoint(),{
            "customer_id":customer_id,"confirm":True,
            **kwargs,
        },format="json")

    def mock_customer_api(self,rows=None):
        if rows is None:
            rows=[{"id":"351","email":"cliente@example.invalid"}]
        return (
            patch("apps.participants.customer_link_approval.config",return_value=self.cfg),
            patch("apps.participants.customer_link_approval.decrypt_token",
                  return_value="synthetic-access-token"),
            patch("apps.participants.customer_link_approval.read_customer_candidates",
                  return_value=rows),
        )

    def test_confirm_and_retry_create_only_one_member_with_traceability(self):
        a,b,c=self.mock_customer_api()
        with a,b,c as read:
            first=self.approve()
            self.assertEqual(first.status_code,201,first.data)
            self.assertFalse(first.data["cashback_enabled"])
            self.assertFalse(first.data["orders_modified"])
            self.assertEqual(read.call_count,1)
            self.assertEqual(read.call_args.kwargs["store_id"],8731)
            self.assertEqual(read.call_args.kwargs["email"],self.submission.email)
        self.assertEqual(ProgramParticipant.objects.count(),1)
        participant=ProgramParticipant.objects.get()
        self.assertEqual(participant.external_customer_id,"351")
        self.assertEqual(participant.tenant,self.tenant)
        self.assertEqual(participant.terms_version,"v1")
        self.assertEqual(participant.status,ProgramParticipant.Status.ACTIVE)
        self.assertFalse(CashbackEvent.objects.exists())
        link=EnrollmentCustomerLink.objects.get()
        self.assertEqual(link.confirmed_by,self.owner)
        self.assertEqual(link.submission,self.submission)
        self.assertEqual(link.participant,participant)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status,"linked")
        # Replay returns same member even during throttle; does not query Nuvemshop.
        with patch("apps.participants.customer_link_approval.read_customer_candidates") as read:
            replay=self.approve()
        self.assertEqual(replay.status_code,200,replay.data)
        self.assertTrue(replay.data["already_linked"])
        self.assertEqual(replay.data["participant_id"],str(participant.pk))
        self.assertEqual(ProgramParticipant.objects.count(),1)
        self.assertEqual(EnrollmentCustomerLink.objects.count(),1)
        read.assert_not_called()

    def test_no_link_if_mismatch_or_ambiguous_customer(self):
        for rows in (
            [{"id":"351","email":"someone-else@example.invalid"}],
            [{"id":"351","email":self.submission.email},
             {"id":"352","email":self.submission.email}],
            [],
        ):
            with self.subTest(rows=rows):
                cache.clear()
                a,b,c=self.mock_customer_api(rows)
                with a,b,c:
                    self.assertEqual(self.approve().status_code,409)
        self.assertFalse(ProgramParticipant.objects.exists())
        self.assertFalse(EnrollmentCustomerLink.objects.exists())

    def test_no_link_if_client_id_changed_after_preview(self):
        a,b,c=self.mock_customer_api()
        with a,b,c:
            self.assertEqual(self.approve("999").status_code,409)
        self.assertFalse(ProgramParticipant.objects.exists())

    def test_unverified_withdrawn_and_wrong_role_blocked_before_network(self):
        with patch("apps.participants.customer_link_approval.read_customer_candidates") as read:
            self.client.force_authenticate(self.analyst)
            self.assertEqual(self.approve().status_code,403)
            self.client.force_authenticate(self.other_user)
            self.assertEqual(self.approve().status_code,404)
            self.client.force_authenticate(self.owner)
            self.submission.status="pending_verification"
            self.submission.email_verified_at=None
            self.submission.save(update_fields=["status","email_verified_at"])
            self.assertEqual(self.approve().status_code,409)
            self.submission.status="withdrawn"
            self.submission.withdrawn_at=timezone.now()
            self.submission.save(update_fields=["status","withdrawn_at"])
            self.assertEqual(self.approve().status_code,409)
        read.assert_not_called()
        self.assertFalse(ProgramParticipant.objects.exists())

    def test_gates_and_bad_payloads(self):
        with override_settings(FIDELIZA_PARTICIPANT_APPROVAL_ENABLED=False):
            self.assertEqual(self.approve().status_code,409)
        with override_settings(FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED=False):
            self.assertEqual(self.approve().status_code,409)
        for data in (
            {},{"customer_id":"351","confirm":False},
            {"customer_id":"351","confirm":True,"email":"attacker@example.invalid"},
            {"customer_id":"351 and 1=1","confirm":True},
            {"customer_id":"0","confirm":True},
            {"customer_id":351,"confirm":True},
        ):
            with self.subTest(data=data):
                self.assertEqual(self.client.post(self.endpoint(),data,
                                                  format="json").status_code,400)
        self.assertFalse(ProgramParticipant.objects.exists())

    def test_missing_scope_or_wrong_store_blocks_token(self):
        self.install.scope="read_products"
        self.install.save(update_fields=["scope"])
        self.assertEqual(self.approve().status_code,409)
        self.install.scope="read_products,read_customers"
        self.install.store_id="0001"
        self.install.save(update_fields=["scope","store_id"])
        self.assertEqual(self.approve().status_code,409)
        self.assertFalse(ProgramParticipant.objects.exists())

    def test_privacy_redact_receipt_blocks_any_new_link(self):
        PrivacyWebhookRequest.objects.create(
            tenant=self.tenant,store_id="8731",customer_id="351",
            topic=PrivacyWebhookRequest.Topic.CUSTOMER_REDACT,
            event_key="a"*64,
            state=PrivacyWebhookRequest.State.NEEDS_REVIEW,
            reason_code="pending_erasure",
        )
        a,b,c=self.mock_customer_api()
        with a,b,c:
            response=self.approve()
        self.assertEqual(response.status_code,409)
        self.assertFalse(ProgramParticipant.objects.exists())
        self.assertFalse(EnrollmentCustomerLink.objects.exists())

    def test_existing_participant_is_not_adopted_silently(self):
        ProgramParticipant.objects.create(
            tenant=self.tenant,external_customer_id="351",
            display_name="Registro prévio",contact_email="prior@example.invalid",
            consent_at=timezone.now(),
            consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL,
            terms_version="older",status=ProgramParticipant.Status.ACTIVE,
        )
        a,b,c=self.mock_customer_api()
        with a,b,c:
            response=self.approve()
        self.assertEqual(response.status_code,409)
        self.assertEqual(ProgramParticipant.objects.count(),1)
        self.assertFalse(EnrollmentCustomerLink.objects.exists())

    def test_withdrawal_after_link_revokes_participation_and_marketing(self):
        a,b,c=self.mock_customer_api()
        with a,b,c:
            self.assertEqual(self.approve().status_code,201)
        challenge_id=uuid.uuid4()
        token=make_token(challenge_id,"withdraw")
        EnrollmentEmailChallenge.objects.create(
            id=challenge_id,submission=self.submission,
            purpose="withdraw",token_digest=digest(token),
            expires_at=timezone.now()+timedelta(minutes=20),
        )
        self.assertEqual(consume_challenge(token,"withdraw"),"withdrawn")
        member=ProgramParticipant.objects.get()
        self.assertEqual(member.status,ProgramParticipant.Status.WITHDRAWN)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status,"withdrawn")
        self.assertFalse(self.submission.marketing_opt_in)
        self.assertIsNotNone(self.submission.withdrawn_at)
        self.assertEqual(consume_challenge(token,"withdraw"),None)
        self.assertEqual(self.approve().status_code,409)
        self.assertEqual(EnrollmentCustomerLink.objects.count(),1)
        self.assertFalse(CashbackEvent.objects.exists())
