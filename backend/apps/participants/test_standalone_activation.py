"""Participação sem Nuvemshop, sem crédito e com vínculo externo opcional."""
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase,override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.customers.models import ChannelCustomerReference, CustomerProfile, VerifiedCustomerContact
from apps.nuvemshop.models import NuvemshopInstallation
from apps.tenants.models import Tenant
from apps.wallets.models import CashbackEvent,CashbackWallet
from .email_proof import digest,make_token
from .enrollment_models import EnrollmentInvite,EnrollmentEmailChallenge,EnrollmentSubmission,ProgramTerms,EnrollmentCustomerLink
from .models import ProgramParticipant
from .customer_link_service import link_verified_submission


@override_settings(
    FIDELIZA_STANDALONE_MEMBERSHIP_ENABLED=True,
    FIDELIZA_AUTO_CUSTOMER_LINK_ENABLED=False,
    FIDELIZA_EMAIL_DELIVERY_ENABLED=True,
    FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED=False,
    FIDELIZA_LEDGER_WRITES_ENABLED=False,
)
class StandaloneActivationTests(TestCase):
    def setUp(self):
        cache.clear()
        now=timezone.now()
        self.tenant=Tenant.objects.create(
            name="Clube Independente",slug="clube-independent-qa",
            platform="independent",status=Tenant.Status.ACTIVE,
        )
        terms=ProgramTerms.objects.create(
            tenant=self.tenant,version="v1",title="Regulamento",
            body="O cliente entra somente com consentimento verificado. "*3,
            privacy_notice="Informações e dados protegidos para este teste. "*4,
            approved_at=now,
        )
        invitation=EnrollmentInvite.objects.create(
            tenant=self.tenant,terms=terms,token_digest="b"*64,
            expires_at=now+timedelta(hours=1),consumed_at=now,
        )
        self.submission=EnrollmentSubmission.objects.create(
            tenant=self.tenant,invitation=invitation,terms=terms,
            name="Pessoa QA",email="qa@example.invalid",accepted_at=now,
            terms_digest="c"*64,marketing_opt_in=False,
        )
        self.challenge=EnrollmentEmailChallenge.objects.create(
            submission=self.submission,purpose=EnrollmentEmailChallenge.Purpose.VERIFY,
            token_digest="d"*64,expires_at=now+timedelta(minutes=20),
        )
        self.token=make_token(self.challenge.id,"verify")
        self.challenge.token_digest=digest(self.token)
        self.challenge.save(update_fields=["token_digest"])
        self.api=APIClient(enforce_csrf_checks=True)
        self.api.get(reverse("auth-session"))
        self.csrf=self.api.cookies["csrftoken"].value

    def verify(self):
        return self.api.post(reverse("public-enrollment-email-action"),{
            "token":self.token,"action":"verify",
        },format="json",HTTP_X_CSRFTOKEN=self.csrf)

    def test_verified_email_enrolls_without_store_api_or_points(self):
        response=self.verify()
        self.assertEqual(response.status_code,200,response.data)
        self.assertTrue(response.data["participant_created"])
        self.assertEqual(response.data["club_slug"], self.tenant.slug)
        self.assertFalse(response.data["identity_verified_in_nuvemshop"])
        member=ProgramParticipant.objects.get()
        self.assertIsNone(member.external_customer_id)
        self.assertEqual(member.tenant_id,self.tenant.id)
        self.assertEqual(CustomerProfile.objects.get(participant=member).tenant_id, self.tenant.id)
        self.assertEqual(VerifiedCustomerContact.objects.count(), 1)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status,EnrollmentSubmission.Status.MEMBER)
        self.assertEqual(self.submission.participant_id,member.id)
        self.assertEqual(self.verify().status_code,410)
        self.assertEqual(ProgramParticipant.objects.count(),1)
        self.assertFalse(CashbackWallet.objects.exists())
        self.assertFalse(CashbackEvent.objects.exists())

    def test_manual_member_can_later_link_same_nuvemshop_customer(self):
        self.assertEqual(self.verify().status_code,200)
        member=ProgramParticipant.objects.get()
        self.tenant.platform="nuvemshop"
        self.tenant.external_store_id="8731"
        self.tenant.save(update_fields=["platform","external_store_id"])
        NuvemshopInstallation.objects.create(
            tenant=self.tenant,client_id="12345",store_id="8731",
            scope="read_customers",token_ciphertext="synthetic-not-real",
        )
        link,created=link_verified_submission(
            tenant_id=self.tenant.id,submission_id=self.submission.id,
            customer_id="351",client_id="12345",store_id="8731",
        )
        self.assertTrue(created)
        self.assertEqual(link.participant_id,member.id)
        member.refresh_from_db()
        self.assertEqual(member.external_customer_id,"351")
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status,EnrollmentSubmission.Status.LINKED)
        self.assertEqual(EnrollmentCustomerLink.objects.count(),1)
        self.assertEqual(CustomerProfile.objects.count(), 1)
        self.assertEqual(ChannelCustomerReference.objects.get().external_id, "351")
        self.assertFalse(CashbackWallet.objects.exists())

    def test_withdrawal_disables_local_member(self):
        self.assertEqual(self.verify().status_code,200)
        now=timezone.now()
        challenge=EnrollmentEmailChallenge.objects.create(
            submission=self.submission,
            purpose=EnrollmentEmailChallenge.Purpose.WITHDRAW,
            token_digest="e"*64,expires_at=now+timedelta(minutes=15),
        )
        token=make_token(challenge.id,"withdraw")
        challenge.token_digest=digest(token)
        challenge.save(update_fields=["token_digest"])
        result=self.api.post(reverse("public-enrollment-email-action"),{
            "token":token,"action":"withdraw",
        },format="json",HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(result.status_code,200,result.data)
        self.assertEqual(ProgramParticipant.objects.get().status,ProgramParticipant.Status.WITHDRAWN)
        self.assertFalse(CashbackEvent.objects.exists())
